# CSE636 Capstone — Runbook

A command-by-command guide to reproduce every piece of the capstone built
so far. Each command includes a short explanation of what it does and
why — written so someone with the GitHub repo but none of the build
history can follow along. This is a **living document**: sections get
appended as new stages/phases are built, not rewritten from scratch.

For *why* decisions were made, see `docs/decisions.md`. For the
high-level design, see `docs/architecture.md`.

---

## 0. Prerequisites

| Tool | Why it's needed |
|---|---|
| `gcloud` CLI, authenticated | Stage 2 (IaC) provisions real GCP resources |
| `terraform` | Stage 2 — infrastructure as code |
| `conftest` | Stage 2 — OPA policy enforcement against Terraform plans |
| `slsa-verifier` | Stage 2 — verifies (and correctly rejects) the SLSA provenance document |
| Docker Desktop, with local Kubernetes enabled | Stage 4 — containerizing and deploying `order-svc`, running Prometheus/Grafana |
| `helm` | Stage 4 production-shaping — installs Prometheus and Grafana |
| Python 3.12+ | All stages |
| `pip` | Installing per-stage dependencies |
| An Anthropic API key | Stage 5's remediation agent, and (as of Phase 6) Stage 4's `rca_agent.py`, both call the Claude API |

```bash
gcloud --version
terraform --version
conftest --version
docker --version
helm version
python3 --version
```

Run these first — if any is missing, install it before continuing.

---

## 1. Clone and orient

```bash
git clone https://github.com/kuldeepjain1920/cse636-coursework.git
cd cse636-coursework
git checkout capstone-option-c
```

`capstone-option-c` is the active branch for all Option C (heterogeneous
orchestration) work — everything below assumes you're on it.

```bash
cat .gitignore
```

Confirms which files are intentionally excluded (`.env`, `venv-*/`,
`gcp-sa-key.json`, Terraform plan files) — none of these should ever be
committed, and none are needed from git; they're either regenerated
locally or must be supplied by you (the `.env` API key).

```bash
cat > .env << 'EOF'
ANTHROPIC_API_KEY=your-key-here
EOF
```

Required for Stage 5's `remediation_agent.py` and Stage 4's
`rca_agent.py`, both of which call the Claude API directly (not via
Claude Code). `python-dotenv` finds this by walking up from the current
working directory, so it works regardless of which stage's folder
you're running from.

---

## 2. Stage 2 — Agentic IaC

```bash
cd week-07-capstone/orchestrator-c-heterogeneous/iac
```

### 2.1 GCP setup

```bash
gcloud config set project cse636-capstone-iac
gcloud config list
```

Sets the active project. **Always verify this before any resource-creating
command** — a stale active project was a real cause of a misdirected
resource creation earlier in this build (see `decisions.md` D3).

```bash
gcloud services enable storage.googleapis.com
gcloud iam service-accounts create terraform-iac-demo --display-name="Terraform IaC demo"
gcloud projects add-iam-policy-binding cse636-capstone-iac \
  --member=serviceAccount:terraform-iac-demo@cse636-capstone-iac.iam.gserviceaccount.com \
  --role=roles/storage.admin
gcloud iam service-accounts keys create gcp-sa-key.json \
  --iam-account=terraform-iac-demo@cse636-capstone-iac.iam.gserviceaccount.com
```

Creates a service account scoped to `storage.admin` only (least
privilege), and generates its key. **`gcp-sa-key.json` is gitignored —
you must regenerate it yourself**, it is never present in the repo.

### 2.2 Validate and plan

```bash
terraform init
terraform validate
terraform plan -out=tfplan.binary
```

`init` downloads the Google provider; `validate` checks syntax without
touching GCP; `plan` shows exactly what would be created — this is the
step that actually authenticates against GCP using `gcp-sa-key.json`.

```bash
terraform show -json tfplan.binary > tfplan.json
```

Converts the binary plan to JSON so OPA/conftest can evaluate it.

### 2.3 Policy enforcement

```bash
conftest test tfplan.json --policy policy/
```

Runs `policy/gcs.rego` against the plan. Expected: `2 tests, 2 passed` —
the plan already satisfies both policy rules (`environment` label present
and equal to `capstone`).

### 2.4 Apply (only after human review of the plan)

```bash
terraform apply "tfplan.binary"
```

**This is the step that creates real GCP infrastructure.** It will
interactively prompt for confirmation — do not automate past this prompt.
This command should never be run by an unsupervised agent (a real
incident during this build involved exactly that risk — see
`decisions.md` D11).

### 2.5 Verify provenance and its honest limitation

```bash
shasum -a 256 gcs.tf tfplan.binary
```

Confirms `provenance.json`'s recorded hashes still match the current
files.

```bash
slsa-verifier verify-artifact tfplan.binary \
  --provenance-path provenance.json \
  --source-uri github.com/kuldeepjain1920/cse636-coursework
```

**Expected to fail** — this is intentional and correct. The command
confirms `provenance.json` is a structurally correct SLSA predicate but
not a signed, independently-verifiable attestation (no certificate, no
Rekor transparency-log entry). See `decisions.md` D12 and `iac/README.md`
for the full explanation.

---

## 3. Stage 5 — Auto-remediation

```bash
cd ~/cse636-coursework
source venv-week6/bin/activate
cd week-07-capstone/orchestrator-c-heterogeneous/remediation
```

Reuses `venv-week6` (already has `anthropic` and `python-dotenv`
installed from Week 6). This section runs `remediation_agent.py`
**standalone**, against the hand-written `stage4-incident.json` fixture
— for running it as part of the real, Phase-6-chained pipeline, see §5.6.

```bash
python3 remediation_agent.py
```

Reads `../handoffs/stage4-incident.json`. Runs the ReAct loop, and — if
all automated gates pass — pauses for human approval at
`[APPROVAL REQUIRED] execute_scale on order-svc`.

**To exercise the other guardrail paths:**

```bash
# Decline the approval prompt (type anything other than 'y')
python3 remediation_agent.py

# Kill switch — should refuse before the approval prompt ever appears
export AUTONOMY_KILL_SWITCH=off
python3 remediation_agent.py
export AUTONOMY_KILL_SWITCH=on   # reset afterward
```

**A fourth outcome, `resolved_no_action_needed`, was added during Phase 6
(§5.6)** — it only appears when a real, low-impact incident causes the
agent to correctly determine via `dry_run_scale` that no scaling is
warranted. It cannot be triggered against the original hand-written
fixture (which describes a genuine CPU-saturation incident); it requires
a real, benign incident from the Phase 4-6 chain.

Each run overwrites `../handoffs/stage5-output.json` and writes a new,
uniquely-named ticket to `itsm_tickets/` — commit each outcome separately
if you want a clean git history of each path (see `decisions.md` D10).

```bash
deactivate
```

---

## 4. Stage 4 — Observability (Steps 1-4, base build)

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability/order-svc
```

### 4.1 Run standalone (no Docker)

```bash
python3 -m venv venv-order-svc
source venv-order-svc/bin/activate
pip install -r requirements.txt
python3 app.py
```

Starts the Flask app on port 8080. In a second terminal:

```bash
curl http://localhost:8080/health
curl -X POST http://localhost:8080/order
curl http://localhost:8080/metrics
```

`/order` performs genuine CPU-bound work (repeated SHA-256 hashing) —
`cpu_pct` and `latency_ms` in the response are real measurements, not
scripted.

### 4.2 Load-test standalone

```bash
for i in $(seq 1 20); do curl -s -X POST http://localhost:8080/order & done; wait
curl http://localhost:8080/metrics
```

Fires 20 concurrent requests. Expect some `500` responses once `cpu_pct`
crosses 75% (real error correlation), and `peak_cpu_pct` in `/metrics` to
exceed the final instantaneous `cpu_pct` reading (proves the
peak-tracking fix — see §4.5).

### 4.3 Containerize

```bash
docker build -t order-svc .
docker run -d --name order-svc -p 8080:8080 order-svc
sleep 3
curl -X POST http://localhost:8080/order
docker logs order-svc
```

`sleep 3` avoids a race against the container's startup (a real
`Connection reset by peer` was hit skipping this). `docker logs` should
show the same behavior as standalone, **plus** a full OTel span object
(see §4.4) — `ConsoleSpanExporter` writes spans to stdout, which Docker
captures as container logs.

```bash
docker stop order-svc; docker rm order-svc
```

Run before any `docker run` if a container with this name already exists
— names must be unique among existing containers. **Note:** this
standalone Docker container is torn down permanently once §5 begins —
`order-svc` moves to running inside Kubernetes instead.

### 4.4 Verify OTel spans

```bash
docker logs order-svc | head -30
```

Expect a JSON span object with `"name": "order.process"`, attributes
`http.method`, `http.route`, `order.id`, `order.cpu_pct`,
`http.status_code`, `order.latency_ms` (plus `order.error_reason` on
500s), and `status.status_code` of `"OK"` or `"ERROR"`.

### 4.5 Run the load generator

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability
source order-svc/venv-order-svc/bin/activate
pip install -r requirements.txt
```

(This `requirements.txt` — in `observability/`, not `order-svc/` — is a
separate host-side dependency list; `load_generator.py` is not part of
the deployed service.)

```bash
docker stop order-svc 2>/dev/null; docker rm order-svc 2>/dev/null
docker run -d --name order-svc -p 8080:8080 order-svc
sleep 3
python3 load_generator.py
```

Drives a calm (10 requests, 1s apart) → spike (40 requests, concurrency
20) → recovery (10 requests, 1s apart) pattern. Expect: baseline all
`200`s at `cpu_pct: 0.0`; spike phase producing real `500`s correlated
with the highest `cpu_pct` readings; clean recovery back to `200`s.
Final `/metrics` summary prints at the end.

### 4.6 Cleanup between runs

```bash
docker stop order-svc; docker rm order-svc
docker images -f dangling=true
docker image prune   # optional, reclaims disk space from old rebuilds
```

---

## 5. Stage 4 — Production-shaped (Phases 1-6, all complete)

This section covers K8s deployment, Prometheus/Grafana, PromQL-based
detection, and the full chain into Stage 5. It replaces §4's standalone
Docker container — `order-svc` now runs inside Kubernetes for the rest
of the capstone.

**Every-session operational sequence** (needed every time you resume
work on this section, not just once):

```bash
kubectl cluster-info
```

Confirms Docker Desktop's Kubernetes is up. If it was closed, open Docker
Desktop and wait ~1-3 minutes before this succeeds. **Known quirk:**
closing Docker Desktop's dashboard window does not fully quit it — its
VM backend keeps running until quit via the menu bar whale icon → *Quit
Docker Desktop* (`ps aux | grep -i virtualization` to check).

```bash
kubectl get pods -n orders
kubectl get pods -n monitoring
```

Confirm `order-svc` is `1/1 Running`, and Prometheus's 5 components plus
Grafana are all `Running`.

### 5.1 Phase 1 — Deploy `order-svc` to Kubernetes

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability/order-svc/k8s
kubectl create namespace orders
kubectl apply -f deployment.yaml
```

Deploys `order-svc` as a K8s Deployment + ClusterIP Service, in its own
`orders` namespace (not `default`) for realism. `imagePullPolicy: Never`
is required — the image is only built locally, never pushed to a
registry — which means any rebuild needs an explicit
`kubectl rollout restart deployment/order-svc` to actually be picked up
(the tag never changes, so K8s won't notice a new image on its own).

```bash
kubectl get pods,deployment,service -n orders
kubectl run curltest --image=curlimages/curl --rm -it --restart=Never -n orders -- \
  curl -s http://order-svc:8080/health
```

Confirms the pod is `Running`, and that the Service correctly routes to
it from inside the cluster.

### 5.2 Phase 2 — Prometheus-format metrics endpoint

No new commands beyond a `docker build` + `kubectl rollout restart` —
`app.py` was updated to expose `/metrics/prometheus` via
`prometheus_client`, alongside (not replacing) the original JSON
`/metrics` endpoint still used by Stage 5.

```bash
docker build -t order-svc:latest .
kubectl rollout restart deployment/order-svc -n orders
kubectl run curltest --image=curlimages/curl --rm -it --restart=Never -n orders -- \
  curl -s http://order-svc:8080/metrics/prometheus
```

Expect real Prometheus text-exposition format output — `order_svc_cpu_percent`
(Gauge), `order_svc_requests_total{status}` (Counter), and
`order_svc_request_duration_seconds` (Histogram), alongside
Python/process default metrics `prometheus_client` adds automatically.

### 5.3 Phase 3 — Install Prometheus, wire the scrape target

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create namespace monitoring
```

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/k8s/monitoring
helm install prometheus prometheus-community/prometheus \
  --namespace monitoring \
  -f prometheus-values.yaml
```

`prometheus-values.yaml` already includes the D24 fix
(`scrape_interval: 5s`, `scrape_timeout: 4s`) — this is a **fresh
install**, not a reuse of Week 4's KEDA-stretch-goal Prometheus, which
had been torn down.

The Service annotations enabling scrape discovery
(`prometheus.io/scrape`, `prometheus.io/path`, `prometheus.io/port`) are
already present on `order-svc`'s Service — **must be on the Service's
metadata, not the Deployment's** (a real mistake made and corrected
during this build — see `decisions.md` for the full narrative).

```bash
kubectl get pods -n monitoring
kubectl port-forward -n monitoring svc/prometheus-server 9090:80
```

In a browser, `http://localhost:9090/targets` should show `order-svc`'s
target as `UP`, scraping `/metrics/prometheus`.

### 5.4 Phase 4 — PromQL-based anomaly detection

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability
python3 -m venv venv-anomaly-detector
source venv-anomaly-detector/bin/activate
pip install -r requirements.txt
```

`requirements.txt` here includes `requests`, `pandas`, `scikit-learn`
(for detection), plus `anthropic`/`python-dotenv` (added in Phase 6, for
`rca_agent.py`) — this single venv now covers the entire Phase 4-6 chain.

**Requires the Prometheus port-forward from §5.3 to still be running.**

```bash
python3 anomaly_detector.py
```

Queries Prometheus's `query_range` API via PromQL, feeds real data into
the unchanged `fit_detector()` (IsolationForest) logic from Week 5.
Prints how many anomalies were flagged out of how many points fetched.

**To see a real, correlated incident rather than idle noise, generate
load first:**

```bash
kubectl port-forward -n orders svc/order-svc 8080:8080
```

(separate terminal, leave running)

```bash
python3 load_generator.py
python3 anomaly_detector.py
```

### 5.5 Phase 5 — Grafana dashboard

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/k8s/monitoring
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
helm install grafana grafana/grafana \
  --namespace monitoring \
  -f grafana-values.yaml
```

`grafana-values.yaml` deliberately does NOT set an admin password —
Helm auto-generates a random one, retrieved via:

```bash
kubectl get secret --namespace monitoring grafana \
  -o jsonpath="{.data.admin-password}" | base64 --decode; echo
```

```bash
kubectl port-forward -n monitoring svc/grafana 3000:80
```

Log in at `http://localhost:3000` (`admin` / the retrieved password),
add a Prometheus datasource (`http://prometheus-server.monitoring.svc.cluster.local`,
name `order-svc-prometheus`), then **Dashboards → Import** using
`dashboard-order-svc-incident.json`.

**Known caveat:** the dashboard JSON has a hardcoded datasource UID from
the original install — on a fresh install, Grafana's import screen will
need the datasource re-mapped by name, since a fresh datasource gets a
different UID.

To see a real incident on the dashboard, generate fresh load first
(same as §5.4), then set the dashboard's time range to a window covering
when the load ran.

### 5.6 Phase 6 — Chain into Stage 5

```bash
cd ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous/observability
source venv-anomaly-detector/bin/activate
```

**Requires both port-forwards (Prometheus 9090, `order-svc` 8080) from
§5.3/§5.4 to still be running.**

```bash
python3 write_incident_handoff.py
```

Runs the full real chain: `anomaly_detector.py` → `alert_grouper.py`
(standalone copy of Week 5's `group_alerts()`, unchanged) →
`rca_agent.py` (a **real Claude API call** — deliberately NOT a copy of
Week 5's simulated `if/else` version, since a working API key is
available here) → writes the real `handoffs/stage4-incident.json`
(mapping `current_replicas` from a live `kubectl get deployment` query,
plus explicit placeholder constants for `max_replicas`/`target_cpu_pct`/
`error_budget_remaining` — Stage 3's autoscaling policy doesn't exist
yet, see `decisions.md` D25) → `subprocess`-chains into
`remediation_agent.py` (unmodified).

If the agent proposes a scale, you'll be prompted at
`[APPROVAL REQUIRED] execute_scale on order-svc`, same as §3. Depending
on the incident's real severity, you may see any of: `remediated`,
`escalated_declined`, `escalated_kill_switch`, `escalated_rate_limit`,
`escalated_error_budget`, or `resolved_no_action_needed` (this last one
added specifically to correctly represent a real, benign incident where
the agent's own dry-run confirmed no scaling was warranted —
`decisions.md` D27).

**To generate a fresh incident first** (rather than whatever's currently
in Prometheus's recent window):

```bash
python3 load_generator.py
python3 write_incident_handoff.py
```

**Verify the ticket/handoff landed in the right place:**

```bash
find ~/cse636-coursework/week-07-capstone/orchestrator-c-heterogeneous -name "TICKET-*.json"
```

Should show new tickets under `remediation/itsm_tickets/`, not
`observability/itsm_tickets/` — an earlier version of
`write_incident_handoff.py` had a `subprocess` `cwd` bug that caused
exactly this misplacement; it's since been fixed
(`cwd="../remediation"` on the `subprocess.run()` call — see
`decisions.md` D26).

### 5.7 Known, deliberate limitations (not bugs to fix casually)

- **Local dev only:** this entire chain reaches Prometheus/`order-svc`
  via `kubectl port-forward`, not via in-cluster service discovery — not
  production-realistic, deliberately deferred (`decisions.md` D22).
- **`execute_scale` remains simulated:** it updates
  `remediation_agent.py`'s in-memory state only, never calls `kubectl
  scale` — true since Stage 5's original build, not something Phase 6
  introduced, deliberately not changed (`decisions.md` D26).
- **`max_replicas`/`target_cpu_pct`/`error_budget_remaining` are
  hardcoded placeholders**, not real measured or configured values —
  Stage 3 (autoscaling policy) hasn't been built yet (`decisions.md`
  D25).

---

## 6. Common verification patterns used throughout this build

```bash
git status --ignored <path>
```

Run before every `git add`, scoped to the folder you're about to stage.
Confirms nothing sensitive (`gcp-sa-key.json`, `venv-*/`) is about to be
committed, and that expected ignores are actually taking effect.

```bash
git fetch origin
git status
```

Confirms local and remote are in sync before trusting either as ground
truth — useful after any break or when picking work back up.

```bash
docker ps
lsof -i :8080
```

Confirms what's actually running before assuming a fresh start is needed
— avoids redundant rebuilds/restarts.

```bash
kubectl get pods -n <namespace>
```

Same idea, for anything running in Kubernetes rather than plain Docker
(§5 onward) — check actual pod status before assuming a rebuild/restart
is needed, and before trusting any agent's or tool's claim of success.

```bash
find <path> -name "<pattern>"
```

Used repeatedly to confirm exactly where a file actually landed (e.g.
ITSM tickets, handoff JSON) rather than assuming a path based on the
code alone — this caught the real D26 `cwd` bug.
