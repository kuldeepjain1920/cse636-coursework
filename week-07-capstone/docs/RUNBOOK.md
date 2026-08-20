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
| Docker Desktop, with local Kubernetes enabled | Stage 4 — containerizing and (soon) deploying `order-svc` |
| Python 3.12+ | All stages |
| `pip` | Installing per-stage dependencies |
| An Anthropic API key | Stage 5's remediation agent calls the Claude API |

```bash
gcloud --version
terraform --version
conftest --version
docker --version
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

Required for Stage 5's `remediation_agent.py`, which calls the Claude API
directly (not via Claude Code). `python-dotenv` finds this by walking up
from the current working directory, so it works regardless of which
stage's folder you're running from.

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
installed from Week 6).

```bash
python3 remediation_agent.py
```

Reads `../handoffs/stage4-incident.json` (currently a hand-written
`INC-002` fixture — will be replaced by Stage 4's real output once the
production-shaped pipeline is complete). Runs the ReAct loop, and — if
all automated gates pass — pauses for human approval at
`[APPROVAL REQUIRED] execute_scale on order-svc`.

**To exercise the other two guardrail paths:**

```bash
# Decline the approval prompt (type anything other than 'y')
python3 remediation_agent.py

# Kill switch — should refuse before the approval prompt ever appears
export AUTONOMY_KILL_SWITCH=off
python3 remediation_agent.py
export AUTONOMY_KILL_SWITCH=on   # reset afterward
```

Each run overwrites `../handoffs/stage5-output.json` and writes a new,
uniquely-named ticket to `itsm_tickets/` — commit each outcome separately
if you want a clean git history of each path (see `decisions.md` D10).

```bash
deactivate
```

---

## 4. Stage 4 — Observability (Steps 1-4, current build)

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
— names must be unique among existing containers.

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

## 5. Stage 4 — Production-shaped (Phases 1-6)

**Not yet built as of this writing.** This section will be filled in as
each phase is completed — see `docs/CONTINUATION.md` §6 for the detailed
phase-by-phase plan (K8s deployment, Prometheus scrape config, PromQL
query replacing the CSV load, Grafana dashboard, chaining into Stage 5).

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
