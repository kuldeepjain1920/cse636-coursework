# forecast_and_eval.py
import pandas as pd
import matplotlib.pyplot as plt
from prophet import Prophet
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

# --- Step 3: Train (same as before) ---
df = pd.read_csv("synthetic_metrics.csv", parse_dates=["ds"])
cpu_df = df[["ds", "cpu"]].rename(columns={"cpu": "y"})

split_time = cpu_df["ds"].max() - pd.Timedelta("24h")
train = cpu_df[cpu_df["ds"] < split_time].copy()
test = cpu_df[cpu_df["ds"] >= split_time].copy()

print(f"Training on {len(train)} points, evaluating on {len(test)} points")

model = Prophet(
    daily_seasonality=True,
    weekly_seasonality=True,
    yearly_seasonality=False,
    interval_width=0.80
)
model.fit(train)

##future = model.make_future_dataframe(periods=12, freq="5min")
##forecast = model.predict(future)

# Instead of periods=12, use enough periods to cover the entire held-out
# test window (24 hours = 288 intervals at 5 minutes each), not just 1 hour
future = model.make_future_dataframe(periods=len(test), freq="5min")
forecast = model.predict(future)

fig = model.plot(forecast)
plt.title("CPU Forecast")
plt.savefig("cpu_forecast.png", dpi=120)

fig2 = model.plot_components(forecast)
plt.savefig("cpu_forecast_components.png", dpi=120)

# --- Step 4: Evaluate (new) ---
# Filter the full forecast down to just the rows matching the held-out
# test set's timestamps, so actual vs. predicted compare the same dates
test_forecast = forecast[forecast["ds"].isin(test["ds"])]
actual = test["y"].values
predicted = test_forecast["yhat"].values

# MAE: average absolute error, in the same units as the data (CPU points)
mae = mean_absolute_error(actual, predicted)
# MAPE: same idea, but as a percentage of the actual value (scale-independent)
mape = mean_absolute_percentage_error(actual, predicted) * 100

print(f"\nEvaluation on held-out 24-hour test set:")
print(f"  MAE:  {mae:.2f}% CPU")
print(f"  MAPE: {mape:.1f}%")

# Visualize actual vs. predicted specifically on the test period, with
# the confidence band and the 70% scale-up threshold for reference
fig3, ax = plt.subplots(figsize=(14, 4))
ax.plot(test["ds"], actual, label="Actual", color="steelblue")
ax.plot(test_forecast["ds"], predicted, label="Predicted", color="orange", linestyle="--")
ax.fill_between(test_forecast["ds"], test_forecast["yhat_lower"], test_forecast["yhat_upper"],
                alpha=0.2, color="orange", label="80% CI")
ax.axhline(70, color="red", linestyle=":", alpha=0.5, label="Scale-up threshold")
ax.set_title("CPU Forecast vs. Actual (Test Period)")
ax.legend()
plt.savefig("cpu_eval.png", dpi=120)

plt.show()

# --- Step 5: Translate forecast into a scaling decision ---
import math

def recommend_replicas(forecast_df, current_replicas, target_cpu_pct=60,
                       horizon_minutes=30, min_replicas=2, max_replicas=50):
    """
    Given a Prophet forecast DataFrame, recommend a replica count
    to handle the maximum predicted CPU load within the next horizon_minutes.
    """
    # "Now" anchored to the last known data point, not the real-world
    # current time -- our synthetic data is dated Oct 2025, so
    # pd.Timestamp.now() would find nothing "upcoming" in the dataset
    now = forecast_df["ds"].max() - pd.Timedelta(minutes=horizon_minutes + 5)
    cutoff = now + pd.Timedelta(minutes=horizon_minutes)

    upcoming = forecast_df[(forecast_df["ds"] > now) & (forecast_df["ds"] <= cutoff)]

    if upcoming.empty:
        print("No future forecast points found. Using last known forecast.")
        upcoming = forecast_df.tail(horizon_minutes // 5)

    # Conservative: use the UPPER confidence bound, not the point estimate,
    # so under-provisioning (worse for users) is less likely
    max_cpu = upcoming["yhat_upper"].max()

    # ceil because you can't run a fractional replica; rounding down
    # would under-provision
    recommended = math.ceil(current_replicas * max_cpu / target_cpu_pct)
    # Clamp so a wild forecast can't scale to zero or to thousands of pods
    recommended = max(min_replicas, min(max_replicas, recommended))

    return recommended, max_cpu


current = 4
recommended, max_cpu_pred = recommend_replicas(forecast, current_replicas=current)

print(f"\n--- Autoscaling Recommendation ---")
print(f"Current replicas:           {current}")
print(f"Max predicted CPU (30 min): {max_cpu_pred:.1f}% (upper 80% CI)")
print(f"Target CPU per replica:     60%")
print(f"Recommended replicas:       {recommended}")

if recommended > current:
    print(f"DECISION: Scale UP by {recommended - current} replica(s)")
elif recommended < current:
    print(f"DECISION: Scale DOWN by {current - recommended} replica(s)")
else:
    print("DECISION: No change")
