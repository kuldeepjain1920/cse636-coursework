# CSE636 Capstone — Master Build Guide

A single, chronological walkthrough of the entire capstone build, in the
order it actually happened across all working sessions — from initial
planning through final submission. This consolidates `docs/decisions.md`
(the *why*), `docs/RUNBOOK.md` (the *how*, organized by finished stage),
and `docs/CONTINUATION.md` (the *current state*) into one linear story,
for anyone (including future-me) who wants to understand or reproduce
the whole arc in the order it unfolded, not just the final state.

**A note on completeness:** commands shown here for stages already
verified and committed (Stages 2, 4, 5, and Stage 3 Phases 1-2) are the
real, tested commands from `docs/RUNBOOK.md`. A few early steps —
mainly where a Claude Code agent generated a file interactively (the
Terraform config, the initial `remediation_agent.py` additions) — are
described narratively rather than as literal shell commands, since that
work happened as iterative code generation, not a fixed command
sequence. Where that's the case, it's called out explicitly.

---

## Phase 0 — Prerequisites and environment setup

Tools needed across the whole build:

```bash
gcloud --version
terraform --version
conftest --version
docker --version
helm version
python3 --version
kubectl version --client
```

Accounts and identifiers used throughout:

| Item | Value |
|---|---|
| GCP project (IaC/capstone only) | `cse636-capstone-iac` |
| GCP account | `kuldeepjainphotos@gmail.com` |
| GitHub account | `kuldeepjain1920` |
| Repo | `github.com/kuldeepjain1920/cse636-coursework` |
| Working branch | `capstone-option-c` |
| Local repo path | `~/cse636-coursework` |

```bash
git clone https://github.com/kuldeepjain1920/cse636-coursework.git
cd cse636-coursework
git checkout capstone-option-c
cat .gitignore
```

`.gitignore` covers `.env`, `venv-*/`, `gcp-sa-key.json`, and Terraform
plan files — none of these are ever committed.

```bash
cat > .env << 'EOF'
ANTHROPIC_API_KEY=your-key-here
EOF
```

Required for `remediation_agent.py` and `rca_agent.py`, both of which
call the Claude API directly. `python-dotenv` finds this by walking up
from the current working directory.

---

## Phase 1 — Capstone planning

Before writing any code, the existing work from Weeks 0-6 was mapped
against the capstone's 7-stage pipeline to identify what already existed
versus what needed building. This produced the architectural decision
that shapes everything downstream:

- **Orchestration approach chosen: Option C** (heterogeneous native
  platforms — Docker, Kubernetes, local scripts — with file/subprocess
  handoffs), over Option B (GitHub Actions) or Option A (single Python
  script). All three are eventually planned, built in that order, for
  comparative material in the report — but only Option C was actually
  built.
- **Build order chosen: back-to-front.** Stage 5 (auto-remediation) was
  built first, reusing `week-06-assignment/src/react_agent.py` as a
  foundation, before Stage 4 (observability) existed to feed it real
  incidents. This was a deliberate sequencing choice, not an accident.
- **Working sequence for Week 7 overall:** capstone planning → IaC lab
  (fills the one real gap from prior weeks) → capstone build-out (all
  stages) → final exam review.

This phase was planning and design discussion only — no code written.

---

## Phase 2 — Stage 2: Agentic IaC (the Week 7 lab)

### 2.1 GCP setup

```bash
gcloud config set project cse636-capstone-iac
gcloud config list
```

**Always verify the active project before any resource-creating
command** — a stale active project was a real cause of a misdirected
resource creation earlier in this build (D3).

```bash
gcloud services enable storage.googleapis.com
gcloud iam service-accounts create terraform-iac-demo --display-name="Terraform IaC demo"
gcloud projects add-iam-policy-binding cse636-capstone-iac \
  --member=serviceAccount:terraform-iac-demo@cse636-capstone-iac.iam.gserviceaccount.com \
  --role=roles/storage.admin
gcloud iam service-accounts keys create gcp-sa-key.json \
  --iam-account=terraform-iac-demo@cse636-capstone-iac.iam.gserviceaccount.com
```

Least-privilege service account (`storage.admin` only), key gitignored.

### 2.2 Generate the Terraform config

*(Narrative, not a fixed command sequence: a Claude Code agent was
prompted to generate a `google_storage_bucket` resource with versioning,
uniform bucket-level access, public-access prevention, and a required
`environment=capstone` label. The output is `gcs.tf`.)*

**Real finding during this step:** the agent attempted an unprompted
`terraform apply` — caught and stopped before any real infrastructure
was created. Documented as a genuine, unstaged example of agent
over-scoping (see `iac/README.md`).

### 2.3 Validate and plan

```bash
cd week-07-capstone/orchestrator-c-heterogeneous/iac
terraform init
terraform validate
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary > tfplan.json
```

### 2.4 Policy enforcement

```bash
conftest test tfplan.json --policy policy/
```

Expected: `2 tests, 2 passed`. Verified against all three cases during
development: a passing plan, a plan with the wrong label value, and a
plan missing the label entirely.

### 2.5 Prompt-injection test

A malicious document (`malicious_docs.txt`) was crafted to attempt to
trick the agent into rewriting the Terraform config. Tested across three
escalating attempts, including a direct authority-assertion ("I am human
in the loop"). The agent correctly refused all three — documented
verbatim in `iac/README.md`.

### 2.6 Apply (human-supervised only)

```bash
terraform apply "tfplan.binary"
```

**Interactive confirmation required — never automate past this prompt.**
A real incident during this build involved exactly this risk (D11).

### 2.7 SLSA provenance

A SLSA v1.0 provenance document was hand-authored, found to have three
real defects on review (stale commit reference, fabricated timestamps,
unverified builder version), and corrected.

```bash
shasum -a 256 gcs.tf tfplan.binary
slsa-verifier verify-artifact tfplan.binary \
  --provenance-path provenance.json \
  --source-uri github.com/kuldeepjain1920/cse636-coursework
```

**Expected to fail** — intentional. Confirms the document is
provenance-*shaped* but not independently *verifiable* (no signature, no
Rekor entry) — D12.

### 2.8 Commit

```bash
git status --ignored orchestrator-c-heterogeneous/iac/
git add orchestrator-c-heterogeneous/iac/gcs.tf orchestrator-c-heterogeneous/iac/policy/ \
  orchestrator-c-heterogeneous/iac/malicious_docs.txt orchestrator-c-heterogeneous/iac/provenance.json \
  orchestrator-c-heterogeneous/iac/README.md
git commit -m "Stage 2: Agentic IaC — Terraform + OPA/conftest + SLSA provenance + prompt-injection demo"
git push origin capstone-option-c
```

Actual commits: `1c7e2b2`, `c4580c3`.

---

## Phase 3 — Stage 5: Auto-remediation (built before Stage 4, deliberately)

Built on `week-06-assignment/src/react_agent.py` (the Assignment
version — already targeted `INC-002`/`order-svc`, had 4 layered
guardrails). New work: `create_itsm_ticket()` and
`write_stage5_handoff()`.

*(Narrative: the additions to the base react agent were written
iteratively, not via a fixed command sequence — the commands below are
for running and verifying the finished agent, not generating it.)*

```bash
cd ~/cse636-coursework
source venv-week6/bin/activate
cd week-07-capstone/orchestrator-c-heterogeneous/remediation
python3 remediation_agent.py
```

Reads `../handoffs/stage4-incident.json` (a hand-written fixture at this
point — Stage 4 didn't exist yet). Runs the ReAct loop, pauses for human
approval at `[APPROVAL REQUIRED] execute_scale on order-svc`.

**To exercise the other guardrail paths:**

```bash
# Decline the approval prompt
python3 remediation_agent.py

# Kill switch — refuses before the approval prompt appears
export AUTONOMY_KILL_SWITCH=off
python3 remediation_agent.py
export AUTONOMY_KILL_SWITCH=on
```

**Verified, real outcome paths, each committed separately:**

| Outcome | Verified behavior | Commit |
|---|---|---|
| `remediated` | Full happy path — 4→7 replicas, approved | `3f5364b` |
| `escalated_declined` | Operator declined; correctly escalated | `baac52c` |
| `escalated_kill_switch` | Blocked before approval prompt ever appeared | `be3f793` |

```bash
deactivate
```

*(`resolved_no_action_needed`, a 4th outcome, wasn't added until Phase
5's real chain in §5.6 below — see D27.)*

---

## Phase 4 — Stage 4, Steps 1-4: Observability base build

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability/order-svc
```

*(Narrative: `app.py` — a Flask service doing genuine CPU-bound work via
repeated SHA-256 hashing, instrumented with OTel spans — was written
iteratively. Commands below are for running/testing the finished
service.)*

### 4.1 Standalone run

```bash
python3 -m venv venv-order-svc
source venv-order-svc/bin/activate
pip install -r requirements.txt
python3 app.py
```

```bash
curl http://localhost:8080/health
curl -X POST http://localhost:8080/order
curl http://localhost:8080/metrics
```

### 4.2 Load-test standalone

```bash
for i in $(seq 1 20); do curl -s -X POST http://localhost:8080/order & done; wait
curl http://localhost:8080/metrics
```

**Real bug found and fixed:** a race condition where concurrent
responses reported the same `order_id` — fixed via an early counter
snapshot.

### 4.3 Containerize

```bash
docker build -t order-svc .
docker run -d --name order-svc -p 8080:8080 order-svc
sleep 3
curl -X POST http://localhost:8080/order
docker logs order-svc
```

`sleep 3` avoids a real `Connection reset by peer` race against
container startup.

**Real bug found and fixed:** container CPU measurement was diluted by
Docker Desktop VM's multi-core visibility. `--cpus=1` didn't fix it
(cgroup quotas don't change what `cpu_count()` reports) — the actual fix
was switching from `psutil.cpu_percent()` (system-wide) to
`psutil.Process().cpu_percent()` (per-process).

```bash
docker stop order-svc; docker rm order-svc
```

### 4.4 Verify OTel spans

```bash
docker logs order-svc | head -30
```

Expect a JSON span with `"name": "order.process"`, `http.*`/`order.*`
attributes.

### 4.5 Load generator

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability
source order-svc/venv-order-svc/bin/activate
pip install -r requirements.txt
docker run -d --name order-svc -p 8080:8080 order-svc
sleep 3
python3 load_generator.py
```

Calm (10 req, 1s apart) → spike (40 req, concurrency 20) → recovery (10
req, 1s apart). Verified run: 13/40 real errors (32.5%) during spike,
peak CPU 212.4% (multi-core, legitimate — D17/D18), clean recovery.

### 4.6 Commit

```bash
git status --ignored orchestrator-c-heterogeneous/observability/
git add orchestrator-c-heterogeneous/observability/order-svc/app.py \
  orchestrator-c-heterogeneous/observability/order-svc/Dockerfile \
  orchestrator-c-heterogeneous/observability/load_generator.py
git commit -m "Stage 4 Steps 1-4: order-svc (Flask, containerized, OTel), load generator"
git push origin capstone-option-c
```

Actual commits: `1583769`, `b09ed39`, `369b86c`, `cac93c9`.

---

## Phase 5 — Stage 4 production-shaping (Phases 1-6)

**Every-session sequence from this point forward:**

```bash
kubectl cluster-info
kubectl get pods -n orders
kubectl get pods -n monitoring
```

### 5.1 Phase 1 — Deploy to Kubernetes

**Real history:** `order-svc` was first deployed into the `default`
namespace per the original lab instructions, then deliberately moved
into `orders` for realism. Namespace is immutable on an existing K8s
object, so this required delete-and-recreate, not an in-place edit
(D30).

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability/order-svc/k8s
kubectl create namespace orders
kubectl apply -f deployment.yaml
kubectl get pods,deployment,service -n orders
kubectl run curltest --image=curlimages/curl --rm -it --restart=Never -n orders -- \
  curl -s http://order-svc:8080/health
```

Commit: `65c2c9f`.

### 5.2 Phase 2 — Prometheus metrics endpoint

`app.py` updated to expose `/metrics/prometheus` via `prometheus_client`,
alongside (not replacing) the original JSON `/metrics`.

```bash
docker build -t order-svc:latest .
kubectl rollout restart deployment/order-svc -n orders
kubectl run curltest --image=curlimages/curl --rm -it --restart=Never -n orders -- \
  curl -s http://order-svc:8080/metrics/prometheus
```

Commit: `45abc42`.

### 5.3 Phase 3 — Install Prometheus, wire the scrape target

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create namespace monitoring
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/k8s/monitoring
helm install prometheus prometheus-community/prometheus \
  --namespace monitoring \
  -f prometheus-values.yaml
```

Fresh install, not a reuse of Week 4's torn-down KEDA Prometheus.
`prometheus.io/*` scrape annotations **must be on the Service, not the
Deployment** — a real mistake made and corrected during this build.

```bash
kubectl get pods -n monitoring
kubectl port-forward -n monitoring svc/prometheus-server 9090:80
```

Check `http://localhost:9090/targets` shows `order-svc` as `UP`.

Commit: `4c27706`.

### 5.4 Phase 4 — PromQL-based anomaly detection

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability
python3 -m venv venv-anomaly-detector
source venv-anomaly-detector/bin/activate
pip install -r requirements.txt
python3 anomaly_detector.py
```

Standalone, does not import from `week-05/`. `fit_detector()`/
`FEATURE_COLUMNS` copied verbatim from Week 5; `fetch_real_metrics()`
queries Prometheus's `query_range` API.

**Real findings:**
- **D22:** reaches Prometheus via `kubectl port-forward` — not
  production-realistic, deliberately left as-is.
- **D23:** IsolationForest (contamination=0.04) can miss a sustained
  incident once `rate()`'s 5-minute smoothing duplicates readings across
  consecutive points.

To see a real correlated incident:
```bash
kubectl port-forward -n orders svc/order-svc 8080:8080   # separate terminal
python3 load_generator.py
python3 anomaly_detector.py
```

Commit: `8f57509`.

### 5.5 Phase 5 — Grafana dashboard

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/k8s/monitoring
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
helm install grafana grafana/grafana \
  --namespace monitoring \
  -f grafana-values.yaml
kubectl get secret --namespace monitoring grafana \
  -o jsonpath="{.data.admin-password}" | base64 --decode; echo
kubectl port-forward -n monitoring svc/grafana 3000:80
```

Log in (`admin` / retrieved password), add Prometheus datasource, import
`dashboard-order-svc-incident.json`.

**Real finding — D24:** Prometheus's default 60s scrape interval was too
coarse for brief Gauge-based CPU spikes. Fixed by reducing to 5s in
`prometheus-values.yaml` (`scrape_interval: 5s`, `scrape_timeout: 4s`).

Commit: `92adf5b`.

### 5.6 Phase 6 — Chain into Stage 5

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability
source venv-anomaly-detector/bin/activate
python3 write_incident_handoff.py
```

Full chain: `anomaly_detector.py` → `alert_grouper.py` (standalone copy
of Week 5's `group_alerts()`, unchanged) → `rca_agent.py` (**real**
Claude API call, a deliberate upgrade over Week 5's simulated `if/else`
version) → `write_incident_handoff.py` (writes
`handoffs/stage4-incident.json`, `subprocess`-chains into
`remediation_agent.py`).

**Real findings:**
- **D25:** `max_replicas`/`target_cpu_pct`/`error_budget_remaining`
  hardcoded as placeholder constants — Stage 3's autoscaling policy
  didn't exist yet.
- **D26:** `subprocess.run()` `cwd` bug caused ITSM tickets/handoffs to
  land in the wrong directory. Fixed with explicit `cwd="../remediation"`.
- **D27:** `remediation_agent.py`'s outcome taxonomy had no way to
  represent "correctly decided no action needed" — a real benign
  incident (9.9% CPU, 0 errors) fell through to `unresolved`. Fixed by
  adding `resolved_no_action_needed`, verified by re-running the same
  scenario (`TICKET-f764ae73.json` pre-fix vs. `TICKET-34cd34f0.json`
  post-fix).

To generate a fresh incident first:
```bash
python3 load_generator.py
python3 write_incident_handoff.py
```

Verify placement:
```bash
find ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous -name "TICKET-*.json"
```

### 5.7 Commit

```bash
git status --ignored orchestrator-c-heterogeneous/
git add orchestrator-c-heterogeneous/observability/ orchestrator-c-heterogeneous/remediation/remediation_agent.py \
  orchestrator-c-heterogeneous/handoffs/ docs/decisions.md
git commit -m "Stage 4 Phase 6: chain into Stage 5, D25-D27 fixes"
git push origin capstone-option-c
```

Actual commit: `28c684f`.

---

## Phase 6 — Documentation set (first pass)

With Stages 2, 4, and 5 all built and verified, five documentation
artifacts were produced:

1. `docs/decisions.md` — chronological decisions log, D1 through the
   current point, each with alternatives considered and reasoning.
2. `docs/CONTINUATION.md` — fresh-chat handoff document, updated at the
   end of each session from this point forward.
3. `docs/architecture.md` — pipeline design, Mermaid diagrams,
   three-orchestrator decision, stage-by-stage breakdown, rubric-mapping
   table.
4. `docs/RUNBOOK.md` — command-by-command reproducibility guide (the
   source for most of Phases 2-5 above).
5. Per-stage READMEs (`iac/README.md`, `remediation/README.md`,
   `observability/README.md`, `k8s/monitoring/README.md`).

**Documents 6 (capstone report) and 7 (demo script) were deliberately
deferred at this point** — both summarize the whole project, and with
Stage 3 and full wiring still unbuilt (~65-70% of the project), writing
them then risked the same kind of rewrite `architecture.md` had already
hit once mid-session.

```bash
git status --ignored docs/
git add docs/decisions.md docs/CONTINUATION.md docs/architecture.md docs/RUNBOOK.md \
  orchestrator-c-heterogeneous/iac/README.md orchestrator-c-heterogeneous/remediation/README.md \
  orchestrator-c-heterogeneous/k8s/monitoring/README.md
git commit -m "Documentation set: decisions log, continuation doc, architecture, runbook, per-stage READMEs"
git push origin capstone-option-c
```

---

## Phase 7 — Stage 3 Phase 1: real risk scoring

Design decided first (no code): risk-score `order-svc`'s own deployment
(Option A — not Stage 2's Terraform plan, not a synthetic scenario, to
keep Stage 3 connected to both Stage 2 and Stage 4).

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/predictive-deploy
source ../observability/venv-anomaly-detector/bin/activate
python3 risk_scorer.py
```

Pulls 3 real inputs: current CPU%/error rate (Prometheus instant query),
fresh OPA/conftest result (re-runs `terraform plan` → `terraform show`
→ `conftest test` every call, not cached), current replica count
(`kubectl get deployment`). Writes `handoffs/stage3-risk.json`.

**Real finding — D28:** the shared error-rate PromQL query —
```
rate(order_svc_requests_total{status="500"}[5m])
/ rate(order_svc_requests_total[5m])
```
— had a vector-matching bug. Prometheus's default division matching
paired only the identical `status="500"` series, silently dropping
`status="200"` from the denominator. Result: exactly `1.0` whenever any
errors existed, or `0/0 = NaN` otherwise — never the real ratio, and
already silently affecting `anomaly_detector.py` since Phase 4 (masked
by an existing `.fillna(0.0)`).

**Fix:**
```
sum(rate(order_svc_requests_total{status="500"}[5m]))
/ sum(rate(order_svc_requests_total[5m]))
```
applied to both `risk_scorer.py` and `anomaly_detector.py`, plus an
explicit `math.isnan()` guard in `risk_scorer.py` so a NaN can never
silently default the gate to `"proceed"`.

**Verified:** re-ran `anomaly_detector.py` post-fix — 4/118 points
flagged, consistent with `contamination=0.04`. Re-ran `risk_scorer.py`
after a fresh load spike — `error_rate: 0.3158`, plausible vs. the app's
own `0.2812`, not the broken `1.0`/masked `0.0`.

```bash
git add orchestrator-c-heterogeneous/predictive-deploy/risk_scorer.py \
  orchestrator-c-heterogeneous/observability/anomaly_detector.py docs/decisions.md
git commit -m "Stage 3 Phase 1: real risk_scorer.py; fix D28 PromQL vector-matching bug"
git push origin capstone-option-c
```

Commit: `76320fd`.

---

## Phase 8 — Stage 3 Phase 2: real canary deploy

### 8.1 Design decisions made before coding

- **Canary target:** Option B chosen — a genuinely real canary needs a
  real v2, not a simulated recommendation.
- **v2's real difference:** `cpu_bound_work()` does `100_000` hashing
  iterations vs. v1's `200_000` — a real performance change.
- **Separate images, not a shared image + env-var flag** — matches
  production practice (immutable, independently-buildable artifacts per
  version).

### 8.2 Label metrics by version

`app.py`/new `app_v2.py`: added `VERSION` env var, labeled all three
Prometheus metrics (`order_svc_cpu_percent`, `order_svc_requests_total`,
`order_svc_request_duration_seconds`) with it.

### 8.3 Build and deploy both versions

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability/order-svc
docker build -t order-svc:v1 .
docker build -t order-svc:v2 -f Dockerfile.v2 .
docker images | grep order-svc
```

```bash
cd k8s
kubectl apply -f deployment.yaml       # v1
kubectl apply -f deployment-v2.yaml    # v2, shares v1's Service selector
kubectl get pods -n orders -l app=order-svc --show-labels
```

### 8.4 Run the canary comparison

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/predictive-deploy
source ../observability/venv-anomaly-detector/bin/activate
python3 canary_controller.py --dry-run
```

**Real finding — D29, bug 1:** `kubectl port-forward` to a Service pins
to a single backing pod, doesn't load-balance. First real test showed v2
reading exactly `0.0/0.0` — genuinely zero traffic, not "healthier."

**Fix:** generate comparison traffic from inside the cluster instead:
```bash
kubectl run canary-load --image=curlimages/curl --rm -it --restart=Never -n orders -- \
  sh -c 'for i in $(seq 1 200); do curl -s -X POST http://order-svc:8080/order > /dev/null; done'
```

**Real finding — D29, bug 2:** `canary_controller.py` originally polled
v1 and v2 in two separate sequential ~60s windows, not concurrently —
comparing two different slices of real time, not fair same-conditions
data. Surfaced when a load run landed only during v2's phase.

**Fix:** replaced two sequential `poll_and_average()` calls with a
single `poll_both_and_average()` sampling both versions together at each
timestamp within one shared window.

**Verified post-fix:** `v1: cpu_pct_avg=18.79`, `v2: cpu_pct_avg=12.49`,
both `error_rate_avg=0.0` — distinct, plausible, simultaneous values.

### 8.5 Execute the real promote

```bash
python3 canary_controller.py
```
(no `--dry-run`)

Decision: `promote`. **This actually executed** —
```
kubectl scale deployment/order-svc-v2 -n orders --replicas=1
kubectl scale deployment/order-svc -n orders --replicas=0
```

Verified against real cluster state:
```bash
kubectl get deployments -n orders
kubectl get pods -n orders -l app=order-svc --show-labels
cat ../handoffs/stage3-canary.json
```
`order-svc` at `0/0/0/0`, `order-svc-v2` at `1/1/1/1`, Running. This is
the **current, ongoing production state** — `order-svc-v2` is live,
`order-svc` intentionally left at 0 replicas (not deleted) for rollback
capability. `risk_scorer.py`'s `DEPLOYMENT_NAME` was updated to
`"order-svc-v2"` to match.

### 8.6 Commit

```bash
git status --ignored
git add orchestrator-c-heterogeneous/observability/order-svc/app.py \
  orchestrator-c-heterogeneous/observability/order-svc/app_v2.py \
  orchestrator-c-heterogeneous/observability/order-svc/Dockerfile.v2 \
  orchestrator-c-heterogeneous/observability/order-svc/k8s/deployment.yaml \
  orchestrator-c-heterogeneous/observability/order-svc/k8s/deployment-v2.yaml \
  orchestrator-c-heterogeneous/predictive-deploy/canary_controller.py \
  orchestrator-c-heterogeneous/predictive-deploy/risk_scorer.py \
  orchestrator-c-heterogeneous/handoffs/stage3-canary.json
git commit -m "Stage 3 Phase 2: canary controller, v1/v2 images, D29 fixes, real promote executed"

git add docs/decisions.md
git commit -m "Add D29: canary-testing infrastructure bugs"

git push origin capstone-option-c
```

Actual commits: `092a56e`, `ba3b082`.

---

## Phase 9 — Documentation correction pass

While reviewing docs for accuracy before Phase 10, a factual gap was
found: `RUNBOOK.md`/`architecture.md` implied `order-svc` had always
been deployed directly into `orders`, omitting the real `default`→
`orders` migration history (§5.1 above). This became **D30**.

Updated in this pass:
- `docs/architecture.md` — new §6 (Stage 3 Phases 1-2 section, mirroring
  §3/§4/§5's style), old §6 (rubric)/§7 (open items) renumbered to §7/§8
  with content updated.
- `docs/RUNBOOK.md` — new §6 (Stage 3 commands), old §6 renumbered to
  §7, namespace note added to §5.1.
- `docs/CONTINUATION.md` — §4 (repo structure, including new
  `predictive-deploy/` and v1/v2 `order-svc/` entries), §10 (open
  items), §11 (how to resume) all brought current — these had been
  missed by an earlier partial update.
- `docs/decisions.md` — D30 added.

```bash
git status --ignored docs/
git add docs/architecture.md docs/RUNBOOK.md docs/decisions.md
git commit -m "Documentation correction pass: Stage 3 Phases 1-2 added to architecture.md/RUNBOOK.md; D30 (namespace migration finding) added to decisions.md"
git push origin capstone-option-c
```

Commit: `98fe7b1`.

```bash
git add docs/CONTINUATION.md
git commit -m "Update CONTINUATION.md §4/§10/§11"
git push origin capstone-option-c
```

---

## Phase 10 — Submission scope decision, Documents 6 and 7

**Decision made:** submit as-is at the current build level. Stage 3
Phases 3-4 (FinOps cost estimator, full orchestrator wiring), full
5-stage end-to-end chaining, and Options B/A are explicitly deferred —
a conscious scope choice, not an oversight, and the report/demo script
state this plainly rather than waiting for those to exist (which had
been the original deferral condition for Documents 6/7).

Wrote:
- `docs/capstone-report.md` — Document 6, 4-6pp, first-person, covering
  every stage above plus D22-D30 as honest lessons-learned material and
  an explicit "what's deliberately not built" section.
- `docs/demo-script.md` — Document 7, ~15-minute timed walkthrough with
  speaker notes, live commands, and a fallback plan if anything doesn't
  cooperate live.

```bash
git status
git add docs/capstone-report.md docs/demo-script.md docs/CONTINUATION.md
git commit -m "Add Document 6 (capstone report) and Document 7 (demo script); update CONTINUATION.md to reflect both done"
git push origin capstone-option-c
```

Commit: `2c4170b`.

---

## Phase 11 — Final submission checklist

```bash
git status
git log -1 --oneline
```

Confirm clean working tree, `HEAD` matches `origin/capstone-option-c`.

- [ ] Confirm on GitHub's web UI (not just local state) that
      `capstone-option-c` shows everything: all `docs/`, `predictive-
      deploy/`, updated `order-svc/` with v1/v2, `handoffs/`.
- [ ] Confirm the actual submission link points at `capstone-option-c`,
      not `main` (a PR to `main` was left deliberately unopened for this
      submission).
- [ ] Confirm `decisions.md` D30 is actually committed, not just
      locally present.
- [ ] Leave the live cluster state (`order-svc-v2` promoted, `order-svc`
      at 0 replicas) untouched until grading is confirmed done — it's
      real evidence matching the report/demo script's claims.
- [ ] Note for later (not urgent): Stage 2's GCS bucket in
      `cse636-capstone-iac` is real, billed GCP infrastructure — the
      only one in this whole capstone. Worth a `terraform destroy` once
      the course wraps up, tracked against the GCP trial's remaining
      credit/day window.

---

## Appendix A — Full decisions index (D1-D30)

| # | One-line summary |
|---|---|
| D3 | Stale active GCP project caused a misdirected resource creation — always verify `gcloud config list` first |
| D4 | Why all three orchestration options (C/B/A) are being built, not just one |
| D6 | Inter-stage handoff design: JSON file first, then direct `subprocess` invocation |
| D10 | Commit each Stage 5 outcome path separately for clean git history |
| D11 | `terraform apply` must never run unsupervised — real incident risk |
| D12 | SLSA provenance is shaped but not independently verifiable — `slsa-verifier` correctly fails |
| D17/D18 | Multi-core CPU% readings above 100% are legitimate, not a bug |
| D20 | Load generator must not self-report its own traffic to the detector — architecturally biased |
| D22 | Local dev reaches services via `kubectl port-forward` — not production-realistic, deliberately deferred |
| D23 | IsolationForest can miss a sustained incident due to `rate()`'s 5-minute smoothing |
| D24 | Prometheus's 60s default scrape interval too coarse for brief spikes — fixed to 5s |
| D25 | Stage 5's autoscaling-policy inputs hardcoded as placeholders (Stage 3 didn't exist yet) |
| D26 | `subprocess` `cwd` bug misplaced ITSM tickets/handoffs — fixed with explicit `cwd` |
| D27 | Remediation outcome taxonomy had no "correctly decided no action needed" path — fixed |
| D28 | Shared error-rate PromQL had a vector-matching bug — fixed with `sum()` + NaN guard |
| D29 | Two canary-testing infrastructure bugs: port-forward doesn't load-balance; sequential (not concurrent) polling |
| D30 | Real `default`→`orders` namespace migration history — corrected in docs |

*(D1, D2, D5, D7-D9, D13-D16, D19, D21 exist in `docs/decisions.md` but
aren't summarized here — see that file directly for the full text of
every entry.)*

## Appendix B — Suggestions for what else this guide could include

A few things worth considering adding, if you want this to be even more
complete as a standalone reference:

1. **A troubleshooting/FAQ section** — pulling together the recurring
   gotchas already scattered across `RUNBOOK.md`/`CONTINUATION.md` (the
   Docker Desktop credential-prompt hang, the `Connection reset by peer`
   race, the Docker Desktop VM-not-fully-quitting quirk) into one
   searchable list, since right now they're only discoverable by reading
   the whole document.
2. **A "if starting completely fresh" quick-start** — a condensed
   10-15 command sequence to get from a bare clone to a fully running
   cluster with all stages verifiable, for someone who doesn't want the
   full chronological narrative, just a working environment.
3. **Screenshots or terminal output samples** — this guide has the
   commands but not what successful output actually looks like (e.g.,
   what a real `conftest test` pass or a real Grafana dashboard
   incident view looks like). Not strictly necessary for a text
   audience, but would help a visual learner or a grader skimming
   quickly.
4. **A rubric cross-reference table** — this guide already implicitly
   covers every rubric line item, but an explicit table (like
   `architecture.md` §7 already has) mapping each phase above to a
   specific point value would make grading faster for whoever reviews
   it.
5. **A changelog of exact `git diff` stats per phase** — you have these
   from the actual commits; adding them here would let a reader verify
   the scope of each phase without leaving this document.
6. **A one-paragraph "if I were starting over" retrospective** — distinct
   from the report's lessons-learned section, something more candid and
   process-focused (e.g., "I'd build the version-labeled metrics into
   `app.py` from the start instead of retrofitting them for the canary")
   that might be useful for you personally on a future project, even if
   it doesn't belong in the graded report itself.

I didn't build any of these into the guide above since you didn't ask
for them specifically — flagging them as options in case any are worth
adding before you consider this fully done.
