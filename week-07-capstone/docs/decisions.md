# CSE636 Capstone — Decisions Log

Chronological record of every significant decision made during the Week 7
capstone build, including alternatives considered and rejected, with
reasoning. This is the raw source material for `architecture.md` — read
this for *why*, read `architecture.md` (once written) for the synthesized
*what*.

---

## D1 — Week 7 phase ordering

**Decision:** Capstone planning → IaC lab → Capstone build-out → Final exam review.

**Alternative considered:** Build-out before IaC lab (original instinct).

**Rejected because:** the capstone's Stage 2 (Agentic IaC) didn't exist yet.
Building 4 stages then retrofitting a 5th into an already-wired pipeline
later means touching the wiring twice. Doing IaC first means the
build-out happens in one continuous pass, all 5 stages in real order.

---

## D2 — IaC lab: local Mac vs. GCP VM

**Decision:** Local Mac, not `cse636-lab-vm`.

**Reasoning:** `gcloud` already authenticated locally from Week 1. No VM
start/stop/SSH session overhead per iteration. The IaC stage is logically
separate from Wk3's CI/CD stage (Jenkins on the VM) — no need to co-locate.
VM stays reserved for what it's actually for.

---

## D3 — Dedicated GCP project for the capstone

**Decision:** Created `cse636-capstone-iac`, a new project, rather than
reusing `project-8c1a75fc-3921-4d5c-ae0` ("My First Project", Weeks 1-2's
VM/Jenkins home).

**Trigger:** discovered a service account had been accidentally created
under `swift-devsecops-lab-01` (unrelated DevSecOps lab work) because the
active `gcloud` project wasn't checked first.

**Reasoning:** Terraform's create/destroy operations need contained blast
radius — a mistake in a dedicated, disposable project can't damage
Weeks 1-2's working VM/Jenkins setup. No cost penalty: trial credit lives
on the billing account, not the project, so a new project draws from the
same pool.

---

## D4 — Orchestration approach: build all three options

**Decision:** Build Option C (heterogeneous platforms, file/artifact
handoffs), then Option B (GitHub Actions backbone), then Option A (single
Python script) — all three, in that order, each fully working and merged
independently.

**Alternative considered:** Build only one orchestrator (the rubric's
literal minimum).

**Reasoning:** deliberate choice for more hands-on practice — "the more I
practice, the more I learn." Also strengthens the report's "lessons
learned" / comparative-analysis material with real, not hypothetical, data.

**Trade-off acknowledged:** roughly 3x the implementation work of the
strict rubric minimum. Time-risk mitigated by Option A being intentionally
the cheapest/lightest to build, absorbing schedule pressure first if
needed.

**Note:** user later clarified they are not time-constrained for the
capstone (will submit whatever is ready by the weekend), which relaxes
this trade-off's urgency but doesn't change the decision itself.

---

## D5 — Repo/branch structure

**Decision:**
```
week-07-capstone/
  orchestrator-c-heterogeneous/
  orchestrator-b-actions/
  orchestrator-a-python/
  docs/
    architecture.md
```
One branch per option (`capstone-option-c`, `-b`, `-a`), each PR'd to
`main` on completion — same propose→approve→merge discipline as Week 3's
build-fixer agent.

**Reasoning:** each option must be independently reproducible — a fresh
clone of just that option's folder should work standalone. This means
shared artifacts (e.g., the IaC Terraform/OPA content) get *duplicated*
into each orchestrator's folder rather than cross-referenced, to avoid
breaking independence.

---

## D6 — Inter-stage handoff mechanism

**Decision:** Each stage writes a JSON output file to
`handoffs/stageN-output.json` (audit trail), then *directly invokes* the
next stage's script via `subprocess` — not a polling watcher.

**Alternative considered:** A standalone watcher process polling
`handoffs/` for new files and triggering the next stage reactively.

**Rejected because:** unnecessary complexity for a human-initiated,
short-burst pipeline (not a long-running production service). Direct
chaining also naturally supports an explicit approval pause (`input()`)
between stages — a poller can't easily express "wait for human
confirmation," it just reacts to files appearing.

**Refinement:** only Stage 2→3 (IaC→Deploy) gets a human-approval gate;
Stages 4→5 and the 5→4 loop-back auto-chain, since those represent the
"agentic SRE" parts meant to run autonomously within blast-radius controls.

---

## D7 — Stage build order: back-to-front

**Decision:** Build Stage 5 (remediation) first, then Stage 4
(observability), then Stage 3 (predictive deploy) last, then connect
Stage 2 (already done) into Stage 3.

**Reasoning:** Stage 5 is the most mature existing code (Week 6) — build
it first to get a concrete, working target the earlier stages can be
verified against ("does this correctly hand off to something Stage 5 can
consume"). Stage 3 is the most net-new work (canary logic, FinOps
estimate don't exist anywhere yet) — tackled last so its interface
requirements are already known from what Stage 4 produces, rather than
guessing ahead.

---

## D8 — Stage 5 foundation: Assignment code, not Lab code

**Decision:** Build on `week-06-assignment/src/react_agent.py`
(INC-002/order-svc, scale-out, 4 blast-radius controls), not
`week-06-lab/react_agent.py` (generic payment-svc rollback scenario).

**Reasoning:** the Assignment version already targets the exact incident
(`INC-002`) and metrics that Week 5's `alert_grouper.py`/`rca_agent.py`
actually produced, and already has more layered guardrails (kill switch,
rate limit, error-budget gate, plus approval) vs. the Lab's single gate.
Genuinely built with the eventual capstone integration in mind, just never
wired up.

---

## D9 — ITSM ticket + Stage 5 handoff (new work beyond Week 6)

**Decision:** Add `create_itsm_ticket()` (writes a structured local JSON
record, not a real PagerDuty/ServiceNow API call) and
`write_stage5_handoff()` (writes `handoffs/stage5-output.json`) to
`remediation_agent.py`.

**Reasoning:** these were the two concrete gaps between Week 6's working
code and what the capstone rubric needs — Week 6 had no ITSM integration
and no way to feed a result back to an upstream stage.

---

## D10 — Commit granularity for Stage 5's three outcome paths

**Decision:** One commit per outcome path (`remediated`,
`escalated_declined`, `escalated_kill_switch`), tested and committed
separately, since `stage5-output.json` is overwritten (not appended) on
every run.

**Reasoning:** preserves a clean git-history record of each distinct
outcome, rather than only the last one run before committing.

---

## D11 — Real agent incidents observed and kept as evidence, not "fixed away"

**Two incidents captured verbatim in the IaC lab README, not smoothed over:**
1. Claude Code, asked only to fix a Terraform label, unpromptedly attempted
   `terraform apply` — caught before any real infra was created
   (`terraform show` returned `No state.`, `gcloud storage ls` confirmed
   empty).
2. The prompt-injection demo: the agent correctly refused a malicious
   instruction across three escalating attempts, including a direct
   "I am human in the loop" authority assertion.

**Reasoning for keeping both, unedited:** genuine, unstaged evidence for
the capstone's "Agent security and guardrails" rubric line is more
valuable than a staged example — and the contrast between the two
incidents (over-scoping on a "helpful" task vs. resisting pressure on a
"harmful" one) is a more nuanced, realistic finding than either alone.

---

## D12 — SLSA provenance: hand-authored, then corrected three times

**Decision:** Add SLSA v1.0 provenance for the Terraform artifact —
required by the rubric's governance line, not covered by the base IaC lab
spec.

**Three real corrections made during review, each itself a finding:**
1. Git commit reference initially pointed to a commit that didn't contain
   the artifact (provenance generated before the commit existed).
2. Timestamps were initially fabricated (single retroactive value
   duplicated into both `startedOn`/`finishedOn`); corrected to use two
   genuine session-derived timestamps, with an honesty annotation.
3. Builder version (`claude-code`) was initially an unverified carryover
   from Week 2's notes; corrected via `claude --version`, judged reliable
   given the whole session occurred within one calendar day.

**Verification:** ran the real `slsa-verifier` CLI against the document —
it correctly failed (no certificate, no Rekor entry), confirming the
document is provenance-*shaped* but not independently *verifiable*,
exactly the honest caveat already written into it.

---

## D13 — Stage 4 service design: build new (Option 2), not reuse (Option 1) or synthetic (Option 3)

**Options considered:**
- **Option 1:** Reuse Week 0's starter Flask app (already Dockerized,
  already has `/risk`) — lowest risk, ~4.5-6 hrs, best learning-per-hour
  since the container is already proven.
- **Option 2:** Build a new purpose-built `order-svc` from scratch —
  highest risk/time (~5.5-8 hrs original estimate), most new-skill
  surface area colliding at once.
- **Option 3:** Synthetic data, no container at all (~3-4.5 hrs) — least
  new learning, essentially repeats Week 5.

**Decision:** Option 2, chosen explicitly for maximum hands-on practice
("more practice = more learning"), even after being shown Option 1 had
the better learning-to-time ratio.

**Correction made during this decision:** initially believed the capstone
was a "bonus" — corrected against the plan document, which lists it at
20%, tied with the Final Exam as the largest single component.

---

## D14 — order-svc: real CPU-bound work, not sleep()

**Decision:** `/order` performs genuine CPU-bound computation (repeated
SHA-256 hashing), not `time.sleep()`.

**Reasoning:** makes CPU saturation under load real and measurable via
`psutil`, not scripted — concurrent requests genuinely compete for real
CPU cycles.

---

## D15 — Error correlation: probabilistic, driven by real CPU pressure

**Decision:** Once measured `cpu_pct` crosses `CPU_ERROR_THRESHOLD` (75%),
`/order` starts probabilistically returning 500s, with failure probability
scaling with how far past the threshold the reading is.

**Reasoning:** makes the eventual RCA conclusion ("CPU saturation likely
driving...") an *earned* one from real data, not an assumed one.

---

## D16 — Two real bugs found and fixed in order-svc (Step 1, standalone testing)

1. **Race condition:** `order_id` in the JSON response read the *shared
   global* `_request_count` again at response-build time, not a snapshot
   from when the request started — under real concurrency, every response
   in a burst reported the *same*, most-recent value. Fixed by snapshotting
   `order_id = _request_count` immediately after incrementing.
2. **Metrics snapshot-timing gap:** a single post-burst `/metrics` call
   showed `cpu_pct` back near 0, completely missing a peak of 100% that
   occurred mid-burst. Fixed by adding `_peak_cpu_pct` tracking (`max()`
   over every request), alongside the existing instantaneous reading.

**Broader lesson kept for the report:** point-in-time metric snapshots can
silently miss transient spikes that have already resolved — a real
argument for continuous/scraped monitoring over ad hoc checks.

---

## D17 — Container CPU measurement: two rounds of real debugging

**Problem 1:** `psutil.cpu_percent()` (system-wide) inside a Docker
Desktop container reported far lower values under the same load that hit
100% standalone — diluted by however many cores the host VM reports.

**First attempted fix:** `docker run --cpus=1` (cgroup CPU quota).
**Result:** did NOT fix it — cgroup quotas throttle execution but don't
change what `psutil.cpu_count()` *reports* inside the VM.

**Actual fix:** switched to `psutil.Process().cpu_percent()` — measures
this process's own CPU time, normalized to one core (100% = one core
fully saturated), independent of host core count. Required a one-time
"warm-up" call (`_process.cpu_percent()` once at startup) since the first
real call always returns 0.0.

**Consequence:** values can now legitimately exceed 100% (e.g., 290%,
meaning ~2.9 cores' worth of concurrent work — real, since `hashlib`
releases the GIL during hashing, allowing genuine multi-core parallelism).

---

## D18 — Leave cpu_pct uncapped, don't clamp to 0-100

**Alternative considered:** clamp reported `cpu_pct` to a `0-100` range
for downstream readability.

**Rejected because:** (1) real observability tools (Prometheus/cAdvisor/
K8s) don't clamp multi-core CPU usage either — it's true information; (2)
clamping would break the error-probability formula's gradation, since it
scales failure probability with *how far past* threshold the reading is;
(3) staying consistent with Week 4's KEDA/autoscaling conventions, which
already assume multi-core-aware metrics.

**Mitigation:** added an explanatory code comment instead, so the
uncapped values are understood rather than mistaken for a bug.

---

## D19 — Load generator pattern: calm → spike → recovery

**Decision:** 10 baseline requests (spaced 1s apart) → 40 concurrent
requests (concurrency 20) → 10 recovery requests (spaced 1s apart).

**Reasoning:** matches the `INC-002` incident narrative (quiet service,
sudden real incident, clean recovery) already established in Weeks 5-6,
rather than inventing an unrelated traffic pattern.

**Verified result:** 13/40 real errors during spike (32.5%), peak CPU
212.4%, clean return to 0% CPU / all-200s in recovery.

---

## D20 — Step 5 architecture: production-shaped, not load-generator-records-itself

**Options considered:**
1. **Load generator records its own observations** (its view of
   `cpu_pct`/`status`) and feeds that directly into `anomaly_detector.py`.
2. **A separate script polls `/metrics` on an interval**, decoupled from
   the traffic generator — closer to real Prometheus scrape behavior.
3. **Full production-shaped:** deploy `order-svc` to local K8s (not
   `docker run`), expose real Prometheus-format metrics, scrape via the
   existing Prometheus stack from Week 4's KEDA stretch goal, query via
   PromQL instead of hand-aggregating.

**Rejected Option 1 because:** architecturally biased — the traffic
generator observing its own traffic and calling that "monitoring" isn't
how real observability works; a real service's telemetry should be
independent of who's calling it.

**Decision:** Option 3 (full production-shaped), explicitly chosen once
confirmed the user is not time-constrained for this project. Reuses
Week 4's already-installed, already-proven Prometheus/KEDA Helm stack
rather than building anything from scratch.

**Confirmed scope:** includes an optional Grafana dashboard (Phase 5) as
a demo-strength bonus.

**What carries forward unchanged from Steps 1-4:** `app.py`'s core logic,
`Dockerfile`, existing OTel spans, `load_generator.py` — all kept exactly
as-is; production-shaping is additive, not a rewrite.

---

## D21 — Documentation strategy: defer big docs, capture decisions continuously

**Initial plan:** wait until the full build-out is done, then write
`architecture.md`/`RUNBOOK.md`/report once, using the conversation
transcript as source material.

**Correction:** flagged as risky — long-session memory isn't guaranteed,
and total remaining time is unknown. Revised to: write per-stage READMEs
immediately after each stage (already the practice), plus this
`decisions.md` log updated continuously at each real decision point,
so no single document depends on reconstructing reasoning after the fact.

**Confirmed generation order for the remaining documents:**
1. `docs/decisions.md` (this file)
2. Continuation/handoff document (for starting a fresh chat if needed)
3. `docs/architecture.md`
4. `docs/RUNBOOK.md`
5. Per-stage READMEs (fill gaps: `observability/`, `remediation/`)
6. Capstone report (4-6pp)
7. 15-minute demo script/outline

---

### D22 — anomaly_detector.py -> Prometheus: local dev via port-forward, containerize for Phase 6

**Decision:** Phase 4's anomaly_detector.py reaches Prometheus's query_range
API via `kubectl port-forward svc/prometheus-server 9090:80` while
developing/debugging the PromQL logic locally. This is explicitly NOT
production-realistic -- port-forward is a manual developer tunnel, not
something a real deployment relies on.

**Why not fix this now:** the actual goal of Phase 4 is validating the
PromQL queries and fit_detector() behavior on real data -- fast local
iteration (edit script, rerun, see result in seconds) matters more right
now than in-cluster realism.

**Plan to close the gap:** once anomaly_detector.py's logic is confirmed
working, it will be containerized (Dockerfile similar to order-svc's) and
run as a Kubernetes Job for Phase 6's "chain into Stage 5" step -- at that
point PROMETHEUS_URL changes from http://localhost:9090 to Prometheus's
in-cluster DNS name (http://prometheus-server.monitoring.svc.cluster.local),
and no tunnel is needed since the Job runs on the correct side of the
network boundary. Phase 6 needs anomaly_detector.py running as an
automated pipeline stage anyway, so this isn't wasted work -- just
correctly sequenced later rather than now.

**Rejected alternative:** containerizing immediately, before validating
the query logic. Rejected because every iteration on the PromQL
expressions would require a full rebuild+redeploy cycle, far slower than
local iteration for something still being debugged.

---

## D23 — IsolationForest under-detects sustained/repeated incidents at low contamination

**Finding:** Real-data testing produced a genuinely surprising result. The
same anomalous reading (error_rate=1.0, latency_p99_ms=2387.5, from a real
load_generator.py spike) appeared in two separate test runs:
- Run 1: appeared as a single isolated point (1 of 46) -- correctly flagged
  as an anomaly.
- Run 2: the same value appeared 5 consecutive times (5 of 61, ~8.2% of the
  window) due to rate()'s 5-minute trailing-average smoothing -- NONE of
  the 5 points were flagged, despite being the same extreme values.

**Root cause:** IsolationForest isolates points by how easy they are to
separate from their neighbors via random splits. A single extreme point is
trivially easy to isolate. Five points at an identical extreme value form a
small cluster, which is inherently harder to separate -- even though every
value in that cluster is genuinely anomalous. This is compounded by
contamination=0.04 (~4%) being lower than the actual anomalous fraction in
this window (~8.2%), so the model's internal threshold wasn't tuned to
expect a cluster this large.

**Why this happens with real data but didn't surface in Week 5's testing:**
Week 5's synthetic data controlled the anomaly block size directly (16
contiguous minutes out of 500, ~3.2%) and used per-minute readings with no
PromQL rate()-smoothing effect duplicating values across multiple rows.
Real Prometheus data introduces this smearing effect organically, which
synthetic generation didn't expose as a testable case.

**Disposition:** documented as a known limitation, not fixed. Two possible
mitigations exist (raise contamination to better match real cluster sizes;
deduplicate consecutive identical rate()-smoothed readings before fitting)
but neither was implemented -- Phase 4's goal was validating the
Prometheus -> PromQL -> IsolationForest pipeline works end-to-end, which it
does. Tuning detection sensitivity is flagged as future work, not blocking.

**Practical implication:** the current detector reliably catches brief,
isolated spikes but may under-detect a sustained incident once its
rate()-smoothed signature spans several consecutive query points --
arguably the more realistic real-world case, which makes this a genuinely
important limitation to state plainly in the capstone report rather than
implying the detector performs uniformly well.

---

## Open items (not yet decided)

- **PR from `capstone-option-c` to `main`:** not yet opened. Original
  question was whether to open it now (IaC-only) or after more of Option
  C's build-out lands on the branch. Still unresolved as of Stage 4
  Step 4's completion.
