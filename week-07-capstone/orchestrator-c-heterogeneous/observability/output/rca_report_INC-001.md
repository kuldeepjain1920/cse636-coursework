# RCA Report -- INC-001

**Window:** 2026-08-22 17:44:59.956000090 to 2026-08-22 17:59:14.956000090
**Points flagged:** 5
**Peak metrics:** {'cpu_pct': 103.8, 'error_rate': 1.0, 'latency_p99_ms': 993.125}

**Probable cause:** A CPU saturation event on order-svc caused request queuing and thread starvation, driving error rates to 100% and p99 latency near the 1-second threshold over a ~14-minute window

## Evidence
- CPU utilization reached 103.8%, exceeding physical capacity and indicating the process was consistently runnable with no idle headroom, consistent with a tight compute loop, GC storm, or sudden traffic spike
- Error rate hit 1.0 (100%) during the incident window, meaning every request failed — a pattern consistent with a thread pool or connection pool exhausted by CPU starvation rather than a partial downstream degradation
- p99 latency of 993.125ms is near a likely 1-second timeout boundary, suggesting requests were queuing behind CPU-bound work until they hit a deadline and were rejected or timed out
- 5 anomalous data points flagged across an 855-second window indicates the degradation was sustained and not a transient spike, pointing to a resource leak, runaway process, or prolonged traffic overload rather than a momentary burst
- The combination of >100% CPU with simultaneous 100% error rate and high latency rules out a network or downstream-only failure and centers the fault on the order-svc process itself

**Confidence:** high