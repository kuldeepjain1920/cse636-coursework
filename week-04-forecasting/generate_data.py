import pandas as pd
import numpy as np

np.random.seed(42)
n_points = 2016  # 7 days at 5-minute intervals

timestamps = pd.date_range(start="2025-10-01", periods=n_points, freq="5min")

t = np.arange(n_points)
daily_cycle = 20 * np.sin(2 * np.pi * t / (24 * 12))
weekly_cycle = 10 * np.sin(2 * np.pi * t / (7 * 24 * 12))
noise = np.random.normal(0, 3, n_points)
trend = 0.005 * t

cpu = np.clip(30 + daily_cycle + weekly_cycle + noise + trend, 5, 95)
memory = np.clip(45 + 0.5 * daily_cycle + noise * 0.5, 20, 90)

df_sim = pd.DataFrame({"ds": timestamps, "cpu": cpu, "memory": memory})
df_sim.to_csv("synthetic_metrics.csv", index=False)
print("Generated synthetic_metrics.csv with", len(df_sim), "rows")
