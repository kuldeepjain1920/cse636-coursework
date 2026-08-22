# CSE636 Capstone — Continuation / Handoff Document

**Purpose:** paste this entire document into a new Claude chat to resume
work on this capstone with full context, without needing the original
(very long) conversation history. Keep this updated at the end of each
work session.

**Last updated:** after building and successfully test-running Stage 4
Phase 6's full chain (`anomaly_detector.py` → `alert_grouper.py` →
`rca_agent.py` → `write_incident_handoff.py` → `remediation_agent.py`)
end-to-end multiple times against real data, with real `remediated` and
`unresolved` outcomes observed. D25-D27 are drafted but not yet inserted
into `decisions.md`; nothing from Phase 6 is committed to git yet.
Documents 6 (capstone report) and 7 (demo script) still deliberately
deferred — see §9.

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
| `orders` namespace | K8s namespace holding `order-svc`'s Deployment + Service (moved off `default` during Phase 3 for realism) |
| `monitoring` namespace | K8s namespace holding Prometheus (5 components) and Grafana |

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
| Python venvs in use | `venv-week6` (repo root, `anthropic`+`python-dotenv`, used historically for Stage 5 standalone testing); `venv-order-svc` (inside `order-svc/`, `flask`+`psutil`+`opentelemetry-*`+`prometheus-client`+`requests`); `venv-anomaly-detector` (inside `observability/`, now has `requests`+`pandas`+`scikit-learn`+`anthropic`+`python-dotenv` — used for the ENTIRE Phase 4-6 chain including invoking `remediation_agent.py` via subprocess, since `subprocess.run([sys.executable, ...])` reuses whatever interpreter is currently active) |
| `order-svc` access | Deployed to K8s (`orders` namespace); reached locally via `kubectl port-forward -n orders svc/order-svc 8080:8080` |
| Prometheus access | K8s Service `prometheus-server` in `monitoring` namespace; reached locally via `kubectl port-forward -n monitoring svc/prometheus-server 9090:80` |
| Grafana access | K8s Service `grafana` in `monitoring` namespace; reached locally via `kubectl port-forward -n monitoring svc/grafana 3000:80`; login `admin` / auto-generated password (retrieve via `kubectl get secret grafana -n monitoring -o jsonpath="{.data.admin-password}" \| base64 --decode`) |
| `.gitignore` (root) additions this project | `gcp-sa-key.json`, `tfplan.binary`, `tfplan.json`, `.terraform/`, `venv-*/` |
| ANTHROPIC_API_KEY | Loaded via `.env` at repo root (`~/cse636-coursework/.env`), found by `load_dotenv()` walking up from cwd |

**Known operational quirk:** closing Docker Desktop's dashboard *window*
does not fully quit it — its Virtualization.framework VM backend keeps
running (observed ~4.7GB RAM / 26% CPU) until quit via the menu bar whale
icon → **Quit Docker Desktop**. Check with `ps aux \| grep -i virtualization`
if unsure.

**Every-session operational sequence** (not one-time setup — needed each
time work resumes):
1. `kubectl cluster-info` — confirm Docker Desktop/K8s is up (wait
   ~1-3 min after opening Docker Desktop if it was closed)
2. `kubectl get pods -n orders` / `-n monitoring` — confirm `order-svc`,
   Prometheus's 5 components, and Grafana are all `Running`
3. Start the port-forwards needed for whatever you're doing (Prometheus
   for anything touching `anomaly_detector.py`/`alert_grouper.py`;
   `order-svc` for `load_generator.py`; Grafana only if viewing the
   dashboard)
4. Activate the right venv — `venv-anomaly-detector` for anything in
   `observability/` (covers the whole Phase 4-6 chain now)

---

## 4. Repo structure (current state)

```
cse636-coursework/                          [repo root, branch: capstone-option-c]
├── .gitignore
├── .env                                    [gitignored — ANTHROPIC_API_KEY]
├── week-00 through week-06.../             [complete, closed out, not relevant here]
└── week-07-capstone/
    ├── docs/
    │   ├── decisions.md                    [D1 through D24 committed; D25-D27 drafted, NOT yet inserted]
    │   ├── CONTINUATION.md                 [this file]
    │   ├── architecture.md                 [§5b needs a small update — still says "being upgraded"]
    │   └── RUNBOOK.md                      [Sections 0-4 + 6 done; Section 5 still a placeholder]
    └── orchestrator-c-heterogeneous/
        ├── handoffs/
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
        ├── remediation/                    [DONE — Stage 5 core build]
        │   ├── remediation_agent.py        [UNCHANGED by Phase 6 -- same code, now invoked
        │   │                                 for real by write_incident_handoff.py]
        │   ├── README.md                   [DONE]
        │   └── itsm_tickets/
        │       ├── TICKET-4bcc5234.json    [remediated outcome — original Stage 5 standalone test]
        │       ├── TICKET-f80d6a13.json    [escalated_declined outcome — original Stage 5 standalone test]
        │       ├── TICKET-d0bd48bc.json    [escalated_kill_switch outcome — original Stage 5 standalone test]
        │       └── TICKET-f764ae73.json    [NEW — first real Phase 6 end-to-end ticket, outcome=unresolved
        │                                     (see D27); correctly landed here after the D26 cwd fix]
        ├── k8s/                            [Stage 4 production-shaping, Phases 3-5]
        │   └── monitoring/
        │       ├── README.md               [reinstall steps, datasource setup, D24 summary]
        │       ├── prometheus-values.yaml  [scrape_interval: 5s, scrape_timeout: 4s — D24]
        │       ├── grafana-values.yaml     [admin password deliberately NOT hardcoded]
        │       └── dashboard-order-svc-incident.json  [exported "order-svc Incident Dashboard"]
        └── observability/                  [Stage 4 — Steps 1-4 done, production-shaping Phases 1-6 done]
            ├── load_generator.py           [DONE — Step 4; BASE_URL still hardcoded to localhost:8080,
            │                                 relies on the order-svc port-forward being open]
            ├── requirements.txt             [UPDATED Phase 6 — now requests, pandas, scikit-learn,
            │                                 anthropic, python-dotenv (last two added for rca_agent.py)]
            ├── anomaly_detector.py         [Phase 4; standalone, does NOT import from week-05/;
            │                                 fetch_real_metrics() queries Prometheus via PromQL;
            │                                 fit_detector()/FEATURE_COLUMNS copied verbatim from Week 5]
            ├── alert_grouper.py            [NEW — Phase 6; standalone copy of week-05/src/alert_grouper.py's
            │                                 group_alerts() logic, unchanged, does NOT import from week-05/]
            ├── rca_agent.py                [NEW — Phase 6; NOT a copy of Week 5's rca_agent.py — makes a
            │                                 REAL Claude API call (Week 5's version used simulated if/else
            │                                 threshold logic since no API key was available there;
            │                                 here one is, so this is a deliberate upgrade, not a copy)]
            ├── write_incident_handoff.py   [NEW — Phase 6; maps real Incident + rca dict into
            │                                 remediation_agent.py's exact expected schema, queries
            │                                 current_replicas live via kubectl, hardcodes
            │                                 max_replicas/target_cpu_pct/error_budget_remaining as
            │                                 explicit placeholder constants (D25), then subprocess-chains
            │                                 into remediation_agent.py with cwd="../remediation" (D26)]
            ├── output/                     [NEW — rca_report_INC-*.md files, human-readable RCA reports]
            ├── venv-anomaly-detector/       [gitignored — dedicated venv, now covers the whole Phase 4-6 chain]
            ├── README.md                    [Step 4 era; may need a Phase 1-6 addendum]
            └── order-svc/                  [DONE — Steps 1-3, Phases 1-2]
                ├── app.py                  [UPDATED Phase 2 — added /metrics/prometheus endpoint
                │                             via prometheus_client; original JSON /metrics untouched]
                ├── requirements.txt         [UPDATED — added prometheus-client]
                ├── k8s/
                │   └── deployment.yaml     [Phase 1/3; Deployment + Service, namespace: orders,
                │                             Service carries prometheus.io/* scrape annotations]
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
| Stage 5 (auto-remediation) core build | ✅ Done, 3 outcome paths verified | `3f5364b`, `baac52c`, `be3f793` |
| Stage 4 Steps 1-4 (service, container, OTel, load gen) | ✅ Done | `1583769`, `b09ed39`, `369b86c`, `cac93c9` |
| Stage 4 production-shaping Phase 1 (K8s Deployment) | ✅ Done | `65c2c9f` |
| Stage 4 production-shaping Phase 2 (Prometheus metrics endpoint) | ✅ Done | `45abc42` |
| Stage 4 production-shaping Phase 3 (real Prometheus scrape target, `orders` namespace move) | ✅ Done | `4c27706` |
| Stage 4 production-shaping Phase 4 (PromQL-based anomaly detection) | ✅ Done — real findings D22, D23 | `8f57509` |
| Stage 4 production-shaping Phase 5 (Grafana dashboard) | ✅ Done — real finding D24 | `92adf5b` |
| **Stage 4 Phase 6 (chain into Stage 5)** | 🔶 **BUILT AND WORKING — verified end-to-end multiple times (real `remediated` and `unresolved` outcomes observed) — NOT YET COMMITTED. Two open design questions remain (see §9), then commit.** | — |
| Stage 3 (predictive deploy) | ⬜ Not started | — |
| Wiring all 5 stages end-to-end | ⬜ Not started | — |
| Option B (GitHub Actions) | ⬜ Not started | — |
| Option A (single script) | ⬜ Not started | — |
| `docs/decisions.md` (doc 1) | 🔶 D1-D24 committed; D25-D27 drafted, not yet inserted | `be01265` (original), updated continuously |
| `docs/CONTINUATION.md` (doc 2) | ✅ Done, kept updated | `22fdcb4` (original), this revision pending commit |
| `docs/architecture.md` (doc 3) | ✅ Done | `057d023` — §5b could use a small update noting Phases 1-5 are complete, not "being upgraded" |
| `docs/RUNBOOK.md` (doc 4) | ✅ Done for what's built; §5 still a placeholder pending Phase 1-6 commands being appended | `12026e9` |
| Per-stage READMEs — `observability/`, `remediation/` (doc 5) | ✅ Done for Steps 1-4 era; `observability/README.md` could use a Phase 1-6 addendum | `1e19da2` |
| `k8s/monitoring/README.md` | ✅ Done | `92adf5b` |
| Capstone report (doc 6, 4-6pp) | ⬜ **Deliberately deferred** — see §9 | — |
| 15-min demo script (doc 7) | ⬜ **Deliberately deferred** — see §9 | — |

**Rough overall completion: directionally higher than the ~30-35%
estimated earlier.** Stage 4's entire production-shaping arc (Phases 1-5)
is fully done and committed; Phase 6 is built and functionally verified,
just uncommitted pending two design decisions. Not re-estimated
precisely; every phase so far has taken longer than planned due to real,
unpredictable debugging (see `decisions.md`), and Phase 6 was no
exception (three real findings: D25's schema gap, D26's `cwd` bug, D27's
outcome-taxonomy gap).

---

## 6. THE CURRENT TASK: finish Stage 4 Phase 6, then move to Stage 3

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
  via `kubectl port-forward`, explicitly not production-realistic — the
  plan was to containerize as a K8s Job "for Phase 6," which did NOT
  happen — Phase 6 still uses port-forward; this remains a live gap, see
  §9); **D23** (IsolationForest can miss a sustained incident once
  `rate()`'s 5-minute smoothing duplicates readings across several
  consecutive points).
- **Phase 5:** A Grafana dashboard with 3 panels (CPU %, Error Rate, p99
  Latency), verified showing a real correlated incident. Real finding:
  **D24** (Prometheus's default 60s scrape interval was too coarse for
  brief Gauge-based spikes; fixed by reducing to 5s/4s timeout, plus an
  explicit rollout restart). `k8s/monitoring/` holds the Helm values and
  exported dashboard JSON for fresh-clone reproducibility.
- **Phase 6 (this session):** Built the full real chain:
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
    `remediation_agent.py`.
  - Ran the full chain successfully multiple times against real,
    live-generated `load_generator.py` incidents:
    - One run produced a genuinely complete, correlated incident
      (CPU 103.8%, error_rate 1.0, latency 993ms) → correct RCA → agent
      reasoned through dry-run → scale approved → `outcome: "remediated"`.
    - Along the way, found and fixed a real `subprocess` `cwd` bug: the
      first run's ITSM ticket/handoff paths resolved against the wrong
      working directory (**D26**) — fixed with `cwd="../remediation"`.
      Also surfaced, while investigating: `execute_scale` has always
      been simulated (updates in-memory state only, never calls
      `kubectl scale`) — true since Stage 5's original build, not
      something Phase 6 introduced, only now visible against real K8s
      infrastructure for the first time.
    - A second run produced a genuinely benign, low-impact incident
      (CPU 9.9%, 0 errors, 0ms extra latency). The agent correctly
      determined no scale-out was warranted and declined to act — sound
      reasoning — but this fell through to `outcome: "unresolved"`,
      since `remediation_agent.py`'s outcome taxonomy has no
      representation for "correctly decided no action needed"
      (**D27**) — a real gap in Stage 5's original design, not a bug
      Phase 6 introduced.
  - An earlier standalone `alert_grouper.py` smoke test also surfaced a
    milder version of D23's pattern: a run against a near-idle window
    grouped a very weak "anomaly" (CPU 9.9%, all else zero) — correct
    behavior for the detector given the data, but a reminder that
    detection quality is bounded by the input window's actual content.

### What's genuinely still open (not yet decided)

1. **Should `execute_scale` become real** (calling `kubectl scale
   deployment` instead of only updating in-memory state)? This would
   expand Stage 5's already-built-and-verified scope — a decision to
   make deliberately, not a side effect of Phase 6 wiring. Not yet
   decided.
2. **Should Stage 5's outcome taxonomy be expanded** (e.g. adding
   `resolved_no_action_needed`) to correctly represent D27's finding, or
   left as `unresolved` with the gap documented? Same reasoning as #1.
   Not yet decided.
3. **D22's original plan to containerize `anomaly_detector.py` as a K8s
   Job "for Phase 6"** did not happen — Phase 6's chain still runs
   locally via `kubectl port-forward`, same as Phase 4. Worth revisiting
   whether this genuinely needs to happen before Phase 6 is considered
   "done," or whether it's acceptable to leave as a documented ongoing
   limitation (leaning toward the latter, since the chain's correctness
   has now been proven — containerizing is an infrastructure-realism
   improvement, not a functional gap).
4. **D25/D26/D27 need to be inserted into `decisions.md`** (drafted, see
   below) — not yet done.
5. **Nothing from Phase 6 is committed to git yet.**

### What carries forward unchanged (nothing is discarded)

`app.py`'s core logic, the `Dockerfile`, `fit_detector()`/`FEATURE_COLUMNS`
in `anomaly_detector.py`, `group_alerts()` in `alert_grouper.py`,
`load_generator.py`'s calm→spike→recovery pattern, and
`remediation_agent.py` itself (Stage 5's code was NOT modified by Phase 6
— it's invoked as-is, exactly as originally built and verified).

---

## 7. Working conventions established this session (follow these)

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
  caught real bugs multiple times (D22-D27 all came from this habit).
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
- **Documentation discipline:** per-stage READMEs written immediately
  after each stage is verified. `docs/decisions.md` updated continuously
  at each real decision point — including genuinely surprising findings
  discovered while testing. Big synthesis documents (the report, the
  demo script) are deliberately deferred — see §9.

---

## 8. Known limitations / honesty notes (for the report later)

- IaC's SLSA provenance is provenance-*shaped* but not independently
  *verifiable* — confirmed by running the real `slsa-verifier` CLI
  against it, which correctly failed (no signature, no Rekor entry).
- The IaC work runs against a single local project via manual Terraform,
  not a real CI/CD-triggered pipeline — that gap is intentionally closed
  later by Option B (GitHub Actions).
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
  D23. Not fixed.
- `anomaly_detector.py` (and now the whole Phase 6 chain) reaches
  Prometheus/`order-svc` via `kubectl port-forward` for local
  development, which is explicitly NOT production-realistic. D22
  originally planned to containerize this "for Phase 6" — that did NOT
  happen; the chain still runs locally. Left as an open item (§9),
  since the chain's correctness has now been proven and containerizing
  is an infrastructure-realism improvement, not a functional fix.
- Prometheus's scrape interval (originally 60s) was too coarse to
  reliably observe short-lived Gauge-based metrics — fixed by reducing
  to 5s (`decisions.md` D24).
- Stage 4's real telemetry can be genuinely measured, but Stage 5's
  `remediation_agent.py` also needs autoscaling-policy inputs
  (`max_replicas`, `target_cpu_pct`, `error_budget_remaining`) that don't
  correspond to anything configured in the cluster yet, since Stage 3
  hasn't been built. Phase 6 hardcodes these as clearly-labeled
  placeholder constants (`decisions.md` D25).
- **`remediation_agent.py`'s `execute_scale` has always been simulated**
  — it updates only its own in-memory `state` dict, never calls `kubectl
  scale`. True since Stage 5's original build (before Phase 6 existed),
  only now visible against real K8s infrastructure for the first time
  (`decisions.md` D26). A "remediated" outcome currently does not change
  the actual Deployment's replica count.
- **`remediation_agent.py`'s outcome taxonomy has no representation for
  "the agent correctly determined no action was needed."** A real,
  benign incident (CPU 9.9%, zero errors, zero extra latency) produced
  a sound `dry_run_scale`-informed decision to take no action — but this
  fell through to the default `unresolved` outcome, since the code only
  ever reassigns `outcome` inside `execute_scale`'s branch
  (`decisions.md` D27). Genuinely interesting evidence: the agent
  behaved more sensibly than the surrounding code's ability to represent
  that sensible behavior.

---

## 9. Open items (unresolved)

- **PR from `capstone-option-c` to `main`:** not yet opened.
- **Documents 6 and 7 (capstone report, demo script): deliberately
  deferred**, not forgotten. **Resume these once Stage 3, full wiring,
  and at minimum Option B exist.**
- **Rubric-mapping table:** completed — lives in `docs/architecture.md` §6.
- **`docs/architecture.md` §5b:** still describes Stage 4's production
  shaping as "in progress, being upgraded" — needs updating now that
  Phases 1-5 are complete and Phase 6 is functionally verified.
- **`docs/RUNBOOK.md` §5:** still a placeholder. Should cover Phases 1-5's
  commands PLUS Phase 6's own operational sequence (port-forwards, venv
  activation, the full `write_incident_handoff.py` chain) — write once,
  covering the whole arc, once Phase 6's two open design questions
  (below) are resolved and everything is committed.
- **Grafana dashboard's default time range** is still "Last 5 minutes" —
  worth broadening before any actual demo.
- **D25, D26, D27 (drafted in §6/§8 above, NOT yet inserted into
  `decisions.md`)** — need to actually be added to the real file.
- **Open design question: should `execute_scale` become genuinely real**
  (calling `kubectl scale deployment`)? Not yet decided — see §6.
- **Open design question: should Stage 5's outcome taxonomy be
  expanded** (e.g. `resolved_no_action_needed`)? Not yet decided — see §6.
- **Open design question: should Phase 6's chain be containerized**
  (closing D22's original plan), or is local `port-forward`-based
  execution acceptable as a documented limitation? Leaning toward the
  latter, not yet finalized.
- **Nothing from Phase 6 is committed to git yet:**
  `observability/alert_grouper.py`, `rca_agent.py`,
  `write_incident_handoff.py`, the updated `requirements.txt`, plus
  `output/rca_report_*.md` files. Two real ITSM tickets exist from
  live-testing (`TICKET-4987e34e.json` — landed in the WRONG
  `observability/itsm_tickets/` location before the D26 fix, arguably
  worth deleting rather than committing as evidence of a bug that's
  since been fixed; `TICKET-f764ae73.json` — correctly in
  `remediation/itsm_tickets/`, outcome `unresolved`, worth keeping as
  evidence for D27). `handoffs/stage4-incident.json` has also been
  overwritten with real output — the original hand-written fixture no
  longer exists in that file (worth deciding whether to preserve a copy
  of the original fixture somewhere, e.g. renamed, since it was useful
  reference material for confirming the schema).

---

## 10. How to resume

1. Confirm environment (see §3's "every-session operational sequence").
2. Read this document fully before taking any action.
3. Resolve the three open design questions in §9 (real `execute_scale`?
   expand the outcome taxonomy? containerize the chain?) — or explicitly
   decide to defer them and document that decision.
4. Insert D25/D26/D27 into `decisions.md` (content drafted in §6/§8 above).
5. Decide what to do with the two stray ITSM tickets and the overwritten
   `stage4-incident.json` fixture (see §9's last bullet).
6. Commit Phase 6: `observability/alert_grouper.py`, `rca_agent.py`,
   `write_incident_handoff.py`, updated `requirements.txt`,
   `docs/decisions.md`, this file, and whichever ITSM tickets/output
   files are kept.
7. Update `docs/architecture.md` §5b and start `docs/RUNBOOK.md` §5.
8. Move on to Stage 3 (predictive deploy) — the next major unstarted
   piece of the capstone.
9. Update §5 (status table) and this document's "Last updated" line at
   the end of the session. If new documents or files get committed,
   update §4 (repo structure) too.
