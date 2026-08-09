"""
rca_agent.py
------------
The agentic core. Given one Incident (from alert_grouper.py), this:
  1. Calls tool #1 (get_metrics_window) for metric context.
  2. Calls tool #2 (get_logs_window) for log context.
  3. Synthesizes an RCA from both, using simple threshold logic since
     no API key is set — same honest-simulator pattern as Lab Part B.
  4. Wraps every step in an OTel span via telemetry.py.
  5. Writes the report to output/rca_report.md.
"""

import os

import pandas as pd

from telemetry import init_tracing, traced_llm_call, traced_tool_call


def get_metrics_window(metrics_df: pd.DataFrame, start_time, end_time, pad_minutes: int = 10) -> dict:
    """Tool #1. Padded a few minutes on each side so the agent can see
    the lead-up to the spike, not just the spike itself."""
    window = metrics_df[
        (metrics_df["timestamp"] >= start_time - pd.Timedelta(minutes=pad_minutes)) &
        (metrics_df["timestamp"] <= end_time + pd.Timedelta(minutes=pad_minutes))
    ]
    return {
        "cpu_max": round(window["cpu_pct"].max(), 2),
        "latency_max": round(window["latency_p99_ms"].max(), 1),
        "error_rate_max": round(window["error_rate"].max(), 4),
    }


def get_logs_window(log_lines: list[str], start_time, end_time) -> list[str]:
    """Tool #2. Naive timestamp-prefix match — fine for your own
    logs_sample.txt format, swap for real parsing if yours differs."""
    start_str = start_time.strftime("%Y-%m-%d %H:%M")
    end_str = end_time.strftime("%Y-%m-%d %H:%M")
    return [line for line in log_lines if start_str <= line[:16] <= end_str]


def synthesize_rca(tracer, incident, metrics_summary: dict, matched_logs: list[str]) -> dict:
    """The 'AI call' step. Simple threshold logic here since no
    ANTHROPIC_API_KEY is set — be upfront about this in your reflection."""
    prompt_len_estimate = 200 + len(str(metrics_summary)) + sum(len(l) for l in matched_logs)

    with traced_llm_call(tracer, model="claude-sonnet-5", input_text="x" * prompt_len_estimate) as span_ctx:
        cpu_max = metrics_summary["cpu_max"]
        probable_cause = (
            "CPU saturation likely driving latency degradation"
            if cpu_max > 80 else
            "Latency spike without matching CPU saturation — check downstream dependency"
        )
        rca = {
            "probable_cause": probable_cause,
            "evidence": [
                f"CPU peaked at {cpu_max}% during the incident window",
                f"p99 latency peaked at {metrics_summary['latency_max']}ms",
                f"{len(matched_logs)} log lines matched the incident window",
            ],
            "preventive_measures": [
                "Add autoscaling trigger on sustained CPU > 75%",
                "Alert on p99 latency > 3x rolling baseline",
            ],
            "confidence": "low (simulated response — no LLM call made)",
        }
        span_ctx["input_tokens"] = prompt_len_estimate // 4
        span_ctx["output_tokens"] = len(str(rca)) // 4

    return rca


def write_rca_report(rca: dict, incident_id: str, out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    lines = [
        f"# RCA Report — {incident_id}",
        "",
        f"**Probable cause:** {rca['probable_cause']}",
        "",
        "## Evidence",
        *[f"- {e}" for e in rca["evidence"]],
        "",
        "## Preventive measures",
        *[f"- {m}" for m in rca["preventive_measures"]],
        "",
        f"**Confidence:** {rca['confidence']}",
    ]
    with open(out_path, "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    from anomaly_detector import generate_synthetic_metrics, fit_detector
    from alert_grouper import group_alerts

    tracer = init_tracing(service_name="week5-rca-agent", export_path="../output/spans_sample.json")

    df = generate_synthetic_metrics()
    result = fit_detector(df, contamination=0.04)
    incidents = group_alerts(result)

    # Placeholder — replace with your own real logs_sample.txt content.
    ##log_lines = [
    ##    f"{ts.strftime('%Y-%m-%d %H:%M')} ERROR db connection pool exhausted"
    ##    for ts in pd.date_range("2025-10-01 11:20", periods=16, freq="1min")
    ##]
    with open("../data/logs_sample.txt") as f:
        log_lines = f.read().splitlines()

    for incident in incidents:
        with traced_tool_call(tracer, tool_name="get_metrics_window", args={"incident_id": incident.incident_id}):
            metrics_summary = get_metrics_window(result, incident.start_time, incident.end_time)

        with traced_tool_call(tracer, tool_name="get_logs_window", args={"incident_id": incident.incident_id}):
            matched_logs = get_logs_window(log_lines, incident.start_time, incident.end_time)

        rca = synthesize_rca(tracer, incident, metrics_summary, matched_logs)
        write_rca_report(rca, incident.incident_id, out_path=f"../output/rca_report_{incident.incident_id}.md")
        print(f"Wrote RCA for {incident.incident_id}: {rca['probable_cause']}")
