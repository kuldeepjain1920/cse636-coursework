# train.py
import pandas as pd
import matplotlib.pyplot as plt
from prophet import Prophet

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

future = model.make_future_dataframe(periods=12, freq="5min")
forecast = model.predict(future)

fig = model.plot(forecast)
plt.title("CPU Forecast")
plt.savefig("cpu_forecast.png", dpi=120)

fig2 = model.plot_components(forecast)
plt.savefig("cpu_forecast_components.png", dpi=120)
plt.show()
