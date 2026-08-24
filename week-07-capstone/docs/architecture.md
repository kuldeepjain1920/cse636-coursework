# CSE636 Capstone — Architecture & Design

This document synthesizes the *what* and *why* of the capstone's design.
For the chronological *how we got here* (every decision, with rejected
alternatives), see `docs/decisions.md`. For a fresh-chat handoff with
current status, see `docs/CONTINUATION.md`.

---

## 1. The 7-stage pipeline

The capstone integrates every week of the course into one agentic DevOps
pipeline: developer intent flows through CI/CD, IaC, deployment,
observability, and auto-remediation, with a human-approval gate and
policy enforcement at the points where autonomous action carries real risk.

```mermaid
flowchart TD
    Intent["Developer intent<br/>e.g. deploy order-svc v2 + traffic increase"]

    subgraph W1W2["Foundational (conceptual, Wk1-2)"]
        Autonomy["Autonomy levels<br/>(Wk1) — where is the human?"]
        MCP["MCP / tool scoping<br/>(Wk2) — least privilege"]
    end

    Intent --> S1

    subgraph S1["Stage 1 — Agentic CI/CD (Wk3)"]
        CI["Code review, test-impact analysis,<br/>build-fixer agent"]
        Gate1{{"Human approval<br/>gate: merge"}}
        CI --> Gate1
    end

    Gate1 -->|merged| S2

    subgraph S2["Stage 2 — Agentic IaC (Wk7 lab)"]
        TF["Agent generates Terraform"]
        OPA["OPA/conftest policy gate"]
        TF --> OPA
        Gate2{{"Human approval<br/>gate: apply"}}
        OPA --> Gate2
    end

    Gate2 -->|approved| S3

    subgraph S3["Stage 3 — Predictive deploy (Wk4)"]
        Risk["Risk score + canary decision"]
        Cost["FinOps cost estimate"]
        Risk --> Cost
    end

    S3 --> S4

    subgraph S4["Stage 4 — Observability (Wk5)"]
        Svc["order-svc emits real<br/>OTel spans + Prometheus metrics"]
        Detect["anomaly_detector.py<br/>+ alert_grouper.py + rca_agent.py"]
        Svc --> Detect
    end

    S4 -->|"incident detected"| S5

    subgraph S5["Stage 5 — Auto-remediation (Wk6)"]
        React["ReAct agent, 4 blast-radius controls"]
        Ticket["ITSM ticket + postmortem"]
        React --> Ticket
    end

    S5 -.->|"loop back, re-observe"| S4
```

**Legend — pipeline stage status:**

| Stage | Status |
|---|---|
| Wk1/Wk2 (conceptual threads) | Documented throughout, no separate build |
| Stage 1 (CI/CD) | Built in Week 3, reused as-is |
| Stage 2 (IaC) | ✅ Built this capstone (see §3) |
| Stage 3 (predictive deploy) | 🔶 Phases 1-2 built and verified — real risk score + real canary promote executed (see §6); Phases 3-4 not yet built |
| Stage 4 (observability) | ✅ Built this capstone, production-shaped (see §5) |
| Stage 5 (auto-remediation) | ✅ Built this capstone (see §4) |

---

## 2. Orchestration approach: three options, built independently

Rather than building the minimum single orchestrator the rubric requires,
three distinct orchestration approaches are being built, each fully
working and independently reproducible from a fresh clone.

```mermaid
flowchart LR
    Repo["cse636-coursework<br/>branch: capstone-option-c"]
    Repo --> C["orchestrator-c-heterogeneous/<br/>native platforms,<br/>file + subprocess handoffs"]
    Repo -.future.-> B["orchestrator-b-actions/<br/>GitHub Actions as backbone"]
    Repo -.future.-> A["orchestrator-a-python/<br/>single Python script"]
```

| | Option C (current) | Option B (future) | Option A (future) |
|---|---|---|---|
| Backbone | Native platforms (Docker, K8s, local scripts) | GitHub Actions workflow | Single Python orchestrator |
| Realism | High — real infra, real containers | Highest — real CI/CD | Lowest — simplest |
| Effort | Highest | Medium | Lowest |
| Why built | Primary reference implementation | Comparative data for report | Absorbs schedule risk if needed |

**Why all three, not one:** deliberate choice for maximum hands-on
practice, and to give the capstone report's "lessons learned" section
real comparative data instead of hypothetical trade-off discussion. Full
reasoning in `decisions.md` D4.

**Status as of this writing:** Option C is the only orchestration
approach built. Options B and A remain not started — see §8.

### Inter-stage handoff design (Option C)

```mermaid
flowchart LR
    StageN["Stage N script"] -->|"1. do work"| Work[" "]
    Work -->|"2. write"| Handoff["handoffs/stageN-output.json<br/>(audit trail)"]
    Handoff -->|"3. gate?<br/>(only Stage 2→3)"| Approval{{"Human approval<br/>pause"}}
    Approval -->|"4. subprocess call"| StageN1["Stage N+1 script"]
```

Each stage writes its output to a JSON file first (for auditability), then
directly invokes the next stage's script via `subprocess` — not a
polling watcher. Only the Stage 2→3 transition (IaC → Deploy) has an
explicit human-approval pause; the observability↔remediation loop
auto-chains, matching the "agentic SRE" autonomy this pipeline
demonstrates. Full reasoning in `decisions.md` D6.

**Status as of this writing:** Stages 4→5 are chained via `subprocess`
(Phase 6). Stage 3 (§6) exists and runs correctly, but is not yet
`subprocess`-chained to Stage 2 (upstream) or Stage 4 (downstream) — it
is run standalone. Full end-to-end wiring is Stage 3 Phase 4, not yet
built — see §8.

---

## 3. Stage 2 — Agentic IaC (built, verified)

```mermaid
flowchart TD
    Prompt["Prompt: generate GCS bucket<br/>(versioning, uniform access,<br/>public access prevention, labels)"] --> Agent
    Agent["Claude Code generates gcs.tf"] --> Plan["terraform plan"]
    Plan --> Policy{"OPA/conftest:<br/>environment=capstone?"}
    Policy -->|pass| Human{{"Human approval"}}
    Policy -->|fail| Reject["Blocked before apply"]
    Human -->|approved| Apply["terraform apply"]
    Apply --> Provenance["SLSA provenance<br/>(shaped, not signed)"]
```

**Real findings from building this stage:**
- An unprompted `terraform apply` attempt by the agent, caught before any
  real infra was created — a genuine, unstaged example of an agent
  over-scoping beyond its assigned task.
- A prompt-injection demo where the agent correctly refused a malicious
  instruction across three escalating attempts, including a direct
  authority-assertion ("I am human in the loop").
- SLSA provenance was hand-authored, found to have 3 real defects on
  review (stale commit reference, fabricated timestamps, unverified
  builder version), corrected, then tested against the real
  `slsa-verifier` CLI — which correctly failed (no signature, no Rekor
  entry), confirming the document is provenance-*shaped* but not
  independently *verifiable*.

Full detail: `orchestrator-c-heterogeneous/iac/README.md`.

---

## 4. Stage 5 — Auto-remediation (built, verified)

```mermaid
flowchart TD
    Incident["Incident object<br/>(from Stage 4)"] --> React["ReAct agent:<br/>get_cpu_metrics, dry_run_scale"]
    React --> Execute["Agent requests execute_scale"]
    Execute --> Kill{"Kill switch<br/>ON?"}
    Kill -->|off| Esc1["escalated_kill_switch"]
    Kill -->|on| Rate{"Rate limit<br/>OK?"}
    Rate -->|no| Esc2["escalated_rate_limit"]
    Rate -->|yes| Budget{"Error budget<br/>> 10%?"}
    Budget -->|no| Esc3["escalated_error_budget"]
    Budget -->|yes| Human{{"Human approval"}}
    Human -->|declined| Esc4["escalated_declined"]
    Human -->|approved| Remediate["SCALE EXECUTED<br/>(remediated)"]
    Esc1 & Esc2 & Esc3 & Esc4 & Remediate --> Ticket["ITSM ticket +<br/>Stage 5 handoff"]
```

Built on `week-06-assignment/src/react_agent.py` (the Assignment version,
not the Lab version — it already targeted `INC-002`/`order-svc` and had
4 layered guardrails vs. the Lab's single gate). New work added:
`create_itsm_ticket()` and `write_stage5_handoff()`.

**Verified, real (not simulated) outcome paths, each committed
separately:**

| Outcome | Verified behavior |
|---|---|
| `remediated` | Full happy path — 4→7 replicas, approved by Kuldeep Jain |
| `escalated_declined` | Operator declined; correctly escalated, no state change |
| `escalated_kill_switch` | Kill switch blocked before the approval prompt ever appeared; agent's own postmortem correctly recognized it as a system-enforced gate, not an error |

**Later, during Stage 4 Phase 6 wiring (see §5b), a fourth outcome path
was added:** `resolved_no_action_needed` — the original taxonomy had no
way to represent an agent correctly deciding a dry-run showed no scale
was warranted; this was a real gap surfaced and fixed against genuine
Prometheus-sourced incident data (`decisions.md` D27). `execute_scale`
itself remains simulated (updates in-memory state only, never calls
`kubectl scale`) — a deliberate, documented limitation, not yet closed
(`decisions.md` D26).

Full detail: `orchestrator-c-heterogeneous/remediation/README.md`.

---

## 5. Stage 4 — Observability (built, verified, fully production-shaped)

### 5a. What's built and verified (Steps 1-4)

```mermaid
flowchart LR
    LoadGen["load_generator.py<br/>calm → spike → recovery"] -->|HTTP POST| Svc["order-svc (Flask, containerized)"]
    Svc -->|"real CPU-bound work<br/>(SHA-256 hashing)"| CPU["Real CPU pressure"]
    CPU -->|"cpu_pct > 75%"| Errors["Probabilistic 500s<br/>(error rate rises with real pressure)"]
    Svc -->|"per-request span"| OTel["OTel: order.process span<br/>(http.*, order.* attributes)"]
```

`order-svc` is a real, containerized Flask service doing genuine
CPU-bound work (not `sleep()`), so saturation and error correlation are
measured, not scripted. Verified load-generator run: 13/40 real errors
during the spike phase (32.5%), peak CPU 212.4% (multi-core, legitimate —
see `decisions.md` D17-D18), clean recovery.

**Two real debugging findings kept as evidence, not smoothed over:**
1. A race condition where concurrent responses all reported the same
   `order_id` (fixed via an early counter snapshot).
2. Container CPU measurement was diluted by Docker Desktop VM's
   multi-core visibility — `--cpus=1` didn't fix it (cgroup quotas don't
   change what `cpu_count()` reports); the actual fix was switching to
   `psutil.Process().cpu_percent()` (per-process, not system-wide).

### 5b. Production-shaping, Phases 1-6 (all complete, all committed)

```mermaid
flowchart TD
    Svc["order-svc<br/>(K8s Deployment + Service, orders namespace)"] -->|"/metrics/prometheus<br/>Prometheus format"| Prom["Prometheus<br/>(fresh install, monitoring namespace)"]
    Prom --> Grafana["Grafana dashboard<br/>(live incident view, 3 panels)"]
    Prom -->|"PromQL query_range"| Detector["anomaly_detector.py<br/>(standalone, real Prometheus data)"]
    Detector --> Grouper["alert_grouper.py<br/>(standalone copy of Wk5 logic, unchanged)"]
    Grouper --> RCA["rca_agent.py<br/>(REAL Claude API call, NOT Week 5's simulated version)"]
    RCA --> Handoff["handoffs/stage4-incident.json<br/>(real, written by write_incident_handoff.py)"]
    Handoff -->|subprocess| Stage5["Stage 5:<br/>remediation_agent.py (unmodified)"]
```

**Phase-by-phase summary:**
- **Phase 1:** `order-svc` deployed to Docker Desktop's K8s. Per the
  original Week 7 lab instructions it was first deployed into the
  `default` namespace; it was then deliberately moved into its own
  `orders` namespace for realism. Kubernetes namespace is an immutable
  field on an existing object, so this required deleting and recreating
  the Deployment/Service rather than an in-place edit — see
  `decisions.md` D30.
- **Phase 2:** `app.py` exposes a real Prometheus-format
  `/metrics/prometheus` endpoint via `prometheus_client` — the original
  custom JSON `/metrics` endpoint is untouched and still used by Stage 5.
- **Phase 3:** A fresh Prometheus instance (Helm-installed into
  `monitoring`, NOT reused from Week 4's KEDA stretch goal — that
  environment had been torn down) scrapes `order-svc` via
  `prometheus.io/*` Service annotations.
- **Phase 4:** `anomaly_detector.py` (standalone, does not import from
  `week-05/`) queries Prometheus's `query_range` API via PromQL, feeding
  real data into the unchanged `fit_detector()` (IsolationForest) logic
  from Week 5.
- **Phase 5:** A Grafana dashboard (3 panels: CPU %, Error Rate, p99
  Latency) verified showing a real, correlated incident from a live
  `load_generator.py` run.
- **Phase 6:** `alert_grouper.py` (standalone copy of Week 5's
  `group_alerts()`, unchanged) and `rca_agent.py` (a **deliberate
  upgrade**, not a copy — makes a real Claude API call, since
  `ANTHROPIC_API_KEY` is genuinely available here, unlike Week 5 where it
  used simulated `if/else` threshold logic) feed into
  `write_incident_handoff.py`, which writes the real
  `handoffs/stage4-incident.json` and chains into Stage 5's
  `remediation_agent.py` (unmodified) via `subprocess`.

**Why this design over the simpler alternative:** the originally-planned
approach (the load generator recording its own traffic observations and
feeding them directly to the detector) was rejected as architecturally
biased — real service telemetry must be independent of whoever is
generating load against it. This design decouples the two, mirroring
real Prometheus scrape behavior. Full reasoning: `decisions.md` D20.

**What is NOT changing:** `app.py`'s core logic, the `Dockerfile`, the
existing OTel spans (still valid — remain secondary evidence, not the
primary data path), `load_generator.py`, `fit_detector()`/
`FEATURE_COLUMNS`, `group_alerts()`, and `remediation_agent.py` itself
(Stage 5's code was never modified — Phase 6 invokes it as-is).

**Four real findings from building Phases 1-6, all documented in
`decisions.md`:**
- **D22:** local dev reaches Prometheus/`order-svc` via `kubectl
  port-forward` — explicitly not production-realistic; a genuine, still-open
  tradeoff (see §8).
- **D23:** IsolationForest (contamination=0.04) can miss a sustained
  incident once `rate()`'s 5-minute smoothing duplicates readings across
  several consecutive query points.
- **D24:** Prometheus's default 60s scrape interval was too coarse to
  reliably catch brief Gauge-based CPU spikes; fixed by reducing to 5s
  (with a real `scrape_timeout` config bug hit and fixed along the way).
- **D25-D27:** Phase 6 surfaced three more real findings — placeholder
  constants for not-yet-built Stage 3 autoscaling inputs (D25), a
  `subprocess` `cwd` bug causing ITSM tickets/handoffs to land in the
  wrong directory (D26), and a genuine gap in `remediation_agent.py`'s
  outcome taxonomy for "correctly decided no action needed," which was
  fixed (D27).

---

## 6. Stage 3 — Predictive Deploy (Phases 1-2 done, Phases 3-4 not built)

```mermaid
flowchart TD
    Inputs["Real inputs:<br/>Prometheus CPU%/error rate,<br/>OPA/conftest policy result (fresh terraform plan each run),<br/>kubectl replica count"] --> Risk["risk_scorer.py:<br/>risk score + proceed/block gate"]
    Risk -->|block| Blocked["Deploy blocked<br/>(policy fail = hard block, independent of score)"]
    Risk -->|proceed| Canary["canary_controller.py:<br/>v1 vs v2, concurrent Prometheus<br/>polling over one shared window"]
    Canary -->|promote| Promote["kubectl scale:<br/>v2 up to v1's replica count,<br/>v1 down to 0"]
    Canary -->|rollback| Rollback["kubectl delete:<br/>v2 Deployment, v1 untouched"]
```

**What's being risk-scored:** `order-svc`'s own K8s deployment (the same
real, already-running service from Stage 4) — not Stage 2's Terraform
plan (too low-signal; a small GCS bucket change rarely trips real risk)
and not a synthetic scenario. This keeps Stage 3 connected to both
Stage 2 (before) and Stage 4 (after) in the real pipeline.

**Canary design:** a genuinely real canary, not a simulated
recommendation. `app.py`/`app_v2.py` differ by one real, honest change —
v2 does half the CPU-bound hashing work of v1 (`100_000` vs `200_000`
iterations) — a real performance change, not a cosmetic label swap.
Separate images (`order-svc:v1`, `order-svc:v2`), not a shared image with
a runtime flag, matching real production practice: an immutable,
independently-buildable artifact per version, not a shared artifact
toggled by config.

**FinOps scope (Phase 3, not yet built):** `order-svc` runs on local
Docker Desktop Kubernetes, which GCP does not actually bill. The only
real, billed GCP resource in this capstone is Stage 2's GCS bucket — so
the planned `cost_estimator.py` will call the real Cloud Billing Catalog
API for that bucket's pricing only, with the `order-svc` scope limitation
documented plainly rather than inventing a hypothetical cloud runtime
cost for a service that isn't actually billed.

**Phase-by-phase status:**
- **Phase 1 — Real risk score. ✅ Done.** `risk_scorer.py` pulls all 3
  real inputs above and combines them into a risk score + gate decision.
  A failed OPA/conftest check is a hard block regardless of score. Writes
  `handoffs/stage3-risk.json`.
- **Phase 2 — Real canary. ✅ Done.** `canary_controller.py` samples v1
  and v2 together, at each timestamp, within one shared polling window
  (not two separate sequential windows — see D29), then promotes or
  rolls back based on the real comparison. **A real promote was
  executed** against the live cluster: `order-svc-v2` is now the live,
  production deployment; `order-svc` (v1) is intentionally left at 0
  replicas (not deleted) to preserve rollback capability. Writes
  `handoffs/stage3-canary.json`.
- **Phase 3 — Real FinOps.** Not started. `cost_estimator.py` will call
  the real Cloud Billing Catalog API for Stage 2's GCS bucket pricing.
- **Phase 4 — Wire it together.** Not started. An orchestrator running
  risk score → gate → (if proceed) canary → cost estimate → writes
  `handoffs/stage3-output.json`, completing the Stage 2→3→4 chain.

**Three real findings from building Phases 1-2, all documented in
`decisions.md`:**
- **D28:** the shared error-rate PromQL query
  (`rate(...{status="500"}[5m]) / rate(...[5m])`) had a real
  vector-matching bug — Prometheus's default division matching paired
  only the identical `status="500"` series, silently dropping the
  `status="200"` series from the denominator entirely. Result: the query
  evaluated to exactly `1.0` whenever any errors existed, or `0/0 = NaN`
  otherwise — never the real ratio. Fixed by wrapping both sides in
  `sum()` in both `risk_scorer.py` and `anomaly_detector.py`, plus an
  explicit `math.isnan()` guard in `risk_scorer.py` so a NaN can never
  again silently default the gate to `"proceed"`.
- **D29:** two canary-testing infrastructure bugs, found via real test
  runs. First, `kubectl port-forward` to a Service pins to a single
  backing pod rather than load-balancing — traffic sent through the local
  port-forward never reached v2 at all, reading as a false `0.0` rather
  than a real result. Fixed by generating comparison traffic from inside
  the cluster instead (a throwaway `kubectl run` pod hitting the Service
  by name). Second, `canary_controller.py` originally polled v1 and v2 in
  two separate sequential ~60s windows rather than together — meaning
  "v1's window" and "v2's window" were two different slices of real time,
  not a fair same-conditions comparison. Fixed by sampling both versions
  together at each timestamp within one shared window.

Full detail: `decisions.md` D28-D30, `handoffs/stage3-risk.json`,
`handoffs/stage3-canary.json`.

---

## 7. Rubric mapping

Maps each capstone rubric line item (from the course's Week 7 doc) to the
artifact/section that satisfies it.

| Rubric criterion | Points | Satisfied by |
|---|---|---|
| End-to-end pipeline integration | 20 | §1 (pipeline diagram) + §2 (handoff design) + §6 (Stage 3). Stages 4→5 fully chained (Phase 6); Stage 3 Phases 1-2 built and real-tested but run standalone, not yet `subprocess`-chained to Stage 2 or Stage 4 (Phase 4, not built). **Partially complete** — full 5-stage wiring not yet achieved. |
| Agentic IaC with policy enforcement | 15 | §3 — `orchestrator-c-heterogeneous/iac/`, fully built and verified; also reused live by §6's `risk_scorer.py`, which re-runs a fresh `terraform plan` → `conftest test` on every risk-score call |
| Agent security and guardrails | 15 | §3's two real incidents (unprompted `apply`, injection refusal) + §4's blast-radius chain (4 gates, all outcome paths verified, including the Phase 6-added `resolved_no_action_needed` path) |
| Observability (service + agent telemetry) | 10 | §5 — service-level spans (Step 3) + Week 5's agent-level `gen_ai.*` spans; production-shaped Prometheus/Grafana pipeline fully built, verified, and committed (Phases 1-6); also the data source for §6's real risk-scoring and canary comparison |
| Auto-remediation with blast-radius control | 10 | §4 — fully built and verified |
| Audit trail and governance | 10 | SLSA provenance (§3) + `handoffs/*.json` files (audit trail per stage, now including `stage3-risk.json`/`stage3-canary.json`) + ITSM tickets (§4) |
| Presentation clarity and demo quality | 10 | Demo script — **not yet built** (document 7 in the docs queue) |
| Technical report quality | 10 | Capstone report — **not yet built** (document 6 in the docs queue), will draw on `decisions.md` for honest lessons-learned material, including D22-D30 |

---

## 8. What's still open

- Stage 3 Phases 3-4 (FinOps cost estimator, full orchestrator wiring) —
  not started.
- Full 5-stage wiring/chaining end to end — Stages 4→5 chained (Phase 6);
  Stage 3 Phases 1-2 built and real-tested standalone, not yet chained to
  Stages 2/4 (blocked on Phase 4).
- Options B and A — not started.
- PR from `capstone-option-c` to `main` — not yet opened.
- `execute_scale` (Stage 5) remains simulated (updates in-memory state,
  never calls `kubectl scale`) — deliberately deferred, see `decisions.md`
  D26.
- The Phase 4-6 chain (Stage 4→5) runs via local `kubectl port-forward`,
  not as an in-cluster K8s Job — deliberately deferred, see `decisions.md`
  D22. (Note: Stage 3's canary comparison specifically works around this
  same limitation differently — see D29 — since a canary needs real
  load-balanced traffic across two pods, which port-forward cannot
  provide.)
- Documents 6 (capstone report) and 7 (demo script) — not started.

See `docs/CONTINUATION.md` for the live, detailed status table and the
next-immediate-task breakdown.
