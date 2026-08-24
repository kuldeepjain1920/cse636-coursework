# CSE636 Final Exam Review — Week-by-Week

The exam is cumulative across all 7 weeks. Since most weeks were built
hands-on rather than just read about, this is mostly a **consolidation
pass**, not fresh learning — except Week 7's IaC-adjacent concepts that
weren't part of the hands-on lab (SLSA supply-chain concepts beyond what
was directly tested, Backstage/IDP/golden paths), which deserve real
review time rather than a skim.

For each week: the core concepts, and — where it exists — the specific
artifact in `cse636-coursework` that proves hands-on understanding, so
you can use your own repo as a study aid rather than re-deriving
everything from memory.

---

## Week 1 — Autonomy levels

**Core concepts to be able to explain cold:**
- The autonomy-level spectrum for agentic systems (from fully
  human-driven through to fully autonomous) and what distinguishes each
  level — specifically, *where the human sits* in the loop at each level
  (approving every action, approving classes of action, monitoring with
  override, fully hands-off).
- Why higher autonomy isn't strictly "better" — the tradeoff between
  velocity and blast radius.

**Your hands-on evidence:** every guardrail decision across the whole
capstone is really an autonomy-level decision in practice — Stage 5's
four blast-radius gates (kill switch, rate limit, error-budget gate,
human approval) are a concrete instantiation of "where exactly does the
human sit." Be ready to explain the capstone's Stage 5 as a worked
example of autonomy-level design, not just remediation logic.

**Likely exam angle:** given a scenario, identify what autonomy level is
being described, or design the right level for a given risk profile.

---

## Week 2 — MCP / tool scoping, least privilege

**Core concepts:**
- What MCP (Model Context Protocol) actually standardizes — tool
  definitions, structured calls, a consistent interface between an agent
  and external systems.
- Least-privilege tool scoping: why an agent's available tools should be
  the minimum needed for its task, not a broad general-purpose toolkit.

**Your hands-on evidence:** the `jenkins_status.py` MCP server from
earlier coursework. Also directly relevant: Stage 2's service account
scoped to `storage.admin` only (not project-owner or broader) — a real
least-privilege decision, verified in practice.

**Likely exam angle:** why scope a tool narrowly even when a broader
permission would be "more convenient" — tie this back to the D11
incident (an agent attempting an unprompted `terraform apply`) as a
concrete argument for why scoping and human gates both matter even with
a well-behaved agent.

---

## Week 3 — Agentic CI/CD

**Core concepts:**
- Code review agents, test-impact analysis, build-fixer agents.
- Where a human-approval gate belongs in a CI/CD flow (typically: before
  merge, not after).

**Your hands-on evidence:** the build-fixer-demo Jenkins pipeline and
Stage 1 in the capstone's overall pipeline design (`architecture.md`
§1) — reused as-is from Week 3, not rebuilt for the capstone.

**Likely exam angle:** designing a review/gate point in a CI/CD pipeline
for agent-generated code changes.

---

## Week 4 — Predictive deploy: risk, canary, cost (FinOps)

**Core concepts:**
- Risk-scoring a deploy before it happens — what real signals feed a
  risk score (this is the one you actually built two capstones' worth
  of evidence for).
- Canary deployment mechanics — traffic splitting, comparison windows,
  promote/rollback criteria.
- FinOps — estimating real infrastructure cost as part of a deploy
  decision, and the importance of scoping cost estimates to what's
  actually billed rather than inventing numbers.

**Your hands-on evidence — this is your strongest week, and worth
walking through fully since it's fresh:**
- `risk_scorer.py` (Stage 3 Phase 1) — real CPU/error-rate/OPA-result/
  replica-count inputs, weighted into a score + gate decision.
- `canary_controller.py` (Stage 3 Phase 2) — a **real, executed**
  canary: separate v1/v2 images, concurrent Prometheus polling over a
  shared window, and a genuine `kubectl scale`/`kubectl delete` action
  based on the comparison, not a simulated recommendation.
- The FinOps design (Phase 3, not built, but the *design* is
  documented): scoping a real Cloud Billing Catalog API call to only
  Stage 2's actually-billed GCS bucket, deliberately not inventing a
  hypothetical cost for `order-svc` since it runs on unbilled local K8s.
  This scoping discipline — not fabricating a number just to have one —
  is itself worth articulating on an exam if asked about FinOps
  estimation honesty.
- Prophet forecasting + KEDA autoscaling (earlier Week 4 stretch goal
  work) — if the exam touches time-series forecasting for capacity
  planning specifically, this is the artifact to recall.

**Likely exam angle:** given a deploy scenario, identify what real
signals should feed a risk score, and design a canary comparison
methodology (this is where your two real bugs — D28, D29 — become great
exam-answer material: you can describe *why* a naive canary comparison
fails, from direct experience, not textbook recall).

---

## Week 5 — Observability

**Core concepts:**
- Service-level telemetry vs. agent-level telemetry — the distinction
  between standard OTel semantic conventions (`http.*`) and GenAI-specific
  span conventions (`gen_ai.*`).
- Anomaly detection approaches — IsolationForest, DBSCAN — and their
  respective strengths/failure modes.
- RCA (root cause analysis) — reasoning from metrics to a probable cause.

**Your hands-on evidence:**
- `order-svc`'s OTel spans (`order.process`, `http.*`/`order.*`
  attributes) — service-level, distinct from Week 5's `gen_ai.*`
  agent-level spans.
- `anomaly_detector.py` — real IsolationForest (`contamination=0.04`)
  against real Prometheus data, with a **documented, real failure
  mode**: it missed a genuine 5-point cluster of anomalous readings due
  to `rate()`'s 5-minute smoothing (D23). This is a genuinely strong
  exam answer if asked about anomaly-detection limitations — you have a
  real, specific, diagnosed example, not a hypothetical.
- `rca_agent.py` — a real Claude API call reasoning from actual
  `peak_metrics`, contrasted directly with Week 5's own simulated
  `if/else` version (you can articulate exactly what changes when you
  swap simulated reasoning for a real model call).

**Likely exam angle:** explain a specific anomaly-detection failure mode
and how you'd mitigate it (D23 is your answer, verbatim); distinguish
service-level from agent-level observability.

---

## Week 6 — Auto-remediation

**Core concepts:**
- ReAct agent loops (reason → act → observe, repeated) for incident
  response.
- Blast-radius controls — layered safety gates before an agent takes a
  destructive/costly real-world action.
- The specific failure mode where a model treats "wait for approval" as
  a conversational stopping point rather than actually invoking a tool
  that triggers a real pause — a real bug you hit and fixed in Week 6
  itself (rewriting the system prompt and tool description so that
  *calling the tool* is what triggers the approval pause, not the model
  narrating that it's waiting).

**Your hands-on evidence:**
- `remediation_agent.py` — 4 layered gates (kill switch, rate limit,
  error-budget gate, human approval), all outcome paths verified against
  real behavior, not just code-reviewed.
- The tool-avoidance bug fix from the original Week 6 build, and its
  echo in the capstone: D27's outcome-taxonomy gap deliberately did NOT
  reclassify the case where a real scale was recommended but never
  executed — because that pattern is specifically the tool-avoidance bug
  resurfacing, and conflating it with a legitimate no-action outcome
  would have hidden a real class of failure.

**Likely exam angle:** design blast-radius controls for a given
autonomous action; explain the tool-avoidance failure mode and how
prompt/tool design addresses it — you have a real before/after fix to
describe.

---

## Week 7 — Agentic IaC, SLSA, IDP/golden paths

**This is the week most worth extra review time** — the capstone lab
gave you hands-on Terraform/OPA and SLSA experience, but topics like
Backstage, Internal Developer Platforms (IDP), and "golden paths" were
part of the course material without a corresponding hands-on artifact in
your repo. Don't skip this section assuming the rest of the week
transfers the same way Weeks 1-6 do.

**Core concepts, with hands-on evidence where you have it:**

- **Terraform + OPA/conftest policy gating** — ✅ strong hands-on
  evidence: `gcs.tf`, `policy/gcs.rego`, verified against all three
  policy cases (pass, wrong value, missing label).
- **SLSA (Supply-chain Levels for Software Artifacts)** — ✅ hands-on,
  but review the **conceptual framework** beyond just your one example:
  what the different SLSA levels actually require (build provenance,
  hermetic builds, two-person review, etc.), since your capstone only
  demonstrates one hand-authored provenance document failing verification
  — useful as a concrete example of "shaped but not verifiable," but you
  should be able to explain *why* a real Level 3+ build would differ
  (signed provenance from a trusted build system, not hand-authored).
- **Prompt injection defenses** — ✅ strong hands-on evidence: your
  three-escalating-attempt refusal demo, including the direct
  authority-assertion attempt.
- **Backstage / Internal Developer Platforms (IDP)** — ⚠️ **no hands-on
  artifact** — review this from course materials directly. Core idea to
  be able to explain: an IDP centralizes self-service infrastructure
  actions behind a consistent interface/catalog, reducing the cognitive
  load on individual developers and centralizing where policy can be
  enforced.
- **Golden paths** — ⚠️ **no hands-on artifact** — review from course
  materials. Core idea: a golden path is an opinionated, supported,
  "paved road" way of doing something (deploying a service, provisioning
  infra) that's easier to follow than to deviate from, without
  *forbidding* deviation outright.

**Likely exam angle:** SLSA levels and what distinguishes them; how an
IDP/golden-path approach relates to (or differs from) the kind of
per-repo policy gating you built by hand in Stage 2 — this is a good
place to think about explicitly, since your hands-on work is closer to
"manual policy enforcement" than "centralized platform enforcement," and
the exam may ask you to articulate that distinction.

---

## Cross-cutting themes likely to show up regardless of week

- **Audit trails and governance** — you have real, concrete
  material here: the `handoffs/*.json` files as an inter-stage audit
  trail, SLSA provenance, ITSM tickets. Be ready to explain *why* an
  audit trail matters even when every individual action was "correct" —
  it's about post-hoc verifiability, not just catching mistakes in the
  moment.
- **The gap between "looks real" and "is verifiable"** — your SLSA
  provenance document is the cleanest example of this distinction from
  your own work: structurally correct but not cryptographically
  verifiable. This concept likely generalizes across multiple exam
  questions (agent-generated anything vs. independently verified
  anything).
- **Why real infrastructure surfaces bugs simulation doesn't** — this is
  the throughline of your entire capstone (D22-D30), and a strong
  general answer to almost any "why does X matter" question about
  testing against real systems.

---

## Suggested review order

1. **Week 7** first, specifically Backstage/IDP/golden paths — this is
   your only real gap.
2. **Weeks 4-6** as a fast confirmation pass — you have the strongest
   hands-on evidence here and it's the most recent, so this should be
   quick.
3. **Weeks 1-3** as a concept refresher — older material, less
   hands-on depth in your own repo, worth a slower re-read of course
   notes rather than relying purely on capstone cross-reference.
