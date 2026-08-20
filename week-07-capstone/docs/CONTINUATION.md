# CSE636 Capstone — Continuation / Handoff Document

**Purpose:** paste this entire document into a new Claude chat to resume work
on this capstone with full context, without needing the original
(very long) conversation history. Keep this updated at the end of each
work session.

**Last updated:** end of Stage 4 Step 4 (load generator), before starting
the production-shaped Step 5 rebuild.

---

## 1. Project identity

- **Course:** CSE636 — DevOps for AI, CSTU, Prof. Qingsong Zhang
- **Repo:** `github.com/kuldeepjain1920/cse636-coursework`
- **Active branch:** `capstone-option-c`
- **This document covers:** the `week-07-capstone/` folder only (Weeks 0-6
  are complete and closed out separately — see `/areas/cse636-devops-for-ai.md`
  memory notes for that history if needed, not relevant to continuing this
  specific work)
- **Grading weight:** Capstone Project = 20% (tied with Final Exam as the
  largest single component — NOT a bonus, this was previously misjudged
  and corrected)
- **Deadline posture:** not time-constrained; will submit whatever is
  ready by the weekend

---

## 2. Glossary / terminology

| Term | Meaning |
|---|---|
| `order-svc` | The fictional service being observed/remediated throughout Weeks 5-6 and now the capstone — a real Flask app built in Stage 4 |
| `INC-002` | The specific incident ID (CPU saturation on `order-svc`) established in Week 5's synthetic data and Week 6's remediation agent; now being reproduced with **real** data in Stage 4 |
| Stage 1-5 | The capstone's 7-stage pipeline: Wk1 (autonomy levels, conceptual) → Wk2 (MCP/tools, conceptual) → **1** Agentic CI/CD (Wk3) → **2** Agentic IaC (Wk7 lab) → **3** Predictive deploy (Wk4) → **4** Observability (Wk5) → **5** Auto-remediation (Wk6) |
| Option C / B / A | Three orchestration approaches being built, in this order: **C** = heterogeneous platforms, file/subprocess handoffs (current focus); **B** = GitHub Actions as backbone (not started); **A** = single Python script (not started) |
| `capstone-option-c` | The git branch all Option C work lives on |
| Handoff file | `handoffs/stageN-output.json` — JSON audit-trail file each stage writes before invoking the next stage directly via `subprocess` |
| Blast-radius controls | The 4-5 automated safety gates in `remediation_agent.py` (kill switch, rate limit, error-budget gate, human approval) |

---

## 3. Environment / credentials reference

| Item | Value |
|---|---|
| GCP project (capstone/IaC only) | `cse636-capstone-iac` — dedicated, isolated from Weeks 1-2's `project-8c1a75fc-3921-4d5c-ae0` |
| GCP account | `kuldeepjainphotos@gmail.com` |
| GitHub account | `kuldeepjain1920` |
| Local repo path | `~/cse636-coursework` |
| Capstone folder | `~/cse636-coursework/week-07-capstone/` |
| Service account (IaC) | `terraform-iac-demo@cse636-capstone-iac.iam.gserviceaccount.com`, scoped to `roles/storage.admin` only |
| Key file | `week-07-capstone/orchestrator-c-heterogeneous/iac/gcp-sa-key.json` (gitignored) |
| Python venvs in use | `venv-week6` (repo root, has `anthropic`+`python-dotenv`, reused for Stage 5); `venv-order-svc` (inside `order-svc/`, has `flask`+`psutil`+`opentelemetry-*`+`requests`) |
| Ports in local use | `8080` → `order-svc` (Docker container, `docker run -p 8080:8080`) |
| `.gitignore` (root) additions this project | `gcp-sa-key.json`, `tfplan.binary`, `tfplan.json`, `.terraform/`, `venv-*/` |
| ANTHROPIC_API_KEY | Loaded via `.env` at repo root (`~/cse636-coursework/.env`), found by `load_dotenv()` walking up from cwd |

---

## 4. Repo structure (current state)

```
cse636-coursework/                          [repo root, branch: capstone-option-c]
├── .gitignore
├── .env                                    [gitignored — ANTHROPIC_API_KEY]
├── week-00 through week-06.../             [complete, closed out, not relevant here]
└── week-07-capstone/
    ├── docs/
    │   └── decisions.md                    [DONE — chronological decisions log]
    └── orchestrator-c-heterogeneous/
        ├── handoffs/
        │   ├── stage4-incident.json        [hand-written fixture, used to test Stage 5]
        │   └── stage5-output.json          [overwritten each Stage 5 run]
        ├── iac/                            [DONE — Stage 2, full IaC lab]
        │   ├── gcs.tf
        │   ├── policy/gcs.rego
        │   ├── malicious_docs.txt
        │   ├── provenance.json
        │   ├── README.md
        │   └── gcp-sa-key.json             [gitignored]
        ├── remediation/                    [DONE — Stage 5]
        │   ├── remediation_agent.py
        │   └── itsm_tickets/
        │       ├── TICKET-4bcc5234.json    [remediated outcome]
        │       ├── TICKET-f80d6a13.json    [escalated_declined outcome]
        │       └── TICKET-d0bd48bc.json    [escalated_kill_switch outcome]
        └── observability/                  [IN PROGRESS — Stage 4]
            ├── load_generator.py           [DONE — Step 4]
            ├── requirements.txt             [DONE — just `requests`]
            └── order-svc/                  [DONE — Steps 1-3]
                ├── app.py
                ├── requirements.txt         [flask, psutil, opentelemetry-sdk, opentelemetry-api]
                ├── Dockerfile
                ├── .dockerignore
                └── venv-order-svc/          [gitignored]
```

---

## 5. Status by capstone component

| Component | Status | Commit(s) |
|---|---|---|
| Capstone planning | ✅ Done | n/a |
| Stage 2 (IaC lab) | ✅ Done, fully verified incl. SLSA + real bugs found | `1c7e2b2`, `c4580c3` |
| Stage 5 (auto-remediation) | ✅ Done, 3 outcome paths verified | `3f5364b`, `baac52c`, `be3f793` |
| Stage 4 Steps 1-4 (service, container, OTel, load gen) | ✅ Done | `1583769`, `b09ed39`, `369b86c`, `cac93c9` |
| **Stage 4 Step 5-6 (production-shaped bridge + chain)** | ⬜ **NOT STARTED — this is the current task** | — |
| Stage 3 (predictive deploy) | ⬜ Not started | — |
| Wiring all 5 stages end-to-end | ⬜ Not started | — |
| Option B (GitHub Actions) | ⬜ Not started | — |
| Option A (single script) | ⬜ Not started | — |
| `docs/decisions.md` | ✅ Done | `be01265` |
| `docs/architecture.md` | ⬜ Not started (doc #3 in queue) | — |
| `docs/RUNBOOK.md` | ⬜ Not started (doc #4 in queue) | — |
| Per-stage READMEs (remaining: observability/, remediation/) | ⬜ Not started (doc #5 in queue) | — |
| Capstone report (4-6pp) | ⬜ Not started (doc #6 in queue) | — |
| 15-min demo script | ⬜ Not started (doc #7 in queue) | — |

**Rough overall completion: ~30% of the full capstone.** This is a
directional estimate, not precise — every stage built so far has taken
longer than originally planned due to real, unpredictable debugging
(see `decisions.md` D16-D18 for examples).

---

## 6. THE CURRENT TASK: Stage 4, production-shaped Step 5-6

### Why production-shaped (not the simpler original plan)

Originally planned: have `load_generator.py` record its own observations
of `order-svc`'s `cpu_pct`/`status` and feed that directly into
`anomaly_detector.py`. **Rejected** as architecturally biased — a real
service's telemetry should be independent of whoever is calling it, not
self-reported by the traffic generator. See `decisions.md` D20 for full
reasoning.

### The 6 phases to build

**Phase 1 — Deploy `order-svc` to Kubernetes, not `docker run`**
- Reuse Docker Desktop's local K8s (already enabled from Week 4's KEDA
  stretch goal).
- Write a `Deployment` + `Service` manifest for `order-svc`, similar
  shape to Week 4's `forecast-demo-app` placeholder Deployment.

**Phase 2 — Expose real Prometheus-format metrics**
- Current `/metrics` returns custom JSON (keep it — Stage 5 testing and
  manual `curl` checks still use it).
- **Add** a second endpoint (or convert `/metrics` to serve both) using
  the `prometheus_client` Python library: `order_svc_cpu_percent` (Gauge),
  `order_svc_requests_total{status}` (Counter), `order_svc_request_duration_seconds` (Histogram).

**Phase 3 — Point the existing Prometheus at it**
- Add a scrape target for `order-svc` to Prometheus's config — same
  mechanism as Week 4's `host.docker.internal` scrape setup for
  `emit_metric.py`.
- Verify via Prometheus's own targets page (already know how to do this
  from Week 4).

**Phase 4 — Query real data via PromQL instead of hand-aggregating**
- Replace `anomaly_detector.py`'s CSV-loading step with an HTTP call to
  Prometheus's query API (`/api/v1/query_range`), pulling real windowed
  aggregates.
- `fit_detector()` itself (from Week 5) stays **unchanged** — only the
  data source feeding it changes.

**Phase 5 — Grafana dashboard (confirmed included, not optional)**
- Live CPU/error-rate/latency panels during the incident — strong visual
  for the 15-min demo.

**Phase 6 — Everything downstream is unchanged**
- `alert_grouper.py`, `rca_agent.py`, writing the real
  `handoffs/stage4-incident.json`, and chaining into Stage 5's
  `remediation_agent.py` via `subprocess` — all identical to the
  already-planned design, just now fed by real Prometheus data instead
  of a hand-written fixture.

### What carries forward unchanged (nothing is discarded)

`app.py`'s core logic (CPU-bound work, error correlation, the race-condition
and CPU-metric fixes), the `Dockerfile`, the existing OTel spans (Step 3,
still valid, just secondary to Prometheus in this design), and
`load_generator.py` (still drives the same calm→spike→recovery pattern) —
**all kept exactly as-is**. Production-shaping is additive.

### Effort estimate

~4-6 hours for Phases 1-6, vs. ~1.5-2 hours for the simpler
already-rejected plan. Given no time constraint and that this reuses
Week 4's proven Prometheus/KEDA infrastructure, the extra time was judged
worthwhile.

---

## 7. Working conventions established this session (follow these)

- **Format:** plain fenced code blocks for all commands — NOT the
  numbered step-card widget (explicitly flagged as not copy-paste
  friendly; this is a stored preference).
- **Git discipline:** always `git status --ignored` before `git add`, to
  confirm nothing unexpected (especially `gcp-sa-key.json`, `venv-*/`) is
  about to be staged. Stage explicit file paths, never `git add .`.
- **Commit granularity:** one commit per logically distinct outcome/step,
  not batched. Small, standalone infra changes (`.gitignore` fixes) get
  their own commit separate from substantive work.
- **Verification discipline:** never trust an agent's claim of success —
  independently verify (`cat` the file, re-run the check, query the
  actual state) before moving on. This caught real bugs multiple times
  this session (see `decisions.md`).
- **Docker Desktop credential prompts:** if a `docker build` hangs on
  `[internal] load metadata for docker.io/...` for a long time, it's
  waiting on macOS Keychain access — click "Always Allow" on the dialog.
- **After `docker run -d`, add a short `sleep` before curling** — the
  container needs a moment to finish starting; hit one
  `Connection reset by peer` racing this.
- **Rebuild discipline:** only run `docker build` when `app.py`,
  `requirements.txt`, or the `Dockerfile` change — not for changes to
  files outside the image (e.g., `load_generator.py`).
- **Documentation discipline:** per-stage READMEs written immediately
  after each stage is verified (see `iac/README.md` as the template).
  `docs/decisions.md` updated continuously at each real decision point —
  do not defer big documentation to "the end."

---

## 8. Known limitations / honesty notes (for the report later)

- IaC's SLSA provenance is provenance-*shaped* but not independently
  *verifiable* — confirmed by running the real `slsa-verifier` CLI
  against it, which correctly failed (no signature, no Rekor entry).
- The IaC work runs against a single local project via manual Terraform,
  not a real CI/CD-triggered pipeline — that gap is intentionally closed
  later by Option B (GitHub Actions).
- Even production-shaped Stage 4 is a single-node local K8s (Docker
  Desktop) simulation, not a real multi-node cluster — worth stating
  plainly rather than implying more realism than exists.
- `psutil`-based CPU measurement inside containers has real, documented
  gotchas (see `decisions.md` D17) — worth keeping as a discussed finding,
  not hiding the debugging process.
- Two genuine, unstaged agent-behavior incidents were captured in the IaC
  lab (an unprompted `terraform apply` attempt; a correctly-refused
  prompt-injection sequence) — see `iac/README.md` for full detail. These
  are real evidence for the "Agent security and guardrails" rubric line.

---

## 9. Open items (unresolved)

- **PR from `capstone-option-c` to `main`:** not yet opened. Still
  undecided whether to open it now or after more of Option C lands.
- **Rubric-mapping table:** agreed to include in this document but not
  yet built — should map each capstone rubric line item (from the
  original Week 7 course doc) to the specific artifact/README/section
  that satisfies it. **TODO when resuming.**

---

## 10. How to resume

1. Confirm environment: `gcloud config list` (expect `cse636-capstone-iac`),
   `git status` / `git branch` (expect `capstone-option-c`, clean tree).
2. Read this document fully before taking any action.
3. Continue with Section 6 (Stage 4 production-shaped Step 5-6, Phase 1
   onward) unless told otherwise.
4. Update Section 5 (status table) and this document's "Last updated"
   line at the end of the session.
