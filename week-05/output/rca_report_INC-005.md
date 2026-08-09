# RCA Report — INC-005

**Probable cause:** Latency spike without matching CPU saturation — check downstream dependency

## Evidence
- CPU peaked at 46.64% during the incident window
- p99 latency peaked at 179.5ms
- 0 log lines matched the incident window

## Preventive measures
- Add autoscaling trigger on sustained CPU > 75%
- Alert on p99 latency > 3x rolling baseline

**Confidence:** low (simulated response — no LLM call made)