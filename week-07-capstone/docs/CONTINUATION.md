# CSE636 Capstone — Continuation / Handoff Document

**Purpose:** paste this entire document into a new Claude chat to resume
work on this capstone with full context, without needing the original
(very long) conversation history. Keep this updated at the end of each
work session.

**Last updated:** after Stage 3 Phase 1 (`risk_scorer.py`) and Phase 2
(`canary_controller.py`) both built, tested, committed, and pushed
(`092a56e`, `ba3b082`). A real canary promote was executed against the
live cluster -- `order-svc-v2` is now the production deployment,
`order-svc` intentionally left at 0 replicas for rollback capability. Two
real bugs found and fixed during this work -- see `decisions.md` D28
(PromQL vector-matching bug) and D29 (canary-testing infrastructure: port-
forward load-balancing, sequential polling). A third finding, D30 (the
real `default`->`orders` namespace migration history), was added while
correcting `architecture.md`/`RUNBOOK.md` for accuracy. **Decision made:
submitting as-is at the current build level** -- Stage 3 Phases 3-4, full
5-stage wiring, and Options B/A are explicitly deferred, not silently
missing. **Next major work item: Documents 6/7 (capstone report, demo
script) -- not started.**

---

## 1. Project identity

- **Course:** CSE636 — DevOps for AI, CSTU, Prof. Qingsong Zhang
- **Repo:** `github.com/kuldeepjain1920/cse636-coursework`
- **Active branch:** `capstone-option-c`
- **This document covers:** the `week-07-capstone/` folder only (Weeks 0-6
  are complete and closed out separately)
- **Grading weight:** Capstone Project = 20% (tied with Final Exam as the
  largest single component — NOT a bonus)
- **Deadline posture:** not time-constrained; will submit whatever is
  ready by the weekend

---

## 2. Glossary / terminology

| Term | Meaning |
|---|---|
| `order-svc` | The fictional service being observed/remediated throughout Weeks 5-6 and now the capstone — a real Flask app, now deployed to Kubernetes (`orders` namespace) |
| `INC-002` | The specific incident ID (CPU saturation on `order-svc`) established in Week 5's synthetic data and Week 6's remediation agent; now reproduced with **real** Prometheus data in Stage 4 (note: Phase 6's live runs so far have produced `INC-001`/`INC-002` IDs generated fresh each run by `alert_grouper.py`, not literally the same incident) |
| Stage 1-5 | The capstone's 7-stage pipeline: Wk1 (autonomy levels, conceptual) → Wk2 (MCP/tools, conceptual) → **1** Agentic CI/CD (Wk3) → **2** Agentic IaC (Wk7 lab) → **3** Predictive deploy (Wk4) → **4** Observability (Wk5) → **5** Auto-remediation (Wk6) |
| Option C / B / A | Three orchestration approaches being built, in this order: **C** = heterogeneous platforms, file/subprocess handoffs (current focus); **B** = GitHub Actions as backbone (not started); **A** = single Python script (not started) |
| `capstone-option-c` | The git branch all Option C work lives on |
| Handoff file | `handoffs/stageN-output.json` — JSON audit-trail file each stage writes before invoking the next stage directly via `subprocess` |
| Blast-radius controls | The 4-5 automated safety gates in `remediation_agent.py` (kill switch, rate limit, error-budget gate, human approval) |
| `orders` namespace | K8s namespace holding `order-svc`'s Deployment + Service (moved off `default` during Phase 3 for realism — see D30 for the real migration history) |
| `monitoring` namespace | K8s namespace holding Prometheus (5 components) and Grafana |
| `resolved_no_action_needed` | The 4th `remediation_agent.py` outcome, added via the D27 fix — represents a dry-run-confirmed, correctly-no-op decision (distinct from `unresolved`, which still means "a scale was likely needed but never executed") |

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
| K8s cluster | Docker Desktop's built-in Kubernetes (`docker-desktop` context), single-node local cluster |
| Python venvs in use | `venv-week6` (repo root, `anthropic`+`python-dotenv`, used historically for Stage 5 standalone testing); `venv-order-svc` (inside `order-svc/`, `flask`+`psutil`+`opentelemetry-*`+`prometheus-client`+`requests`); `venv-anomaly-detector` (inside `observability/`, now has `requests`+`pandas`+`scikit-learn`+`anthropic`+`python-dotenv` — used for the ENTIRE Phase 4-6 chain including invoking `remediation_agent.py` via subprocess, since `subprocess.run([sys.executable, ...])` reuses whatever interpreter is currently active, AND for Stage 3's `risk_scorer.py`/`canary_controller.py`, which only need `requests`) |
| `order-svc` access | Deployed to K8s (`orders` namespace); reached locally via `kubectl port-forward -n orders svc/order-svc 8080:8080` (note: this port-forward pins to a single pod, not load-balanced — see D29 for why canary comparisons need in-cluster traffic instead) |
| Prometheus access | K8s Service `prometheus-server` in `monitoring` namespace; reached locally via `kubectl port-forward -n monitoring svc/prometheus-server 9090:80` |
| Grafana access | K8s Service `grafana` in `monitoring` namespace; reached locally via `kubectl port-forward -n monitoring svc/grafana 3000:80`; login `admin` / auto-generated password (retrieve via `kubectl get secret grafana -n monitoring -o jsonpath="{.data.admin-password}" \| base64 --decode`) |
| `.gitignore` (root) additions this project | `gcp-sa-key.json`, `tfplan.binary`, `tfplan.json`, `.terraform/`, `venv-*/` |
| ANTHROPIC_API_KEY | Loaded via `.env` at repo root (`~/cse636-coursework/.env`), found by `load_dotenv()` walking up from cwd |
| `order-svc` live deployment | `order-svc-v2` (NOT `order-svc`, which is intentionally at 0 replicas post-Phase-2-promote) |

**Known operational quirk:** closing Docker Desktop's dashboard *window*
does not fully quit it — its Virtualization.framework VM backend keeps
running (observed ~4.7GB RAM / 26% CPU) until quit via the menu bar whale
icon → **Quit Docker Desktop**. Check with `ps aux \| grep -i virtualization`
if unsure.

**Every-session operational sequence** (not one-time setup — needed each
time work resumes):
1. `kubectl cluster-info` — confirm Docker Desktop/K8s is up (wait
   ~1-3 min after opening Docker Desktop if it was closed)
2. `kubectl get pods -n orders` / `-n monitoring` — confirm `order-svc-v2`
   (NOT `order-svc` — see the live-deployment row above), Prometheus's 5
   components, and Grafana are all `Running`
3. Start the port-forwards needed for whatever you're doing (Prometheus
   for anything touching `anomaly_detector.py`/`alert_grouper.py`/
   `risk_scorer.py`; `order-svc` for `load_generator.py`; Grafana only if
   viewing the dashboard)
4. Activate the right venv — `venv-anomaly-detector` for anything in
   `observability/` or `predictive-deploy/` (covers Phase 4-6 plus
   Stage 3 Phases 1-2)

---

## 4. Repo structure (current state)

```
cse636-coursework/                          [repo root, branch: capstone-option-c]
├── .gitignore
├── .env                                    [gitignored — ANTHROPIC_API_KEY]
├── week-00 through week-06.../             [complete, closed out, not relevant here]
└── week-07-capstone/
    ├── docs/
    │   ├── decisions.md                    [D1 through D30 — D28/D29 committed; D30 (namespace
    │   │                                     migration) added, commit status: confirm]
    │   ├── CONTINUATION.md                 [this file]
    │   ├── architecture.md                 [FULLY UPDATED — new §6 (Stage 3 Phases 1-2), old §6/§7
    │   │                                     renumbered to §7/§8, rubric table + open items updated —
    │   │                                     pending local replace + commit]
    │   └── RUNBOOK.md                      [FULLY UPDATED — new §6 (Stage 3 Phases 1-2 commands),
    │   │                                     old §6 renumbered to §7, namespace note added to §5.1 —
    │   │                                     pending local replace + commit]
    └── orchestrator-c-heterogeneous/
        ├── handoffs/
        │   ├── stage3-risk.json            [Stage 3 Phase 1; overwritten each risk_scorer.py run,
        │   │                                 same convention as stage4/stage5]
        │   ├── stage3-canary.json          [Stage 3 Phase 2; overwritten each canary_controller.py
        │   │                                 run; current content reflects the REAL executed promote,
        │   │                                 dry_run: false]
        │   ├── stage4-incident.json        [now overwritten by REAL write_incident_handoff.py output,
        │   │                                 no longer the hand-written fixture]
        │   └── stage5-output.json          [overwritten each Stage 5 run]
        ├── iac/                            [DONE — Stage 2, full IaC lab]
        │   ├── gcs.tf
        │   ├── policy/gcs.rego
        │   ├── malicious_docs.txt
        │   ├── provenance.json
        │   ├── README.md
        │   └── gcp-sa-key.json             [gitignored]
        ├── remediation/                    [DONE — Stage 5 core build, incl. Phase 6's D27 fix]
        │   ├── remediation_agent.py        [D27 fix applied: added dry_run_called/dry_run_was_noop
        │   │                                 tracking, reclassifies outcome to resolved_no_action_needed
        │   │                                 when a dry-run genuinely confirmed no scale was needed]
        │   ├── README.md                   [DONE]
        │   └── itsm_tickets/
        │       ├── TICKET-4bcc5234.json    [remediated outcome — original Stage 5 standalone test]
        │       ├── TICKET-f80d6a13.json    [escalated_declined outcome — original Stage 5 standalone test]
        │       ├── TICKET-d0bd48bc.json    [escalated_kill_switch outcome — original Stage 5 standalone test]
        │       ├── TICKET-f764ae73.json    [real Phase 6 end-to-end ticket, PRE-D27-fix, outcome=unresolved
        │       │                             — kept as "before" evidence]
        │       └── TICKET-34cd34f0.json    [real Phase 6 end-to-end ticket, POST-D27-fix, same benign
        │                                     scenario re-run, outcome=resolved_no_action_needed — kept
        │                                     as "after" evidence]
        ├── k8s/                            [Stage 4 production-shaping, Phases 3-5]
        │   └── monitoring/
        │       ├── README.md               [reinstall steps, datasource setup, D24 summary]
        │       ├── prometheus-values.yaml  [scrape_interval: 5s, scrape_timeout: 4s — D24]
        │       ├── grafana-values.yaml     [admin password deliberately NOT hardcoded]
        │       └── dashboard-order-svc-incident.json  [exported "order-svc Incident Dashboard"]
        ├── predictive-deploy/              [Stage 3 Phases 1-2, DONE]
        │   ├── risk_scorer.py              [Phase 1; real CPU%/error rate (Prometheus instant query),
        │   │                                 real OPA/conftest result (fresh terraform plan each run),
        │   │                                 real replica count via kubectl; D28 fix applied
        │   │                                 (sum()-wrapped error-rate query + NaN guard);
        │   │                                 DEPLOYMENT_NAME points at order-svc-v2 post-promote]
        │   └── canary_controller.py        [Phase 2; polls v1/v2 concurrently within one shared
        │   │                                 window (D29 fix); real promote executed —
        │   │                                 order-svc-v2 now live, order-svc at 0 replicas]
        └── observability/                  [Stage 4 — Steps 1-4 done, production-shaping Phases 1-6 DONE]
            ├── load_generator.py           [DONE — Step 4; BASE_URL still hardcoded to localhost:8080,
            │                                 relies on the order-svc port-forward being open]
            ├── requirements.txt             [UPDATED Phase 6 — now requests, pandas, scikit-learn,
            │                                 anthropic, python-dotenv (last two added for rca_agent.py)]
            ├── anomaly_detector.py         [Phase 4; standalone, does NOT import from week-05/;
            │                                 fetch_real_metrics() queries Prometheus via PromQL;
            │                                 fit_detector()/FEATURE_COLUMNS copied verbatim from Week 5;
            │                                 D28 fix applied to error-rate query]
            ├── alert_grouper.py            [Phase 6; standalone copy of week-05/src/alert_grouper.py's
            │                                 group_alerts() logic, unchanged, does NOT import from week-05/]
            ├── rca_agent.py                [Phase 6; NOT a copy of Week 5's rca_agent.py — makes a
            │                                 REAL Claude API call (Week 5's version used simulated if/else
            │                                 threshold logic since no API key was available there;
            │                                 here one is, so this is a deliberate upgrade, not a copy)]
            ├── write_incident_handoff.py   [Phase 6; maps real Incident + rca dict into
            │                                 remediation_agent.py's exact expected schema, queries
            │                                 current_replicas live via kubectl, hardcodes
            │                                 max_replicas/target_cpu_pct/error_budget_remaining as
            │                                 explicit placeholder constants (D25), then subprocess-chains
            │                                 into remediation_agent.py with cwd="../remediation" (D26)]
            ├── output/                     [rca_report_INC-*.md files, human-readable RCA reports]
            ├── venv-anomaly-detector/       [gitignored — dedicated venv, covers the whole Phase 4-6 chain
            │                                 plus Stage 3 Phases 1-2]
            ├── README.md                    [Step 4 era; could use a Phase 1-6 addendum — not blocking]
            └── order-svc/                  [DONE — Steps 1-3, Phases 1-2; v1/v2 canary added Stage 3]
                ├── app.py                  [v1; UPDATED Stage 3 — VERSION env var, all 3 Prometheus
                │                             metrics now labeled by version]
                ├── app_v2.py                [v2; identical to app.py except cpu_bound_work() does
                │                             100_000 iterations vs v1's 200_000 — the real canary diff]
                ├── requirements.txt         [UPDATED — added prometheus-client]
                ├── k8s/
                │   ├── deployment.yaml     [v1; image order-svc:v1, env VERSION=v1]
                │   └── deployment-v2.yaml  [v2; image order-svc:v2, env VERSION=v2; no Service —
                │                             shares v1's existing Service selector]
                ├── Dockerfile               [v1]
                ├── Dockerfile.v2            [v2; copies app_v2.py in as app.py]
                ├── .dockerignore
                └── venv-order-svc/          [gitignored]
```

---

## 5. Status by capstone component

| Component | Status | Commit(s) |
|---|---|---|
| Capstone planning | ✅ Done | n/a |
| Stage 2 (IaC lab) | ✅ Done, fully verified incl. SLSA + real bugs found | `1c7e2b2`, `c4580c3` |
| Stage 5 (auto-remediation) core build | ✅ Done, 4 outcome paths verified (incl. Phase 6's `resolved_no_action_needed`) | `3f5364b`, `baac52c`, `be3f793`, `28c684f` |
| Stage 4 Steps 1-4 (service, container, OTel, load gen) | ✅ Done | `1583769`, `b09ed39`, `369b86c`, `cac93c9` |
| Stage 4 production-shaping Phase 1 (K8s Deployment) | ✅ Done | `65c2c9f` |
| Stage 4 production-shaping Phase 2 (Prometheus metrics endpoint) | ✅ Done | `45abc42` |
| Stage 4 production-shaping Phase 3 (real Prometheus scrape target, `orders` namespace move) | ✅ Done | `4c27706` |
| Stage 4 production-shaping Phase 4 (PromQL-based anomaly detection) | ✅ Done — real findings D22, D23 | `8f57509` |
| Stage 4 production-shaping Phase 5 (Grafana dashboard) | ✅ Done — real finding D24 | `92adf5b` |
| **Stage 4 Phase 6 (chain into Stage 5)** | ✅ **Done — built, verified end-to-end multiple times, all 3 design questions resolved, D25-D27 written and inserted, committed** | `28c684f` |
| **Stage 4 — entire production-shaping arc (Phases 1-6)** | ✅ **Fully complete and committed** | — |
| Stage 3 (predictive deploy) | 🔶 Phases 1-2 done (risk_scorer.py, canary_controller.py); real canary promote executed, order-svc-v2 now live; Phases 3-4 not started, deferred per submission-scope decision (§10) | `76320fd`, `092a56e`, `ba3b082` |
| Wiring all 5 stages end-to-end | 🔶 Stages 4→5 chained (Phase 6); Stage 3 Phases 1-2 built standalone, real promote executed, not yet wired into the full pipeline — deferred per submission-scope decision (§10) | — |
| Option B (GitHub Actions) | ⬜ Not started, deferred per submission-scope decision (§10) | — |
| Option A (single script) | ⬜ Not started, deferred per submission-scope decision (§10) | — |
| `docs/decisions.md` (doc 1) | ✅ D1-D30 — D28/D29 committed; D30 added, commit status: confirm | `be01265` (original), updated continuously, D25-D27 via `28c684f` |
| `docs/CONTINUATION.md` (doc 2) | ✅ Done, kept updated | `22fdcb4` (original), this revision pending commit |
| `docs/architecture.md` (doc 3) | ✅ **Fully updated** with new §6 (Stage 3), renumbered §7/§8 — pending local replace + commit | `057d023` (original) |
| `docs/RUNBOOK.md` (doc 4) | ✅ **Fully updated** with new §6 (Stage 3 commands), renumbered §7 — pending local replace + commit | `12026e9` (original) |
| Per-stage READMEs — `observability/`, `remediation/` (doc 5) | ✅ Done for Steps 1-4 era; `observability/README.md` could use a Phase 1-6 addendum (not blocking) | `1e19da2` |
| `k8s/monitoring/README.md` | ✅ Done | `92adf5b` |
| Capstone report (doc 6, 4-6pp) | ⬜ **Not started** — resume now, against current build scope (§10) | — |
| 15-min demo script (doc 7) | ⬜ **Not started** — resume now, against current build scope (§10) | — |

**Rough overall completion: directionally higher than the ~30-35%
estimated earlier.** Stage 4's entire production-shaping arc (Phases 1-6)
is now fully done, verified, and committed. Stage 3 Phases 1-2 are also
done, including a real executed canary promote. Not re-estimated
precisely; every phase took longer than planned due to real,
unpredictable debugging (see `decisions.md`), and Stage 3 was no
exception (three real findings: D28's PromQL vector-matching bug, D29's
two canary-testing infrastructure bugs, D30's namespace-migration
history — all resolved or documented).

---

## 6. Phase 6's design questions — all resolved

These were the open items blocking Phase 6's commit; all three are now
decided and documented:

1. **Should `execute_scale` become real** (calling `kubectl scale
   deployment` instead of only updating in-memory state)? **Deferred.**
   Low risk, already honestly documented as simulated via D26; making it
   real would expand Stage 5's already-verified scope beyond this
   capstone's current arc.
2. **Should Stage 5's outcome taxonomy be expanded**? **Fixed now.**
   Added `dry_run_called`/`dry_run_was_noop` tracking to
   `remediation_agent.py`'s `run_remediation()`; `outcome` is reclassified
   to `resolved_no_action_needed` only when a dry-run genuinely confirmed
   no scale was needed — deliberately does NOT reclassify cases where a
   real scale was recommended but `execute_scale` was never called (that
   correctly stays `unresolved`, preserving the Week 6 tool-avoidance-bug
   signal). Verified: re-ran the same benign incident scenario post-fix,
   got `resolved_no_action_needed` instead of `unresolved`
   (`TICKET-34cd34f0.json` vs. the pre-fix `TICKET-f764ae73.json`).
3. **Should Phase 6's chain be containerized** (closing D22's original
   plan)? **Deferred**, same reasoning as #1 — an infrastructure-realism
   improvement, not a correctness fix; the chain's correctness has
   already been proven via `kubectl port-forward`.

### What's been built and verified (all of Phases 1-6)

- **Phase 1:** `order-svc` deployed to Docker Desktop's K8s, moved to its
  own `orders` namespace for realism.
- **Phase 2:** `app.py` exposes a real Prometheus-format
  `/metrics/prometheus` endpoint via `prometheus_client` — the original
  custom JSON `/metrics` endpoint is untouched and still used by Stage 5.
- **Phase 3:** A real Prometheus instance scrapes `order-svc` via
  `prometheus.io/*` Service annotations.
- **Phase 4:** `anomaly_detector.py` queries Prometheus's `query_range`
  API via PromQL, feeding real data into the unchanged `fit_detector()`
  (IsolationForest) logic from Week 5. Real findings: **D22** (local dev
  via `kubectl port-forward`, explicitly not production-realistic —
  deliberately left as-is, see §6 above); **D23** (IsolationForest can
  miss a sustained incident once `rate()`'s 5-minute smoothing duplicates
  readings across several consecutive points).
- **Phase 5:** A Grafana dashboard with 3 panels (CPU %, Error Rate, p99
  Latency), verified showing a real correlated incident. Real finding:
  **D24** (Prometheus's default 60s scrape interval was too coarse for
  brief Gauge-based spikes; fixed by reducing to 5s/4s timeout, plus an
  explicit rollout restart). `k8s/monitoring/` holds the Helm values and
  exported dashboard JSON for fresh-clone reproducibility.
- **Phase 6:** Built and committed the full real chain:
  - `alert_grouper.py` — standalone copy of Week 5's `group_alerts()`
    logic (unchanged), groups `anomaly_detector.py`'s flagged rows into
    `Incident` objects via a time-gap rule.
  - `rca_agent.py` — **NOT** a copy of Week 5's version. Week 5's used
    simulated `if/else` threshold logic because no API key was available
    there; here `ANTHROPIC_API_KEY` genuinely works (already proven by
    `remediation_agent.py`), so this makes a real Claude API call,
    reasoning from the incident's actual `peak_metrics`.
  - `write_incident_handoff.py` — maps the real `Incident` + real `rca`
    dict into `remediation_agent.py`'s exact expected schema
    (`cpu_utilization_pct`/`p99_latency_ms` renames,
    `current_replicas` queried live via `kubectl get deployment`,
    `max_replicas`/`target_cpu_pct`/`error_budget_remaining` as explicit
    placeholder constants — **D25**), writes the real
    `handoffs/stage4-incident.json`, then `subprocess`-chains into
    `remediation_agent.py` with `cwd="../remediation"` (**D26** fix).
  - Ran the full chain successfully multiple times against real,
    live-generated `load_generator.py` incidents:
    - One run produced a genuinely complete, correlated incident
      (CPU 103.8%, error_rate 1.0, latency 993ms) → correct RCA → agent
      reasoned through dry-run → scale approved → `outcome: "remediated"`.
    - A second run produced a genuinely benign, low-impact incident
      (CPU 9.9%, 0 errors, 0ms extra latency). Pre-D27-fix, this fell
      through to `outcome: "unresolved"` despite the agent's sound
      reasoning; post-fix, correctly reclassified as
      `resolved_no_action_needed` (**D27**).
  - Cleaned up: deleted the stray pre-`cwd`-fix ticket
    (`TICKET-4987e34e.json`, which had landed in the wrong
    `observability/itsm_tickets/` directory) and its now-empty
    directory. Kept `TICKET-f764ae73.json` (pre-D27-fix) and
    `TICKET-34cd34f0.json` (post-D27-fix) as before/after evidence.
  - Committed everything in `28c684f`: `docs/CONTINUATION.md`,
    `docs/decisions.md` (D25-D27), `handoffs/stage4-incident.json` +
    `stage5-output.json`, `observability/requirements.txt`,
    `remediation/remediation_agent.py` (D27 fix), `alert_grouper.py`,
    `rca_agent.py`, `write_incident_handoff.py`, `observability/output/`,
    both kept ITSM tickets.

### What carries forward unchanged (nothing is discarded)

`app.py`'s core logic, the `Dockerfile`, `fit_detector()`/`FEATURE_COLUMNS`
in `anomaly_detector.py`, `group_alerts()` in `alert_grouper.py`,
`load_generator.py`'s calm→spike→recovery pattern, and
`remediation_agent.py`'s ReAct loop and blast-radius gates (only its
outcome-classification logic changed, via the D27 fix — the core
remediation flow was NOT modified by Phase 6).

---

## 7. Stage 3 — Predictive Deploy: Phases 1-2 Done, Phases 3-4 Not Yet Built

**Status:** Phase 1 (`risk_scorer.py`) and Phase 2 (`canary_controller.py`)
built, verified, and committed (`76320fd`, `092a56e`, `ba3b082`). A real canary
promote was executed (not simulated) -- v2 (half the hashing work of v1,
a genuine perf change) was compared against v1 over a live, concurrent
Prometheus-sampled window, decided `promote` on real CPU/error-rate data,
and the decision was actually carried out: `order-svc` scaled to 0
replicas, `order-svc-v2` scaled to 1 and now serving all traffic.

**`order-svc-v2` is the ongoing production deployment going forward** --
`order-svc` (the original) is intentionally left at 0 replicas rather than
deleted, preserving rollback capability, but is not the live service.
`risk_scorer.py`'s `DEPLOYMENT_NAME` was updated from `"order-svc"` to
`"order-svc-v2"` to reflect this -- **important**: don't assume
`order-svc` at 0 replicas means something is broken when resuming a
session; this is the correct post-promote state.

Two real bugs were found and fixed during Phase 1-2 testing -- see
`decisions.md` D28 (PromQL vector-matching bug in the shared error-rate
query, affecting both `risk_scorer.py` and `anomaly_detector.py`) and D29
(two canary-testing infrastructure bugs: `kubectl port-forward` to a
Service doesn't load-balance, and `canary_controller.py` originally
polled v1/v2 sequentially rather than concurrently -- both fixed). A
third finding, D30, documents the real `default`->`orders` namespace
migration history surfaced while correcting `architecture.md`/
`RUNBOOK.md` for accuracy -- not a Stage 3 bug, but logged alongside
these since it was found during the same doc-correction pass.

Writes `handoffs/stage3-risk.json` (overwritten each run, same convention
as `stage4-incident.json`/`stage5-output.json`).

**Decision: Phases 3-4 are deferred, not resumed.** Submitting as-is at
this build level -- see §10.

### What's being risk-scored
**Option A chosen:** Stage 3 risk-scores a deploy of `order-svc` itself
(the same real, already-running K8s service from Stage 4) — not Stage
2's Terraform/GCS change, and not a synthetic fictional service. This
was chosen over scoring the Terraform plan (too abstract, Stage 2's real
change is low-risk and gives little signal) or a fully synthetic
scenario (disconnects Stage 3 from the rest of the pipeline). Scoring
`order-svc` keeps Stage 3 connected to both Stage 2 (before) and Stage 4
(after) in the real pipeline.

### Risk score inputs — all real, no synthetic inputs
- Real current `order-svc` CPU % and error rate, pulled from Prometheus
  (reuses Stage 4's existing PromQL infrastructure).
- Real Stage 2 OPA/`conftest` policy pass/fail result.
- Real current replica count, via `kubectl get deployment`.
No fabricated inputs (e.g. no fake "code complexity" score) — every
input is something the pipeline can already actually measure.

### Canary decision — Option B chosen (real, not just a recommendation)
A genuinely real canary requires `order-svc` to have an actual "v2" to
compare against v1 — otherwise there's nothing to canary test. Built:
- `VERSION` env var added to `app.py`/`app_v2.py`, exposed as a label on
  all 3 Prometheus metrics, so v1 and v2 traffic can be told apart.
- Separate `order-svc:v1`/`order-svc:v2` images (not a shared image with
  a runtime flag) — v2's only real difference is `cpu_bound_work()`
  doing `100_000` hashing iterations vs. v1's `200_000`, a genuine
  performance change, not a cosmetic label swap.
- `canary_controller.py` deploys v2 at a small replica count alongside
  v1 (same Service/label selector — standard manual-canary pattern),
  polls Prometheus over a shared window comparing v2's error rate/CPU
  against v1's baseline, then either promotes (scale v2 up, v1 down) or
  rolls back (delete v2, keep v1) — a real decision based on real
  comparative data, not simulated. **A real promote was executed** — see
  Status above.

### FinOps cost estimate — real Billing API, with an honest scope limit (not built)
**Important, deliberate limitation:** `order-svc` runs on local Docker
Desktop Kubernetes, which GCP does NOT actually bill. The only real,
actually-provisioned-and-billed GCP resource in this whole capstone is
Stage 2's GCS bucket. So, if built:
- `cost_estimator.py` would call the REAL Google Cloud Billing Catalog API
  for GCS pricing SKUs, and compute a real estimated monthly cost for
  Stage 2's actual bucket configuration.
- This estimate deliberately would NOT cover `order-svc` — inventing a
  hypothetical cloud runtime for it just to produce a number would
  reintroduce the same kind of unlabeled fakery this design is trying to
  avoid by going real.

### Phase breakdown
- **Phase 1 — Real risk score. ✅ Done.** `risk_scorer.py`: pulls the 3 real
  inputs above, combines into a risk score + a proceed/block gate
  decision. Writes `handoffs/stage3-risk.json`.
- **Phase 2 — Real canary. ✅ Done.** `VERSION` env var + Prometheus label
  added to `app.py`/`app_v2.py`; separate v1/v2 images built
  (`order-svc:v1`, `order-svc:v2`); `canary_controller.py` deploys,
  compares v1/v2 concurrently over a shared window, and promotes/rolls
  back based on real data. A real promote was executed; `order-svc-v2` is
  now the live deployment. Writes `handoffs/stage3-canary.json`.
- **Phase 3 — Real FinOps.** ⬜ **Not started, deferred** — see §10.
- **Phase 4 — Wire it together.** ⬜ **Not started, deferred** — see §10.

**Next immediate action when resuming:** not Stage 3 Phase 3 — per the
submission-scope decision (§10), the next actual work is Documents 6/7
(capstone report, demo script), written honestly against the current
build (Stages 2/4/5 complete, Stage 3 Phases 1-2 complete with a real
executed promote, Phases 3-4 and Options B/A explicitly deferred).

---

## 8. Working conventions established (follow these)

- **Format:** plain fenced code blocks for all commands — NOT the
  numbered step-card widget (explicitly flagged as not copy-paste
  friendly; this is a stored preference).
- **No shortcuts:** when a command has a "fast/simplified" version and a
  "full/correct" version (e.g. hardcoding a password vs. retrieving an
  auto-generated one), default to the correct version unless explicitly
  told time is tight.
- **Git discipline:** always `git status --ignored` before `git add`, to
  confirm nothing unexpected (especially `gcp-sa-key.json`, `venv-*/`) is
  about to be staged. Stage explicit file paths, never `git add .`.
- **Commit granularity:** one commit per logically distinct outcome/step,
  not batched. Small, standalone infra changes get their own commit
  separate from substantive work.
- **Verification discipline:** never trust a claim of success —
  independently verify (`cat` the file, re-run the check, query the
  actual state, check raw API responses rather than trusting a UI, `find`
  a file to confirm where it actually landed) before moving on. This
  caught real bugs multiple times (D22-D30 all came from this habit).
- **`week-05/` and `week-06-assignment/` are read-only reference material**
  — never edit or import from them directly. Reusable logic gets copied
  into new standalone files under `week-07-capstone/`, with a comment
  noting what was carried over unchanged vs. deliberately changed (see
  `anomaly_detector.py`/`alert_grouper.py` for "copied unchanged," and
  `rca_agent.py` for "deliberately upgraded, not copied").
- **Explicit `cd` before commands** — don't assume the working directory;
  state it or confirm with `pwd` first. (This exact class of mistake
  caused the D26 `cwd` bug in `subprocess.run()` — worth remembering
  subprocess calls need the same discipline as manual `cd`s.)
- **Reproducibility over live-only cluster state:** Helm `--set` flags
  used ad hoc during a session should get captured into a `*-values.yaml`
  file and committed once the config is confirmed working (see
  `k8s/monitoring/`), rather than left only as invisible cluster state.
- **Requirements files must be checked against `pip freeze`, not
  eyeballed** — compare what's actually imported in the code against
  what's listed, since packages installed ad hoc mid-session are easy to
  forget adding to `requirements.txt` (caught exactly this for
  `anthropic`/`python-dotenv` in `observability/requirements.txt`).
- **Docker Desktop credential prompts:** if a `docker build` hangs on
  `[internal] load metadata for docker.io/...`, it's waiting on macOS
  Keychain access — click "Always Allow."
- **After `docker run -d` or a K8s pod (re)start, add a short pause
  before curling** — hit real `Connection reset by peer` races otherwise.
- **Rebuild discipline:** only run `docker build` when `app.py`,
  `requirements.txt`, or the `Dockerfile` change — not for changes to
  files outside the image. K8s `imagePullPolicy: Never` means a rebuilt
  image needs `kubectl rollout restart deployment/order-svc` to actually
  be picked up. A ConfigMap change needs the same — `kubectl
  apply`/`helm upgrade` alone does not make a running pod re-read its
  config; an explicit rollout restart is required.
- **In-cluster traffic vs. local port-forward for multi-pod comparisons:**
  `kubectl port-forward` to a Service pins to one backing pod, not
  load-balanced — fine for single-target scripts (`risk_scorer.py`,
  `anomaly_detector.py`), but wrong for anything comparing two pods
  (canary testing). Use a throwaway in-cluster `kubectl run` pod instead
  when real load-balanced traffic is required (D29).
- **Documentation discipline:** per-stage READMEs written immediately
  after each stage is verified. `docs/decisions.md` updated continuously
  at each real decision point — including genuinely surprising findings
  discovered while testing. Big synthesis documents (the report, the
  demo script) are being written now, against current build scope — see
  §10.

---

## 9. Known limitations / honesty notes (for the report later)

- IaC's SLSA provenance is provenance-*shaped* but not independently
  *verifiable* — confirmed by running the real `slsa-verifier` CLI
  against it, which correctly failed (no signature, no Rekor entry).
- The IaC work runs against a single local project via manual Terraform,
  not a real CI/CD-triggered pipeline — that gap is intentionally closed
  later by Option B (GitHub Actions), which is deferred for this
  submission (§10).
- Even production-shaped Stage 4 is a single-node local K8s (Docker
  Desktop) simulation, not a real multi-node cluster.
- `psutil`-based CPU measurement inside containers has real, documented
  gotchas (see `decisions.md` D17).
- Two genuine, unstaged agent-behavior incidents were captured in the IaC
  lab (an unprompted `terraform apply` attempt; a correctly-refused
  prompt-injection sequence) — see `iac/README.md`.
- IsolationForest (contamination=0.04) reliably flags brief, isolated
  anomalies but was observed to MISS a genuine 5-point cluster of
  identical extreme values in real Prometheus data — a direct
  consequence of `rate()`'s 5-minute smoothing. Documented in `decisions.md`
  D23. Not fixed — deliberately left as a documented detector limitation.
- `anomaly_detector.py` (and the whole Phase 6 chain) reaches
  Prometheus/`order-svc` via `kubectl port-forward` for local
  development, which is explicitly NOT production-realistic. D22
  originally floated containerizing this — deliberately deferred (see §6
  #3), since the chain's correctness has now been proven end-to-end and
  containerizing is an infrastructure-realism improvement, not a
  functional gap.
- Prometheus's scrape interval (originally 60s) was too coarse to
  reliably observe short-lived Gauge-based metrics — fixed by reducing
  to 5s (`decisions.md` D24).
- Stage 4's real telemetry can be genuinely measured, but Stage 5's
  `remediation_agent.py` also needs autoscaling-policy inputs
  (`max_replicas`, `target_cpu_pct`, `error_budget_remaining`) that don't
  correspond to anything configured in the cluster yet, since Stage 3's
  autoscaling policy layer (Phase 3, deferred) was never built. Phase 6
  hardcodes these as clearly-labeled placeholder constants
  (`decisions.md` D25).
- **`remediation_agent.py`'s `execute_scale` has always been simulated**
  — it updates only its own in-memory `state` dict, never calls `kubectl
  scale`. True since Stage 5's original build (before Phase 6 existed),
  only now visible against real K8s infrastructure for the first time
  (`decisions.md` D26). A "remediated" outcome currently does not change
  the actual Deployment's replica count. Deliberately left this way (see
  §6 #1). **Contrast:** Stage 3's `canary_controller.py` does the
  opposite — its `kubectl scale`/`kubectl delete` calls are real, not
  simulated (see §7 and D29's verification).
- **`remediation_agent.py`'s outcome taxonomy previously had no
  representation for "the agent correctly determined no action was
  needed."** A real, benign incident (CPU 9.9%, zero errors, zero extra
  latency) initially produced a sound `dry_run_scale`-informed decision
  to take no action, but fell through to the default `unresolved`
  outcome. **This has been fixed** (`decisions.md` D27) — a new
  `resolved_no_action_needed` outcome is now correctly assigned when a
  dry-run genuinely confirms no scale is warranted, verified against the
  same real scenario.
- **The shared error-rate PromQL query had a real vector-matching bug**
  (`decisions.md` D28) — Prometheus's default division matching silently
  paired only the identical `status="500"` series, dropping
  `status="200"` from the denominator entirely, so the query never
  computed a real error ratio. Fixed via `sum()`-wrapping in both
  `risk_scorer.py` and `anomaly_detector.py`, plus an explicit
  `math.isnan()` guard so a NaN can never again silently default a gate
  decision to `"proceed"`.
- **`kubectl port-forward` to a Service does not load-balance** across
  backing pods — it pins to one (`decisions.md` D29). This broke the
  first real canary test (v2 read exactly `0.0` — genuinely zero
  traffic, not "healthier"), fixed by generating comparison traffic from
  inside the cluster instead.
- **A related bug in `canary_controller.py` itself:** the original
  version polled v1 and v2 in two separate sequential ~60s windows, not
  concurrently — meaning the two versions were compared against two
  different slices of real time, not fair same-conditions data
  (`decisions.md` D29). Fixed by sampling both versions together at each
  timestamp within one shared window.
- **`order-svc` was originally deployed into the `default` namespace**
  (per the original Week 7 lab instructions), then deliberately moved
  into `orders` for realism — Kubernetes namespace is immutable on an
  existing object, so this required deleting and recreating the
  Deployment/Service, not an in-place edit (`decisions.md` D30). Not a
  bug, but `RUNBOOK.md`/`architecture.md` previously described the
  `orders` deployment as if it had always been the direct target; both
  have been corrected.
- **Stage 3 Phases 3-4, full 5-stage wiring, and Options B/A are
  deliberately not built for this submission** — a conscious scope
  decision (§10), not an oversight. The report and demo script must
  state this plainly.

---

## 10. Open items (unresolved)

- **PR from `capstone-option-c` to `main`:** not yet opened.
- **Submission scope, decided:** submitting as-is at the current build
  level — Stage 2, Stage 4 (all 6 phases), Stage 5, and Stage 3 Phases
  1-2 (including a real executed canary promote) are complete. Stage 3
  Phases 3-4, full 5-stage wiring, and Options B/A are explicitly
  deferred, not silently missing — Documents 6/7 (below) must state this
  scope honestly rather than waiting for those to exist.
- **Documents 6 and 7 (capstone report, demo script):** not yet started.
  Given the submission-scope decision above, these should now be written
  against the current build (not deferred further waiting on Stage 3
  Phases 3-4/Option B, which was the original gating condition).
- **`docs/architecture.md`:** updated with a new §6 (Stage 3 Phases 1-2),
  renumbered rubric table (§7) and open-items (§8) — pending local
  replace + commit.
- **`docs/RUNBOOK.md`:** updated with a new §6 (Stage 3 Phases 1-2
  commands), old §6 renumbered to §7 — pending local replace + commit.
- **`docs/decisions.md` D30:** namespace migration finding (default ->
  orders required delete-and-recreate) — added to the file; commit
  status: confirm.
- **Grafana dashboard's default time range** is still "Last 5 minutes" —
  worth broadening before any actual demo.
- **`observability/README.md`** is still Step 4-era and could use a
  Phase 1-6 addendum — not blocking, low priority.
- **Stage 3 Phases 3-4** (FinOps `cost_estimator.py`, orchestrator
  wiring `handoffs/stage3-output.json`) — not started; deferred per the
  submission-scope decision above.

---

## 11. How to resume

1. Confirm environment (see §3's "every-session operational sequence").
   Remember: `order-svc-v2` is the live deployment, `order-svc` at 0
   replicas is expected, not broken.
2. Read this document fully before taking any action.
3. Confirm/replace local `docs/architecture.md`, `docs/RUNBOOK.md`, and
   `docs/decisions.md` (D30) with their updated versions if not already
   committed, and commit them:
   ```bash
   cd ~/cse636-coursework/week-07-capstone
   git status --ignored docs/
   git add docs/architecture.md docs/RUNBOOK.md docs/decisions.md
   git commit -m "Update architecture.md, RUNBOOK.md for Stage 3 Phases 1-2; add D30 (namespace migration)"
   git push origin capstone-option-c
   ```
4. Move on to **Documents 6 and 7** (capstone report, demo script) — per
   the submission-scope decision (§10), Stage 3 Phases 3-4 are
   deliberately deferred, not the next task. Write both against the
   current, real build: Stages 2/4/5 complete, Stage 3 Phases 1-2
   complete with a real executed canary promote, D22-D30 as honest
   lessons-learned material, Phases 3-4/Options B/A stated plainly as
   out of scope for this submission.
5. Update §5 (status table) and this document's "Last updated" line at
   the end of the session. If new documents or files get committed,
   update §4 (repo structure) too.
