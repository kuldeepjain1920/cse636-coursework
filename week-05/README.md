# Week 5 — Anomaly Detection + Agentic RCA

## What this is

A small pipeline that detects anomalies in synthetic service metrics
(CPU, error rate, p99 latency), groups related anomalies into incidents,
and uses an agent with two tools (metrics + logs) to generate a
structured root-cause analysis report — with every step recorded as an
OpenTelemetry span.

## How to run it

```bash
cd src
python3 anomaly_detector.py   # sanity check: should print "20 of 500 points"
python3 alert_grouper.py      # sanity check: should print 5 incidents
python3 rca_agent.py          # runs the full pipeline, writes output/
```

Output lands in `../output/`: one `rca_report_INC-*.md` per incident,
plus `spans_sample.json` with the captured OTel spans.

## Key decisions

- **contamination=0.04 for IsolationForest** — tuned in the Lab by
  sweeping 0.01/0.04/0.10. 0.04 is closest to the true anomaly rate in
  this dataset (16/500 ≈ 0.032) and gave the best F1 (0.89), with
  perfect recall.
- **Time-gap rule for alert grouping, not LLM-based** — deterministic,
  free to run, and keeps LLM call volume proportional to incidents, not
  raw flagged points (16 flagged minutes become 1 incident to
  investigate, not 16 separate LLM calls).
- **Simulated RCA response, not a real API call** — no `ANTHROPIC_API_KEY`
  was set for this run. The synthesis step uses simple threshold logic
  (CPU > 80% → blame CPU saturation) instead of real model reasoning.
  Every generated report is honestly labeled `confidence: low (simulated
  response)` rather than presented as if it came from a real call.
- **Two tools, not one** — `get_metrics_window` and `get_logs_window`
  are separate spans so the trace shows time spent on each independently,
  rather than one opaque "did some stuff" block.

## Verified results

Running the pipeline correctly separated the one real incident (INC-002,
16 points, CPU peaked 91.56%, latency peaked 3661.8ms) from four
single-point false positives — INC-002 was correctly diagnosed as CPU
saturation, while the false positives correctly fell to the generic
"check downstream dependency" fallback.

- **DBSCAN comparison (Lab bonus)** — swept eps in [0.3, 0.5, 0.7, 0.9, 1.2] against
  the same standardized features. eps=0.5 gave a perfect detector
  (precision=1.00, recall=1.00, f1=1.00), actually beating IsolationForest's
  best F1 of 0.89. Also swept min_samples in [3,...,300] at eps=0.5 — the
  result is robust across min_samples=3 through 20, only degrading once
  min_samples exceeds ~20-100 (fewer normal points meet the density bar).
  IsolationForest remains the detector actually used in the pipeline
  (`src/anomaly_detector.py`) since its `contamination` parameter is more
  forgiving to a rough guess than DBSCAN's `eps`, which has a narrower
  "just right" zone — but DBSCAN's ceiling is genuinely higher on this
  dataset once tuned.
