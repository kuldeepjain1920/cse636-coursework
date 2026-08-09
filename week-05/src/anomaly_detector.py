"""
anomaly_detector.py
--------------------
Reuses the Lab Part A logic, packaged as importable functions instead of
notebook cells so alert_grouper.py and rca_agent.py can both call it
without copy-pasting.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# The 3 metrics IsolationForest looks at. Defined once here so both
# fit_detector() and any future caller reference the same column list —
# avoids a typo'd column name silently dropping a feature somewhere.
FEATURE_COLUMNS = ["cpu_pct", "error_rate", "latency_p99_ms"]


def generate_synthetic_metrics(n: int = 500, seed: int = 42,
                                anomaly_start: int = 200, anomaly_end: int = 216) -> pd.DataFrame:
    """Same generator as Lab Part A Step 1 — deterministic, so anyone
    running this file gets the same data without needing the notebook."""
    # Fixed seed = same "random" numbers every run. Without this, every
    # teammate (or every rerun) would get a different dataset, making
    # results impossible to compare or reproduce.
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range("2025-10-01 08:00", periods=n, freq="1min")

    # Baseline "healthy service" numbers — normal() and exponential()
    # just mean "realistic noisy values centered around a typical reading."
    cpu = rng.normal(35, 5, n)
    error_rate = rng.exponential(0.002, n)
    latency_p99 = rng.normal(150, 20, n)

    # Overwrite one contiguous block (minutes 200-215) with much higher
    # values — this is the fake "incident" the detector is supposed to find.
    # Contiguous on purpose, not scattered, so alert_grouper.py later has
    # something meaningful to group into one incident.
    cpu[anomaly_start:anomaly_end] = rng.normal(85, 5, anomaly_end - anomaly_start)
    error_rate[anomaly_start:anomaly_end] = rng.uniform(0.05, 0.15, anomaly_end - anomaly_start)
    latency_p99[anomaly_start:anomaly_end] = rng.normal(3500, 200, anomaly_end - anomaly_start)

    return pd.DataFrame({
        "timestamp": timestamps,
        # np.clip keeps values in a physically sensible range — e.g. CPU
        # can't go below 0% or above 100%, even if the random noise
        # generated a number outside that range.
        "cpu_pct": np.clip(cpu, 0, 100),
        "error_rate": np.clip(error_rate, 0, 1),
        "latency_p99_ms": np.clip(latency_p99, 0, None),  # latency can't be negative
    })


def fit_detector(df: pd.DataFrame, contamination: float = 0.04, random_state: int = 42) -> pd.DataFrame:
    """Fits IsolationForest (your best-performing setting from Part A)
    and returns df with an is_anomaly column added."""
    features = df[FEATURE_COLUMNS]
    # StandardScaler puts all 3 metrics on the same scale (mean 0, std 1)
    # before comparing them. Without this, latency's raw numbers (hundreds/
    # thousands) would dominate the distance calculations over error_rate's
    # tiny raw numbers (0 to 1), even though both matter equally.
    X = StandardScaler().fit_transform(features)

    # contamination=0.04 was the best setting found in Part A's sweep —
    # it's close to the true anomaly rate (16/500 = 0.032), which is why
    # it balances precision and recall well. n_estimators=200 is just the
    # number of random trees averaged together for a stable score.
    model = IsolationForest(n_estimators=200, contamination=contamination, random_state=random_state)
    model.fit(X)

    out = df.copy()  # don't mutate the caller's original dataframe
    # model.predict() returns -1 for anomalies, 1 for normal points —
    # convert that to a plain True/False column that's easier to read
    # and filter on elsewhere (e.g. df[df["is_anomaly"]] in alert_grouper.py).
    out["is_anomaly"] = (model.predict(X) == -1)
    return out


if __name__ == "__main__":
    # Only runs when this file is executed directly (python3 anomaly_detector.py),
    # not when it's imported by alert_grouper.py or rca_agent.py — a quick
    # smoke test to confirm the file still works on its own.
    df = generate_synthetic_metrics()
    result = fit_detector(df, contamination=0.04)
    print(f"Anomalies detected: {result['is_anomaly'].sum()} of {len(result)} points")
