# orchestrator-c-heterogeneous/predictive-deploy/canary_controller.py
# Stage 3 Phase 2: polls Prometheus over a real time window, comparing v2's
# error rate/CPU against v1's baseline, then makes a real promote/rollback
# decision -- not a simulated recommendation. Reuses risk_scorer.py's
# Prometheus helper (_query_instant, PROMETHEUS_URL) rather than
# reimplementing it, so both scripts hit Prometheus the exact same way.
#
# Run from: orchestrator-c-heterogeneous/predictive-deploy/
# Venv: venv-anomaly-detector (has requests; nothing else needed)
# Requires: kubectl port-forward svc/prometheus-server 9090:80 -n monitoring
#           running, AND real traffic hitting order-svc during the poll
#           window (run load_generator.py concurrently in another terminal --
#           this script does not generate its own traffic, to keep it a
#           decision engine, not a load generator).

import json
import os
import subprocess
import time
import argparse 
from datetime import datetime, timezone

from risk_scorer import _query_instant, PROMETHEUS_URL, K8S_NAMESPACE, HANDOFFS_DIR, SCRIPT_DIR

DEPLOYMENT_V1 = "order-svc"
DEPLOYMENT_V2 = "order-svc-v2"

# Same sum()-wrapped pattern as risk_scorer.py's ERROR_RATE_QUERY (D28 fix),
# parameterized by version label instead of hardcoded.
def _cpu_query(version: str) -> str:
    # avg() handles the (currently 1-replica, but potentially multi-replica)
    # case correctly -- averages across however many pods that version has,
    # rather than only reading whichever pod's series happens to sort first.
    return f'avg(order_svc_cpu_percent{{version="{version}"}})'


def _error_rate_query(version: str) -> str:
    return (
        f'sum(rate(order_svc_requests_total{{status="500",version="{version}"}}[5m])) '
        f'/ sum(rate(order_svc_requests_total{{version="{version}"}}[5m]))'
    )


def sample_version(version: str) -> dict:
    return {
        "cpu_pct": _query_instant(_cpu_query(version)),
        "error_rate": _query_instant(_error_rate_query(version)),
    }

def poll_both_and_average(window_seconds: int, interval_seconds: int) -> tuple[dict, dict]:
    """Samples v1 AND v2 together at each timestamp within one shared
    window, instead of polling them in two separate back-to-back windows.
    A canary comparison is only fair if both versions are measured under
    the same traffic conditions at the same moments -- polling them
    sequentially means they're compared against two different slices of
    real time, which isn't a real apples-to-apples comparison."""
    v1_samples = []
    v2_samples = []
    elapsed = 0
    while elapsed <= window_seconds:
        v1_samples.append(sample_version("v1"))
        v2_samples.append(sample_version("v2"))
        time.sleep(interval_seconds)
        elapsed += interval_seconds

    def _average(samples: list[dict]) -> dict:
        cpu_values = [s["cpu_pct"] for s in samples]
        error_values = [s["error_rate"] for s in samples]
        return {
            "cpu_pct_avg": round(sum(cpu_values) / len(cpu_values), 2),
            "error_rate_avg": round(sum(error_values) / len(error_values), 4),
            "sample_count": len(samples),
        }

    return _average(v1_samples), _average(v2_samples)


def get_replica_count(deployment_name: str) -> int:
    result = subprocess.run(
        [
            "kubectl", "get", "deployment", deployment_name,
            "-n", K8S_NAMESPACE,
            "-o", "jsonpath={.status.replicas}",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"kubectl get deployment {deployment_name} failed: {result.stderr.strip()}")
    raw = result.stdout.strip()
    return int(raw) if raw else 0

def promote(v1_replica_count: int, dry_run: bool = False) -> None:
    """Scale v2 up to v1's current replica count, scale v1 down to 0.
    A real cutover, not a simulated one -- verified via kubectl afterward,
    same verification-discipline convention as the rest of this project."""
    if dry_run:
        print(f"  [DRY RUN] Would promote: scale {DEPLOYMENT_V2} to {v1_replica_count}, "
              f"scale {DEPLOYMENT_V1} to 0. No kubectl commands executed.")
        return
    print(f"  Promoting: scaling {DEPLOYMENT_V2} to {v1_replica_count}, {DEPLOYMENT_V1} to 0...")
    subprocess.run(
        ["kubectl", "scale", f"deployment/{DEPLOYMENT_V2}", "-n", K8S_NAMESPACE,
         f"--replicas={v1_replica_count}"],
        check=True,
    )
    subprocess.run(
        ["kubectl", "scale", f"deployment/{DEPLOYMENT_V1}", "-n", K8S_NAMESPACE,
         "--replicas=0"],
        check=True,
    )

def rollback(dry_run: bool = False) -> None:
    """Delete v2 entirely, leave v1 untouched -- matches the design's
    'delete v2, keep v1' rollback definition."""
    if dry_run:
        print(f"  [DRY RUN] Would roll back: delete {DEPLOYMENT_V2}. No kubectl commands executed.")
        return
    print(f"  Rolling back: deleting {DEPLOYMENT_V2}...")
    subprocess.run(
        ["kubectl", "delete", "deployment", DEPLOYMENT_V2, "-n", K8S_NAMESPACE],
        check=True,
    )


def decide(v1_stats: dict, v2_stats: dict, error_tolerance: float = 0.02, cpu_tolerance_pct: float = 5.0) -> dict:
    """Promote only if v2 is not meaningfully worse than v1 on either
    metric. Small tolerances absorb real sampling noise -- v2 doesn't have
    to be strictly better on every single sample, just not regressed."""
    error_ok = v2_stats["error_rate_avg"] <= v1_stats["error_rate_avg"] + error_tolerance
    cpu_ok = v2_stats["cpu_pct_avg"] <= v1_stats["cpu_pct_avg"] + cpu_tolerance_pct

    if error_ok and cpu_ok:
        decision = "promote"
        reason = (
            f"v2 error_rate {v2_stats['error_rate_avg']} <= v1 {v1_stats['error_rate_avg']} + tolerance, "
            f"v2 cpu_pct {v2_stats['cpu_pct_avg']} <= v1 {v1_stats['cpu_pct_avg']} + tolerance."
        )
    else:
        decision = "rollback"
        failed = []
        if not error_ok:
            failed.append(f"error_rate regressed (v2 {v2_stats['error_rate_avg']} > v1 {v1_stats['error_rate_avg']} + tolerance)")
        if not cpu_ok:
            failed.append(f"cpu_pct regressed (v2 {v2_stats['cpu_pct_avg']} > v1 {v1_stats['cpu_pct_avg']} + tolerance)")
        reason = "; ".join(failed)

    return {"decision": decision, "reason": reason}

def main(window_seconds: int = 60, interval_seconds: int = 10, dry_run: bool = False):
    print(f"Stage 3 Phase 2: canary comparison over a {window_seconds}s window "
          f"({interval_seconds}s samples). Make sure load_generator.py is running "
          f"concurrently in another terminal, or this will mostly measure idle CPU/zero errors.")
    if dry_run:
        print("  [DRY RUN MODE] Will compare and decide, but will NOT scale or delete anything.")

    v1_replica_count = get_replica_count(DEPLOYMENT_V1)
    print(f"  v1 current replicas: {v1_replica_count}")

    print(f"  Polling v1 and v2 together over the same {window_seconds}s window...")
    v1_stats, v2_stats = poll_both_and_average(window_seconds, interval_seconds)
    print(f"    v1: cpu_pct_avg={v1_stats['cpu_pct_avg']}  error_rate_avg={v1_stats['error_rate_avg']}")
    print(f"    v2: cpu_pct_avg={v2_stats['cpu_pct_avg']}  error_rate_avg={v2_stats['error_rate_avg']}")

    result = decide(v1_stats, v2_stats)
    print(f"  Decision: {result['decision']} -- {result['reason']}")

    if result["decision"] == "promote":
        promote(v1_replica_count, dry_run=dry_run)
    else:
        rollback(dry_run=dry_run)

    output = {
        "stage": 3,
        "phase": "canary",
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "window_seconds": window_seconds,
        "interval_seconds": interval_seconds,
        "v1": v1_stats,
        "v2": v2_stats,
        **result,
    }

    os.makedirs(HANDOFFS_DIR, exist_ok=True)
    out_path = os.path.join(HANDOFFS_DIR, "stage3-canary.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Written: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 3 Phase 2: canary comparison and promote/rollback decision")
    parser.add_argument("--dry-run", action="store_true", help="Compare and decide, but don't actually scale or delete anything")
    parser.add_argument("--window-seconds", type=int, default=60)
    parser.add_argument("--interval-seconds", type=int, default=10)
    args = parser.parse_args()
    main(window_seconds=args.window_seconds, interval_seconds=args.interval_seconds, dry_run=args.dry_run)
