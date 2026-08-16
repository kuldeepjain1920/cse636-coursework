"""
emit_metric.py -- Week 4 stretch goal: expose the Prophet forecast as a
Prometheus metric so KEDA can scale on it.

Trains the model ONCE at startup (reusing the same data/logic as
forecast_and_eval.py), then re-predicts and republishes the metric on a
loop -- matching the lab's own guidance to retrain periodically, not on
every single loop iteration.
"""
import math
import time

import pandas as pd
from prophet import Prophet
from prometheus_client import Gauge, start_http_server

# --- Train once at startup (same logic as forecast_and_eval.py Step 3) ---
df = pd.read_csv("synthetic_metrics.csv", parse_dates=["ds"])
cpu_df = df[["ds", "cpu"]].rename(columns={"cpu": "y"})

model = Prophet(
    daily_seasonality=True,
    weekly_seasonality=True,
    yearly_seasonality=False,
    interval_width=0.80,
)
model.fit(cpu_df)  # train on the FULL dataset here, not a train/test split --
                     # this script's job is live serving, not evaluation

def recommend_replicas(forecast_df, current_replicas, target_cpu_pct=60,
                        horizon_minutes=30, min_replicas=2, max_replicas=50):
    """Same scaling logic as Step 5 -- reused here so the emitted metric
    and the lab's own recommendation stay consistent with each other."""
    now = forecast_df["ds"].max() - pd.Timedelta(minutes=horizon_minutes + 5)
    cutoff = now + pd.Timedelta(minutes=horizon_minutes)
    upcoming = forecast_df[(forecast_df["ds"] > now) & (forecast_df["ds"] <= cutoff)]
    if upcoming.empty:
        upcoming = forecast_df.tail(horizon_minutes // 5)
    max_cpu = upcoming["yhat_upper"].max()
    recommended = math.ceil(current_replicas * max_cpu / target_cpu_pct)
    recommended = max(min_replicas, min(max_replicas, recommended))
    return recommended, max_cpu

# --- Start the Prometheus HTTP server on :8000/metrics ---
start_http_server(8000)

# A Gauge is a metric type that can go up or down (unlike a Counter, which
# only ever increases) -- appropriate here since predicted CPU can rise
# or fall between updates. The "service" label lets this same metric name
# be reused for multiple services later, each distinguished by its label.
predicted_cpu_gauge = Gauge(
    "predicted_cpu_next_30m",
    "Prophet-predicted max CPU % for next 30 minutes",
    ["service"]
)

print("Emitting Prometheus metrics on :8000/metrics ...")
while True:
    # Re-predict using the model already trained above -- NOT retraining
    # from scratch every loop, which would be wasteful and slow
    future = model.make_future_dataframe(periods=12, freq="5min")
    fresh_forecast = model.predict(future)
    _, max_pred = recommend_replicas(fresh_forecast, current_replicas=4)

    # .labels(service="my-app") selects/creates the specific label
    # combination this value applies to; .set() overwrites the gauge's
    # current value (as opposed to .inc()/.dec() which adjust it)
    predicted_cpu_gauge.labels(service="my-app").set(max_pred)
    print(f"Emitted predicted_cpu_next_30m = {max_pred:.1f}%")
    time.sleep(300)  # update every 5 minutes, matching the data's own granularity
