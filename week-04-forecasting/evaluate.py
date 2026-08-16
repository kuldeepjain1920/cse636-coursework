from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
import matplotlib.pyplot as plt

test_forecast = forecast[forecast["ds"].isin(test["ds"])]
actual = test["y"].values
predicted = test_forecast["yhat"].values

mae = mean_absolute_error(actual, predicted)
mape = mean_absolute_percentage_error(actual, predicted) * 100

print(f"Evaluation on held-out 24-hour test set:")
print(f"  MAE:  {mae:.2f}% CPU")
print(f"  MAPE: {mape:.1f}%")

fig, ax = plt.subplots(figsize=(14, 4))
ax.plot(test["ds"], actual, label="Actual", color="steelblue")
ax.plot(test_forecast["ds"], predicted, label="Predicted", color="orange", linestyle="--")
ax.fill_between(test_forecast["ds"], test_forecast["yhat_lower"], test_forecast["yhat_upper"],
                alpha=0.2, color="orange", label="80% CI")
ax.axhline(70, color="red", linestyle=":", alpha=0.5, label="Scale-up threshold")
ax.set_title("CPU Forecast vs. Actual (Test Period)")
ax.legend()
plt.savefig("cpu_eval.png", dpi=120)
plt.show()
