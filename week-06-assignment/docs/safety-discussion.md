# Week 6 Assignment — Safety Discussion

## What failure modes exist in this agent implementation?

**1. Blast-radius state does not survive a process restart.** The rate-limit
control (`_last_scale_action`) lives in a plain in-memory Python dict inside
`react_agent.py`. Discovered directly while testing: two separate
`python3 react_agent.py` invocations, run back-to-back well inside the
10-minute cooldown window, both reached the approval gate and both executed
a scale-out — the second run's rate-limit check found an empty dict, since a
fresh process has no memory of the first run. An agent restarting after a
crash, a redeploy, or an orchestrator respawn is a normal event, not a rare
one — so a rate limit that resets on restart provides close to zero real
protection against a flapping or repeatedly-restarted agent.

**2. Hallucinated or malformed tool arguments.** Nothing validates that a
`service` name passed to a tool call actually exists before
`SERVICE_STATE.get(service, {})` silently returns an empty dict — a typo'd
name fails soft (all metrics come back `None`) instead of loudly, which
could let the agent reason its way into a confident but fabricated triage.

**3. A stuck approval prompt blocks the loop indefinitely.** `input()` has
no timeout. If the human never responds, the incident is neither
remediated nor escalated — it just hangs, which is itself an availability
risk for an incident actively burning error budget.

**4. Prompt-only rules are advisory, not enforcement.** The model could in
principle ignore the system prompt's "escalate if near max replicas or low
budget" instruction and call `execute_scale` anyway. The four blast-radius
controls in code are the real enforcement; prompt rules only help the model
reach the right decision faster.

## How would the blast-radius controls limit damage?

- **Dry-run** catches a wrong target replica count before it's ever
  proposed for real.
- **Approval gate** stops a wrong *decision*, even when the math is right —
  a human may know context (e.g. a maintenance window) the agent doesn't.
- **Error-budget gate** stops further autonomous action once things are
  bad enough that a human should be driving.
- **Kill switch** limits damage regardless of whether the above worked —
  verified directly in testing: with `AUTONOMY_KILL_SWITCH=off`,
  `execute_scale` was refused *before* the approval prompt even rendered.
- **Rate limit**, as built, only protects within a single process's
  uptime (failure mode #1) — real protection against restart-driven
  flapping needs this state moved somewhere durable, e.g. Redis or SQLite.

## How would you test this before deploying against a real system?

- **Replay all five Week 5 incidents** (INC-001–005) against the agent to
  confirm it reaches the RCA-consistent decision each time, not just for
  INC-002.
- **Unit-test `runbook.yaml`'s decision logic directly**, independent of
  the LLM — the `auto_remediate_if`/`escalate_if` conditions are plain
  booleans and don't need a model call to verify.
- **Chaos-test the approval-timeout path**, since it's currently
  unhandled: simulate an operator who never responds and confirm the
  system degrades safely rather than hanging indefinitely.
- **Restart the agent mid-cooldown** as a standing test, not a one-off —
  this is exactly the test that surfaced failure mode #1, and it's
  invisible unless you specifically test for a restart.

## What additional guardrails before production?

- **Persistent state for every blast-radius control**, not just the rate
  limit — the kill switch is also process-scoped today (an env var); a
  real deployment wants this in a config service so it survives restarts.
- **A timeout + auto-escalation path** on the approval gate.
- **Scoped, audited credentials** for whatever `execute_scale` actually
  calls in production (e.g. `kubectl scale` with RBAC limited to that one
  Deployment) — least privilege at the infrastructure layer, not just the
  MCP tool layer.
- **Structured, persisted audit logging** of every Thought and tool call,
  not just console output.
