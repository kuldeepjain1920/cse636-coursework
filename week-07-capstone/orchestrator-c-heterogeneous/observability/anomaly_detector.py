# observability/anomaly_detector.py
# Stage 4 Phase 4: standalone copy of Week 5's anomaly_detector.py, with
# generate_synthetic_metrics() replaced by fetch_real_metrics(), which
# pulls real order-svc telemetry from Prometheus (Phases 1-3) instead of
# generating fake data. fit_detector() and FEATURE_COLUMNS are copied
# verbatim, unchanged, from week-05/src/anomaly_detector.py -- only the
# data SOURCE changes, not the detection logic (see decisions.md D20).

import time
import requests
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

FEATURE_COLUMNS = ["cpu_pct", "error_rate", "latency_p99_ms"]

PROMETHEUS_URL = "http://localhost:9090"  # requires: kubectl port-forward svc/prometheus-server 9090:80 -n monitoring


def fit_detector(df: pd.DataFrame, contamination: float = 0.04, random_state: int = 42) -> pd.DataFrame:
    """Unchanged from Week 5 -- same IsolationForest logic, same best
    contamination setting found in Part A's sweep."""
    features = df[FEATURE_COLUMNS]
    X = StandardScaler().fit_transform(features)
    model = IsolationForest(n_estimators=200, contamination=contamination, random_state=random_state)
    model.fit(X)
    out = df.copy()
    out["is_anomaly"] = (model.predict(X) == -1)
    return out


def _query_range(promql: str, start: float, end: float, step: str = "15s") -> list[tuple[float, float]]:
    """Calls Prometheus's query_range API for one PromQL expression.
    Returns (unix_timestamp, value) pairs."""
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params={
        "query": promql, "start": start, "end": end, "step": step,
    })
    resp.raise_for_status()
    result = resp.json()["data"]["result"]
    if not result:
        return []  # no data for this window -- e.g. no traffic hit order-svc yet
    return [(float(ts), float(val)) for ts, val in result[0]["values"]]


def fetch_real_metrics(minutes: int = 30) -> pd.DataFrame:
    """Replaces Week 5's generate_synthetic_metrics(): pulls the last N
    minutes of REAL order-svc telemetry from Prometheus. Returns the same
    column shape fit_detector() already expects, so it needs zero changes."""
    end = time.time()
    start = end - (minutes * 60)

    cpu = _query_range("order_svc_cpu_percent", start, end)
    error_rate = _query_range(
        'rate(order_svc_requests_total{status="500"}[5m]) '
        '/ rate(order_svc_requests_total[5m])',
        start, end,
    )
    latency_p99 = _query_range(
        "histogram_quantile(0.99, rate(order_svc_request_duration_seconds_bucket[5m])) * 1000",
        start, end,
    )

    if not cpu:
        raise ValueError(
            "No data returned from Prometheus -- confirm 'kubectl port-forward "
            "svc/prometheus-server 9090:80 -n monitoring' is running, and that "
            "order-svc has received real traffic in the queried window."
        )

    # error_rate/latency may have fewer points than cpu if rate() couldn't
    # compute early in the window (needs prior data) -- fillna 0.0 is a
    # reasonable default: no requests yet means no errors, no latency.
    df = pd.DataFrame({
        "timestamp": pd.to_datetime([ts for ts, _ in cpu], unit="s"),
        "cpu_pct": [val for _, val in cpu],
        "error_rate": pd.Series([val for _, val in error_rate]).reindex(range(len(cpu)), fill_value=0.0),
        "latency_p99_ms": pd.Series([val for _, val in latency_p99]).reindex(range(len(cpu)), fill_value=0.0),
    }).fillna(0.0)  # catches literal NaN Prometheus returns for early points where rate() lacked enough history
    return df


if __name__ == "__main__":
    df = fetch_real_metrics(minutes=30)
    print(f"Fetched {len(df)} real data points from Prometheus")
    result = fit_detector(df, contamination=0.04)
    print(f"Anomalies detected: {result['is_anomaly'].sum()} of {len(result)} points")
