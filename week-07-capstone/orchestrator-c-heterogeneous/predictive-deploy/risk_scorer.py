# orchestrator-c-heterogeneous/predictive-deploy/risk_scorer.py
# Stage 3 Phase 1: pulls 3 real inputs (current order-svc CPU%/error rate
# from Prometheus, current replica count from kubectl, real OPA/conftest
# policy pass/fail from Stage 2's Terraform plan) and combines them into a
# risk score + proceed/block gate decision. Writes handoffs/stage3-risk.json.
#
# No fabricated inputs -- every number here is something the pipeline can
# actually measure right now, not a placeholder constant (contrast with
# Stage 5's D25 placeholders, which existed only because Stage 3 didn't
# exist yet).
#
# Run from: orchestrator-c-heterogeneous/predictive-deploy/
# Venv: venv-anomaly-detector (already has `requests`; nothing else needed)
# Requires: kubectl port-forward svc/prometheus-server 9090:80 -n monitoring
#           (running in a separate terminal), and `terraform`/`conftest` on PATH.

import json
import os
import subprocess
import time
import math
from datetime import datetime, timezone

import requests

PROMETHEUS_URL = "http://localhost:9090"  # same as anomaly_detector.py

# Paths are relative to this script's own directory (predictive-deploy/),
# a sibling of observability/, remediation/, iac/, and handoffs/ under
# orchestrator-c-heterogeneous/ -- matches D26's fix (always resolve paths
# relative to a known anchor, not the caller's cwd).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IAC_DIR = os.path.join(SCRIPT_DIR, "..", "iac")
HANDOFFS_DIR = os.path.join(SCRIPT_DIR, "..", "handoffs")

K8S_NAMESPACE = "orders"
# order-svc-v2 is now the live/production deployment -- D29's verified canary promote scaled order-svc to 0 and order-svc-v2 to 1
DEPLOYMENT_NAME = "order-svc-v2"

# Same PromQL expressions as anomaly_detector.py's fetch_real_metrics(),
# reused verbatim (not reinvented) so "current risk" and "current anomaly
# detection" are reading the identical signal definitions.
CPU_QUERY = "order_svc_cpu_percent"
ERROR_RATE_QUERY = (
    'sum(rate(order_svc_requests_total{status="500"}[5m])) '
    '/ sum(rate(order_svc_requests_total[5m]))'
)


def _query_instant(promql: str) -> float:
    """Instant-query counterpart to anomaly_detector.py's _query_range():
    same base URL, same error handling, but hits /api/v1/query (a single
    current value) instead of /api/v1/query_range (a time series)."""
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": promql})
    resp.raise_for_status()
    result = resp.json()["data"]["result"]
    if not result:
        # No traffic yet (e.g. error_rate's rate() has no data before the
        # first requests land) -- 0.0 is the correct default, not missing data.
        return 0.0
    value = float(result[0]["value"][1])
    if math.isnan(value):
        # A NaN here means Prometheus's own division hit 0/0 -- genuinely
        # ambiguous data (not "definitely zero"), so this must NOT silently
        # become float("nan") flowing into a >= comparison, which Python
        # evaluates as False and would default the gate to "proceed" on
        # undefined data. Treat it the same as "no data yet."
        return 0.0
    return value

def get_current_cpu_and_error_rate() -> tuple[float, float]:
    try:
        cpu_pct = _query_instant(CPU_QUERY)
        error_rate = _query_instant(ERROR_RATE_QUERY)
    except requests.exceptions.ConnectionError as e:
        raise ValueError(
            "Could not reach Prometheus -- confirm 'kubectl port-forward "
            "svc/prometheus-server 9090:80 -n monitoring' is running."
        ) from e
    return cpu_pct, error_rate


def get_current_replica_count() -> int:
    """Real replica count via kubectl -- not a hardcoded assumption."""
    result = subprocess.run(
        [
            "kubectl", "get", "deployment", DEPLOYMENT_NAME,
            "-n", K8S_NAMESPACE,
            "-o", "jsonpath={.status.replicas}",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ValueError(
            f"kubectl get deployment failed (is the '{K8S_NAMESPACE}' namespace "
            f"up and '{DEPLOYMENT_NAME}' deployed?): {result.stderr.strip()}"
        )
    raw = result.stdout.strip()
    if not raw:
        # Deployment exists but .status.replicas hasn't populated yet
        # (e.g. just applied) -- 0 is accurate, not an error.
        return 0
    return int(raw)


def run_policy_gate() -> dict:
    """Re-runs the real Stage 2 OPA/conftest check fresh: terraform plan ->
    terraform show -json -> conftest test --output json. Fresh each call,
    deliberately -- a cached prior result could reflect infra that's since
    changed (matches the design's 'real, not just a recommendation' spirit)."""

    # Step 0: terraform init is idempotent/cheap once providers are cached,
    # and without it a missing .terraform/ (e.g. fresh clone) would make
    # `plan` fail for an unrelated reason. Output suppressed -- only the
    # exit code matters here.
    init = subprocess.run(
        ["terraform", "init", "-input=false"],
        cwd=IAC_DIR, capture_output=True, text=True,
    )
    if init.returncode != 0:
        raise ValueError(f"terraform init failed:\n{init.stderr.strip()}")

    # Step 1: real plan against real current GCP state.
    plan = subprocess.run(
        ["terraform", "plan", "-input=false", "-out=tfplan.binary"],
        cwd=IAC_DIR, capture_output=True, text=True,
    )
    if plan.returncode != 0:
        raise ValueError(f"terraform plan failed:\n{plan.stderr.strip()}")

    # Step 2: convert to JSON ourselves (avoids a shell=True redirect).
    show = subprocess.run(
        ["terraform", "show", "-json", "tfplan.binary"],
        cwd=IAC_DIR, capture_output=True, text=True,
    )
    if show.returncode != 0:
        raise ValueError(f"terraform show failed:\n{show.stderr.strip()}")

    tfplan_path = os.path.join(IAC_DIR, "tfplan.json")
    with open(tfplan_path, "w") as f:
        f.write(show.stdout)

    # Step 3: real conftest run, structured JSON output (not scraped text)
    # so pass/fail is parsed, not guessed from stdout formatting.
    conftest = subprocess.run(
        ["conftest", "test", "tfplan.json", "--policy", "policy/", "--output", "json"],
        cwd=IAC_DIR, capture_output=True, text=True,
    )
    # conftest exits 1 on policy failures -- that's expected, not a crash.
    # Only treat it as an error if the JSON itself is unparseable.
    try:
        conftest_results = json.loads(conftest.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"conftest output was not valid JSON (stderr: {conftest.stderr.strip()})"
        ) from e

    # A run "passes" only if every file result has zero failures. Checking
    # both the parsed JSON AND the exit code (rather than trusting either
    # alone) matches the verification-discipline convention.
    all_failures = [f for entry in conftest_results for f in entry.get("failures", [])]
    passed_by_json = len(all_failures) == 0
    passed_by_exit_code = conftest.returncode == 0
    if passed_by_json != passed_by_exit_code:
        raise ValueError(
            "conftest's JSON output and exit code disagree on pass/fail -- "
            "treating as a hard failure rather than guessing which is right."
        )

    return {
        "passed": passed_by_json,
        "failure_count": len(all_failures),
        "failure_messages": [f.get("msg", "") for f in all_failures],
    }


def compute_risk_score(cpu_pct: float, error_rate: float, policy_passed: bool) -> dict:
    """Combines the 3 real inputs into a 0-100 risk score + gate decision.
    Weights/thresholds below are this script's own scoring logic (not a
    measured input) -- reasonable starting points, worth revisiting once
    real deploys have run through this and given actual signal.

    A failed policy check is a hard block regardless of CPU/error levels --
    an infra-policy violation isn't something a healthy service can offset."""

    cpu_risk = min(cpu_pct / 100.0, 1.0)        # 0-1, saturates at 100% CPU
    error_risk = min(error_rate, 1.0)            # already 0-1
    policy_risk = 0.0 if policy_passed else 1.0

    # Error rate weighted highest: it's the most direct signal of current
    # user-facing instability, ahead of CPU (a leading indicator) or policy
    # (a gate, not a spectrum).
    risk_score = round(
        (cpu_risk * 30) + (error_risk * 40) + (policy_risk * 30), 1
    )

    if not policy_passed:
        gate_decision = "block"
        gate_reason = "OPA/conftest policy check failed -- hard gate, independent of risk score."
    elif risk_score >= 60:
        gate_decision = "block"
        gate_reason = f"Risk score {risk_score} >= 60 threshold."
    else:
        gate_decision = "proceed"
        gate_reason = f"Risk score {risk_score} below 60 threshold; policy check passed."

    return {
        "risk_score": risk_score,
        "risk_breakdown": {
            "cpu_risk_contribution": round(cpu_risk * 30, 1),
            "error_risk_contribution": round(error_risk * 40, 1),
            "policy_risk_contribution": round(policy_risk * 30, 1),
        },
        "gate_decision": gate_decision,
        "gate_reason": gate_reason,
    }


def main():
    print("Stage 3 Phase 1: computing real risk score for order-svc deploy...")

    cpu_pct, error_rate = get_current_cpu_and_error_rate()
    print(f"  CPU: {cpu_pct:.2f}%  |  Error rate: {error_rate:.4f}")

    replica_count = get_current_replica_count()
    print(f"  Current replicas: {replica_count}")

    print("  Running fresh terraform plan -> conftest check...")
    policy_result = run_policy_gate()
    print(f"  Policy check passed: {policy_result['passed']}")
    if not policy_result["passed"]:
        for msg in policy_result["failure_messages"]:
            print(f"    - {msg}")

    scoring = compute_risk_score(cpu_pct, error_rate, policy_result["passed"])
    print(f"  Risk score: {scoring['risk_score']}/100")
    print(f"  Gate decision: {scoring['gate_decision']} ({scoring['gate_reason']})")

    output = {
        "stage": 3,
        "phase": "risk_score",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": "order-svc",
        "inputs": {
            "cpu_pct": round(cpu_pct, 2),
            "error_rate": round(error_rate, 4),
            "current_replicas": replica_count,
            "policy_check": policy_result,
        },
        **scoring,
    }

    os.makedirs(HANDOFFS_DIR, exist_ok=True)
    out_path = os.path.join(HANDOFFS_DIR, "stage3-risk.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Written: {out_path}")

    # Non-zero exit on "block" so this composes cleanly with Phase 4's
    # future orchestrator (risk -> gate -> canary chain).
    if scoring["gate_decision"] == "block":
        exit(1)


if __name__ == "__main__":
    main()
