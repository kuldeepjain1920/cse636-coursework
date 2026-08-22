# alert_grouper.py
# Stage 4 Phase 6: standalone copy of Week 5's alert_grouper.py, logic
# unchanged -- groups anomaly_detector.py's flagged rows into contiguous
# Incident objects using a time-gap rule, so nearby-but-not-perfectly-
# contiguous flagged points (real telemetry is noisy) are treated as one
# incident rather than many.

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Incident:
    """One grouped incident -- what the RCA agent treats as a single
    investigation target."""
    incident_id: str
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    point_count: int
    peak_metrics: dict = field(default_factory=dict)


def group_alerts(df: pd.DataFrame, max_gap_minutes: int = 5) -> list[Incident]:
    """
    Groups flagged rows into incidents using a time-gap rule: two flagged
    points belong to the same incident if they're within max_gap_minutes
    of each other. Real telemetry is noisy -- a detector might flag one
    point, miss the next, flag again -- so a hard "must be perfectly
    contiguous" rule would wrongly split that into two incidents.
    """
    flagged = df[df["is_anomaly"]].sort_values("timestamp")
    if flagged.empty:
        return []

    incidents: list[Incident] = []
    current_rows = [flagged.iloc[0]]

    def close_incident(rows, idx):
        block = pd.DataFrame(rows)
        return Incident(
            incident_id=f"INC-{idx:03d}",
            start_time=block["timestamp"].min(),
            end_time=block["timestamp"].max(),
            point_count=len(block),
            # Peak values give the RCA step something concrete to cite
            # ("CPU peaked at 87%") instead of a vague "there was an anomaly".
            peak_metrics={
                col: round(float(block[col].max()), 3)
                for col in ("cpu_pct", "error_rate", "latency_p99_ms")
                if col in block.columns
            },
        )

    idx = 1
    for _, row in flagged.iloc[1:].iterrows():
        gap = (row["timestamp"] - current_rows[-1]["timestamp"]).total_seconds() / 60
        if gap <= max_gap_minutes:
            current_rows.append(row)
        else:
            incidents.append(close_incident(current_rows, idx))
            idx += 1
            current_rows = [row]

    incidents.append(close_incident(current_rows, idx))
    return incidents


if __name__ == "__main__":
    # Smoke test against real Prometheus data, not synthetic
    from anomaly_detector import fetch_real_metrics, fit_detector

    df = fetch_real_metrics(minutes=30)
    result = fit_detector(df, contamination=0.04)
    incidents = group_alerts(result)

    if not incidents:
        print("No anomalies detected in the queried window.")
    for inc in incidents:
        print(f"{inc.incident_id}: {inc.start_time} -> {inc.end_time} "
              f"({inc.point_count} points) peaks={inc.peak_metrics}")
