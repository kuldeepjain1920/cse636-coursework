# Capstone Stage 5 — Auto-remediation

**Kuldeep Jain | CSE636 — DevOps for AI | August 2026**

Repository: `cse636-coursework`, branch `capstone-option-c`
Path: `week-07-capstone/orchestrator-c-heterogeneous/remediation/`

---

## 1. Overview

Stage 5 builds the "Auto-remediation" stage of the capstone pipeline: a
ReAct-style agent that triages an incident, proposes a remediation
action, and can only execute it after passing four layered blast-radius
controls, the last of which is a human approval gate.

**Foundation (full reasoning: `docs/decisions.md` D8):** built on
`week-06-assignment/src/react_agent.py`, not `week-06-lab/react_agent.py`
— the Assignment version already targeted the exact incident (`INC-002`,
`order-svc`, CPU saturation → scale-out) and already had 4 guardrails
layered (kill switch, rate limit, error-budget gate, approval) versus the
Lab's single gate. It was effectively already built with this
integration in mind, just never wired to real input.

---

## 2. What was added beyond Week 6

Two genuine gaps between the working Week 6 code and what the capstone
needed:

1. **Real incident input.** Week 6's `SERVICE_STATE` was a hardcoded
   dict. `remediation_agent.py` instead reads a real incident object from
   `handoffs/stage4-incident.json` (currently a hand-written `INC-002`
   fixture, matching the exact schema Stage 4 will eventually produce for
   real).
2. **ITSM ticket + stage handoff.** `create_itsm_ticket()` writes a
   structured local JSON record (a stand-in for a real PagerDuty/
   ServiceNow API call) regardless of outcome. `write_stage5_handoff()`
   writes `handoffs/stage5-output.json` — outcome, ticket ID, and the
   agent's own postmortem summary — closing the loop back toward Stage 4.

---

## 3. The blast-radius gate chain

When the agent requests `execute_scale`, four checks run in order,
**before** anything actually executes:

1. **Kill switch** (`AUTONOMY_KILL_SWITCH` env var) — a global,
   out-of-band override, entirely outside the model's own awareness. If
   off, refuses immediately — no approval prompt is even reached.
2. **Rate limit** — refuses if this service was scaled within the last 10
   minutes.
3. **Error-budget gate** — refuses if `error_budget_remaining ≤ 0.10`.
4. **Human approval** — only if all three automated checks pass does the
   agent pause and wait for an explicit `y`/`N` at the terminal.

---

## 4. Verified outcome paths — all three, real, separately committed

| Outcome | What happened | Commit |
|---|---|---|
| `remediated` | Full happy path: agent gathered metrics, ran a dry run, requested execution, approved by "Kuldeep Jain," scaled 4→7 replicas | `3f5364b` |
| `escalated_declined` | Same path up to the approval prompt, operator typed `N` — correctly declined, no state change, ticket still created | `baac52c` |
| `escalated_kill_switch` | `AUTONOMY_KILL_SWITCH=off` blocked the action *before* the approval prompt ever appeared. The agent's own postmortem correctly recognized this as *"a system-enforced gate, not a tooling failure"* rather than an error to retry | `be3f793` |

**Why each path is a separate commit:** `stage5-output.json` is
overwritten (not appended) on every run — committing each outcome
separately preserves a clean, inspectable git-history record of all three
paths, rather than only the last one run before committing.
(`docs/decisions.md` D10.)

**Notable finding for the report:** in the same build session, this
agent both *over-scoped* on a task it judged unambiguously helpful
(Stage 2's IaC lab — an unprompted `terraform apply` attempt) and
*correctly resisted* repeated, escalating, authority-asserting pressure
on a task it judged potentially harmful (the IaC lab's prompt-injection
demo). The kill-switch behavior here is a third data point in the same
vein: given a hard, out-of-band gate, the agent respected it cleanly and
reasoned about it correctly rather than treating it as an error.

---

## 5. Repository state

- Branch: `capstone-option-c`
- Committed: `remediation_agent.py`, `handoffs/stage4-incident.json` (test
  fixture), `handoffs/stage5-output.json` (reflects the most recently run
  outcome), three ITSM tickets (`TICKET-4bcc5234.json`,
  `TICKET-f80d6a13.json`, `TICKET-d0bd48bc.json`, one per outcome path)
- Commits: `3f5364b`, `baac52c`, `be3f793`
- Not yet wired: this stage still runs standalone against the hand-written
  fixture. Chaining it to receive Stage 4's real output via `subprocess`
  is part of Stage 4's remaining production-shaped work (see
  `docs/RUNBOOK.md` §5).
