# Week 4 Lab Notes — Time-Series Forecasting for Autoscaling

Kuldeep Jain | CSE636 — DevOps with AI | July 2026

## 1. What MAPE did you achieve? Is it good enough for autoscaling decisions?

On the held-out 24-hour test set, the Prophet model achieved:

- **MAE: 2.44% CPU**
- **MAPE: 8.7%**

This is a strong result. An MAE of 2.44 percentage points is small relative to the ~10%–70% range
the synthetic CPU signal actually swings across, and an 8.7% MAPE is generally considered a good
forecast in most practical time-series contexts — under 10% MAPE is commonly treated as a solid,
usable result rather than a marginal one.

For autoscaling specifically, this level of accuracy is good enough to be genuinely useful, with one
caveat: the scaling decision in Step 5 deliberately uses `yhat_upper` (the top of the 80% confidence
interval), not the point forecast `yhat`, as a safety margin. Given the model's demonstrated MAE of
~2.4 points, that margin is doing real, necessary work — a bare point forecast without the upper-bound
buffer would occasionally under-provision on the model's less accurate predictions. In other words,
8.7% MAPE is good enough to trust *as an input* to a decision that also has its own explicit safety
margin — it would not be good enough to act on directly as a single point estimate with no buffer.

It is also worth being explicit that this MAPE was measured on a fully synthetic, well-behaved
dataset — clean daily and weekly seasonality, a smooth linear trend, and Gaussian noise with no genuine
anomalies. Real production CPU/memory metrics are typically messier, so this number likely represents
something closer to a best-case result for Prophet rather than a number to expect unconditionally on
live infrastructure data.

## 2. What patterns did the Prophet components plot reveal?

The components plot cleanly decomposed the single combined CPU series back into the three underlying
signals it was built from, without ever being told those components existed separately:

- **Trend**: a steady, near-linear rise from roughly 29% to 42% over the 7-day window — correctly
  recovering the small upward drift (`0.005` per 5-minute step) built into the synthetic data.
- **Weekly**: a smooth cycle with a trough around Monday/Tuesday and a peak around Thursday/Friday,
  swinging roughly ±10 percentage points — matching the synthetic weekly cycle's shape and amplitude
  closely.
- **Daily**: a clear cycle peaking in mid-morning (~06:51) and troughing in the early evening (~17:08),
  swinging roughly ±20 percentage points — again matching the synthetic daily cycle's amplitude
  precisely.

The fact that Prophet recovered all three components with approximately the correct amplitude and
phase, purely from a single noisy combined series, is a meaningful confirmation that the model is
fitting genuinely correctly rather than just producing a plausible-looking but coincidentally-close
forecast.

## 3. If actual CPU hit 95% during a spike the model did not forecast, what would happen with the
scaling recommendation? How would you make the system more robust?

**What would happen:** `recommend_replicas()` only ever looks at the *forecast* for the next 30
minutes — it never looks at the actual, currently-observed CPU value at all. If a real spike to 95%
occurred that the model had no prior signal for (e.g., a genuine one-off traffic surge unrelated to
the learned daily/weekly pattern), the forecast for that window would still reflect the model's normal
seasonal expectation, likely well under 95%. The function would then recommend a replica count sized
for the *expected* load, not the *actual* load — meaning the system would almost certainly
under-provision during exactly the moment it most needed to scale up. This is a real, structural
blind spot: a purely forecast-driven scaler has no mechanism to react to what is actually happening
right now, only to what it expected to happen.

**How to make this more robust:** the practical fix is to run predictive and reactive scaling
together, not as alternatives. A reactive layer (standard Kubernetes HPA, watching real-time CPU)
should remain active alongside the predictive layer, so that if actual load exceeds what was
forecast, the reactive controller can still trigger a scale-up based on ground truth, independent of
what the forecast predicted. The predictive layer's real value is in scaling up *ahead of* a
predictable pattern (e.g., a known daily peak) so pods are already warm when load arrives, not in
replacing the ability to react to a genuine surprise. A second, complementary improvement would be
combining this forecasting approach with the anomaly detection technique from Week 5 (Isolation
Forest on live metrics) — an anomaly detector could flag that current, real-time CPU has diverged
sharply from what was forecast, triggering an immediate reactive response rather than waiting for the
next forecast cycle to catch up.

## Note on a discrepancy found while completing this lab

The lab's own Step 3 code trains the model with `future = model.make_future_dataframe(periods=12,
freq="5min")` — extending the forecast only 1 hour beyond the training data. However, Step 4's
evaluation code assumes the forecast covers the *entire* 24-hour held-out test set (289 points). Using
`periods=12` as written produces a forecast that only overlaps the first hour of the test set, causing
`mean_absolute_error`/`mean_absolute_percentage_error` to fail with a sample-size mismatch (289 actual
values vs. 12 predicted values). The fix used here was `periods=len(test)`, which extends the forecast
far enough to cover the full test window. This is worth flagging as an inconsistency between the lab's
Step 3 and Step 4 code as written, not a result of an error made while following it.

## AI tool use disclosure

Claude (Anthropic) was used to help write and debug the Python scripts for this lab, and to help
draft this write-up. All code was run and its output independently verified (the components plot
patterns, the MAE/MAPE values, and the scaling recommendation were all checked against the actual
console output and plots, not assumed). The `periods=12` vs. test-set-length discrepancy above was
found through this verification process.

## Stretch Goal: Emitting the Forecast as a Prometheus Metric and Driving KEDA

Completed the full stretch goal end-to-end on Docker Desktop's local Kubernetes (v1.27.2), rather
than leaving it as a described-but-untested extension.

**Setup:**
- Installed Prometheus via the prometheus-community/prometheus Helm chart (a standalone install,
  not the full kube-prometheus-stack, to keep resource usage lighter on a single laptop cluster) into
  a dedicated monitoring namespace.
- Installed KEDA via the kedacore/keda Helm chart into its own keda namespace.
- Wrote emit_metric.py, adapting the lab's Step 6 snippet to train the Prophet model once at
  startup (reusing the same logic as forecast_and_eval.py) rather than retraining on every loop
  iteration, matching the lab's own guidance that retraining should happen periodically, not
  continuously. It serves a predicted_cpu_next_30m Gauge metric on :8000/metrics.

**Connecting the pieces:**
- Since emit_metric.py runs directly on the Mac while Prometheus runs inside the Kubernetes
  cluster, localhost inside a pod does not refer to the host Mac. Docker Desktop's Kubernetes
  provides host.docker.internal specifically for this -- used it as the scrape target
  (host.docker.internal:8000) in an extraScrapeConfigs Helm values override, applied via
  helm upgrade.
- Verified in Prometheus's own Targets UI (localhost:9090/targets, via kubectl port-forward) that
  the forecast-metric job showed state UP, successfully scraping the live metric.
- Created a minimal placeholder Deployment (forecast-demo-app, a bare nginx:alpine with 2
  replicas) purely so KEDA would have a real target to scale -- its actual function is irrelevant to
  the demo.
- Created a KEDA ScaledObject referencing the Prometheus server's in-cluster address
  (prometheus-server.monitoring.svc.cluster.local) and the predicted_cpu_next_30m metric, with a
  threshold of 60 (matching target_cpu_pct=60 in recommend_replicas(), so the two scaling
  mechanisms are conceptually consistent with each other).

**Result, verified via kubectl get scaledobject:**

NAME                    READY   ACTIVE   FALLBACK   TRIGGERS
forecast-scaledobject   True    True     False      prometheus

READY: True confirms KEDA successfully connected to Prometheus and parsed the query correctly.
ACTIVE: True confirms the live forecast value was, at the time of checking, at or above the
configured scaling threshold -- meaning this was a genuinely working, live decision being made from
the forecast, not just a correctly-configured but idle setup.

**What this adds beyond the core lab:** the core lab's Step 5 computes a scaling recommendation as a
one-off Python calculation you read from console output. The stretch goal demonstrates the same
underlying logic operating as an actual, continuously running control loop that a real Kubernetes
cluster would use -- Prometheus continuously scrapes the forecast, and KEDA continuously evaluates
whether to act on it, closing the loop from "the model made a prediction" to "the platform is
prepared to act on that prediction automatically."
