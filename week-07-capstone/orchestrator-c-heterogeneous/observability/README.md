# Capstone Stage 4 — Observability

**Kuldeep Jain | CSE636 — DevOps for AI | August 2026**

Repository: `cse636-coursework`, branch `capstone-option-c`
Path: `week-07-capstone/orchestrator-c-heterogeneous/observability/`

This document covers Steps 1–4 of Stage 4 (a real, containerized
service, verified end to end). Steps 5–6 (production-shaped Prometheus/K8s
pipeline, bridging into Stage 5) are covered separately once built — see
`docs/RUNBOOK.md` §5 for current status.

---

## 1. Overview

Stage 4 builds the "Observability" stage of the capstone pipeline: a real
deployed service (`order-svc`), instrumented with OpenTelemetry
service-level spans, driven through a realistic incident lifecycle by a
load generator. This replaces synthetic/scripted metrics with genuinely
measured CPU pressure and error correlation.

**Design decision (full reasoning: `docs/decisions.md` D13):** rather
than reuse Week 0's starter app (lower effort, less new learning) or use
purely synthetic data (least new learning), a new service was
purpose-built from scratch — chosen deliberately for maximum hands-on
practice.

---

## 2. `order-svc` — the service

A Flask app with three endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `POST /order` | Genuine CPU-bound work (repeated SHA-256 hashing), correlated 500 errors once measured CPU pressure crosses a threshold |
| `GET /metrics` | Current + peak CPU, request/error counts |

**Why real CPU-bound work, not `sleep()`:** so that concurrent load
genuinely competes for real CPU cycles, and the resulting error
correlation is *measured*, not scripted — the RCA conclusion ("CPU
saturation likely driving...") is earned from real data (`decisions.md`
D14–D15).

---

## 3. Real bugs found and fixed during testing

### 3.1 Race condition (standalone testing)

Under concurrent load, every response in a burst reported the same
`order_id` — the JSON response was reading the shared global
`_request_count` again at response-build time, not a snapshot from when
the request started. **Fix:** snapshot `order_id = _request_count`
immediately after incrementing, before any other request can mutate it.

### 3.2 Metrics snapshot-timing gap

A single `/metrics` call taken *after* a load burst showed CPU back near
0%, completely missing a mid-burst peak of 100%. **Fix:** added
`_peak_cpu_pct` tracking (a running `max()`), reported alongside the
instantaneous reading. **Broader lesson (kept for the capstone report):**
point-in-time metric snapshots can silently miss transient spikes that
have already resolved — a real argument for continuous/scraped
monitoring over ad hoc checks.

### 3.3 Container CPU measurement — two rounds of debugging

The same load burst that hit 100% CPU standalone showed only ~12-14%
inside a Docker container. **First attempted fix:** `docker run --cpus=1`
— did not work, since cgroup CPU quotas throttle execution but don't
change what `psutil.cpu_count()` *reports* inside Docker Desktop's Linux
VM (still sees all the VM's cores). **Actual fix:** switched from
`psutil.cpu_percent()` (system-wide) to `psutil.Process().cpu_percent()`
(per-process, normalized to one core). This also means readings can
legitimately exceed 100% — e.g. 290% means the process consumed ~2.9
cores' worth of CPU time concurrently, which is real (Python's `hashlib`
releases the GIL during hashing, allowing genuine multi-core
parallelism). **Decision: left uncapped, not clamped to 0-100** — real
tools (Prometheus/cAdvisor/Kubernetes) report multi-core usage the same
way, and clamping would have broken the error-probability formula's
gradation. Full reasoning: `docs/decisions.md` D17–D18.

---

## 4. OpenTelemetry instrumentation

Each `/order` request is wrapped in an `order.process` span, using
standard `http.*` semantic conventions — deliberately distinct from Week
5's `gen_ai.*` agent-level spans, since this is service telemetry, not
LLM-call telemetry.

**Attributes captured:** `http.method`, `http.route`, `order.id`,
`order.cpu_pct`, `http.status_code`, `order.latency_ms`, and
`order.error_reason` on failures. `span.set_status()` correctly reflects
`OK`/`ERROR`.

**Verified in two contexts:** standalone (`python3 app.py`) and inside
Docker (`docker logs order-svc`) — `ConsoleSpanExporter` correctly
surfaces the full span object in both, confirming the same exporter
mechanism used here will work when captured for the production-shaped
pipeline.

---

## 5. Load generator — the incident lifecycle

`load_generator.py` drives `order-svc` through a **calm → spike →
recovery** pattern, matching the `INC-002` incident narrative already
established in Weeks 5–6:

- **Baseline:** 10 requests, 1 second apart
- **Spike:** 40 requests, concurrency 20 (the incident)
- **Recovery:** 10 requests, 1 second apart

**Verified real run:** baseline 10/10 succeed at `cpu_pct: 0.0`; spike
phase produces 13/40 real errors (32.5%), with `peak_cpu_pct` reaching
212.4% and errors correlating with the highest-pressure requests while
lower-pressure concurrent requests in the same window still succeed
(genuine, messy real-world behavior, not a clean on/off switch); recovery
returns cleanly to `200`s at `cpu_pct: 0.0`.

This is the complete, real data source that Stage 4's remaining
production-shaped work (Prometheus scraping, PromQL querying,
`anomaly_detector.py`) will consume — see `docs/RUNBOOK.md` §5 for that
work once built.

---

## 6. Repository state

- Branch: `capstone-option-c`
- Committed: `order-svc/app.py`, `order-svc/Dockerfile`,
  `order-svc/.dockerignore`, `order-svc/requirements.txt`,
  `load_generator.py`, `requirements.txt` (host-side, separate from
  `order-svc/`'s own)
- Excluded (verified via `git status --ignored`): both venvs
  (`order-svc/venv-order-svc/`), covered by the root `.gitignore`'s
  `venv-*/` pattern
- Commits: `1583769` (standalone service), `b09ed39` (containerize +
  CPU-metric fix), `369b86c` (OTel instrumentation), `cac93c9` (load
  generator)
