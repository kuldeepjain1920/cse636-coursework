# explore.py
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("synthetic_metrics.csv", parse_dates=["ds"])
print(df.describe())

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 6), sharex=True)
ax1.plot(df["ds"], df["cpu"], linewidth=0.8, color="steelblue")
ax1.set_ylabel("CPU %")
ax1.set_title("CPU Utilization")
ax1.axhline(70, color="orange", linestyle="--", alpha=0.5, label="Scale-up threshold")
ax1.legend()

ax2.plot(df["ds"], df["memory"], linewidth=0.8, color="coral")
ax2.set_ylabel("Memory %")
ax2.set_title("Memory Utilization")
plt.tight_layout()
plt.savefig("metrics_overview.png", dpi=120)
plt.show()

print("\nMissing values:")
print(df.isnull().sum())
