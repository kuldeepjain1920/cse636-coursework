# RCA Report — INC-002

**Probable cause:** CPU saturation likely driving latency degradation

## Evidence
- CPU peaked at 91.56% during the incident window
- p99 latency peaked at 3661.8ms
- 16 log lines matched the incident window

## Preventive measures
- Add autoscaling trigger on sustained CPU > 75%
- Alert on p99 latency > 3x rolling baseline

**Confidence:** low (simulated response — no LLM call made)