# scaling.py
import math
import pandas as pd

def recommend_replicas(forecast_df, current_replicas, target_cpu_pct=60,
                       horizon_minutes=30, min_replicas=2, max_replicas=50):
    now = pd.Timestamp.now()
    cutoff = now + pd.Timedelta(minutes=horizon_minutes)

    upcoming = forecast_df[(forecast_df["ds"] > now) & (forecast_df["ds"] <= cutoff)]

    if upcoming.empty:
        print("No future forecast points found. Using last known forecast.")
        upcoming = forecast_df.tail(horizon_minutes // 5)

    max_cpu = upcoming["yhat_upper"].max()
    recommended = math.ceil(current_replicas * max_cpu / target_cpu_pct)
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
