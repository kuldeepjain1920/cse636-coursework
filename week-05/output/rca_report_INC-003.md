# RCA Report — INC-003

**Probable cause:** Latency spike without matching CPU saturation — check downstream dependency

## Evidence
- CPU peaked at 43.64% during the incident window
- p99 latency peaked at 186.7ms
- 0 log lines matched the incident window

## Preventive measures
- Add autoscaling trigger on sustained CPU > 75%
- Alert on p99 latency > 3x rolling baseline

**Confidence:** low (simulated response — no LLM call made)