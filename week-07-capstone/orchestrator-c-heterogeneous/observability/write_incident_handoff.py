# write_incident_handoff.py
# Stage 4 Phase 6: maps the real anomaly_detector.py -> alert_grouper.py ->
# rca_agent.py pipeline's output into remediation_agent.py's exact expected
# handoffs/stage4-incident.json schema, then chains into Stage 5 via subprocess.
#
# IMPORTANT -- placeholder constants (see D25 in decisions.md): max_replicas,
# target_cpu_pct, and error_budget_remaining are NOT measurable facts about
# the current system. They are autoscaling-policy inputs that would normally
# come from a Kubernetes HorizontalPodAutoscaler -- but Stage 3 (predictive
# deploy / autoscaling policy) has not been built yet, and order-svc's actual
# manifest has no HPA at all. These three values are explicit stand-ins for
# that not-yet-built policy, not real measured/configured state.

import json
import subprocess
import sys

from anomaly_detector import fetch_real_metrics, fit_detector
from alert_grouper import group_alerts
from rca_agent import synthesize_rca, write_rca_report

# --- placeholder constants (D25) -- NOT real measured/configured values ---
PLACEHOLDER_MAX_REPLICAS = 10
PLACEHOLDER_TARGET_CPU_PCT = 60
PLACEHOLDER_ERROR_BUDGET_REMAINING = 1.0  # assume full budget: no real SLO tracking exists yet


def get_current_replicas(deployment: str = "order-svc", namespace: str = "orders") -> int:
    """The ONE field in peak_metrics that IS a real, live fact -- queried
    directly from the actual K8s Deployment, not hardcoded."""
    result = subprocess.run(
        ["kubectl", "get", "deployment", deployment, "-n", namespace,
         "-o", "jsonpath={.spec.replicas}"],
        capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())


def build_incident_json(incident, rca: dict) -> dict:
    """Maps the real Incident + rca dict into remediation_agent.py's exact
    expected schema -- renaming anomaly_detector.py's column names to match
    what remediation_agent.py's load_incident()/run_remediation() expect."""
    current_replicas = get_current_replicas()

    return {
        "incident_id": incident.incident_id,
        "service": "order-svc",
        "detected_at": incident.start_time.isoformat(),
        "peak_metrics": {
            "cpu_utilization_pct": incident.peak_metrics.get("cpu_pct", 0.0),
            "error_rate": incident.peak_metrics.get("error_rate", 0.0),
            "p99_latency_ms": incident.peak_metrics.get("latency_p99_ms", 0.0),
            "error_budget_remaining": PLACEHOLDER_ERROR_BUDGET_REMAINING,  # placeholder, see D25
            "current_replicas": current_replicas,  # REAL, queried live
            "max_replicas": PLACEHOLDER_MAX_REPLICAS,  # placeholder, see D25
            "target_cpu_pct": PLACEHOLDER_TARGET_CPU_PCT,  # placeholder, see D25
        },
        "rca_summary": rca,
    }


def main():
    df = fetch_real_metrics(minutes=30)
    result = fit_detector(df, contamination=0.04)
    incidents = group_alerts(result)

    if not incidents:
        print("No anomalies detected in the queried window -- nothing to hand off.")
        return

    # Use the most recent incident if multiple exist -- Stage 5 handles
    # one incident at a time, same as the original hand-written fixture.
    incident = incidents[-1]
    print(f"Using {incident.incident_id}: {incident.peak_metrics}")

    rca = synthesize_rca(incident)
    write_rca_report(rca, incident, out_path=f"output/rca_report_{incident.incident_id}.md")

    handoff = build_incident_json(incident, rca)

    handoff_path = "../handoffs/stage4-incident.json"
    with open(handoff_path, "w") as f:
        json.dump(handoff, f, indent=2)
    print(f"[HANDOFF] Wrote {handoff_path}")

    print("\n--- Chaining into Stage 5 (remediation_agent.py) ---\n")
    subprocess.run(
        [sys.executable, "remediation_agent.py", handoff_path],
        cwd="../remediation",  # so remediation_agent.py's own relative paths
                                 # (itsm_tickets/, ../handoffs/) resolve correctly,
                                 # matching how it behaves when run directly
        check=True,
    )


if __name__ == "__main__":
    main()
