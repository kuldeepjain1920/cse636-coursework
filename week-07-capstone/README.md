# CSE636 Capstone — Agentic DevOps Pipeline for order-svc

**Kuldeep Jain · CSE636, DevOps for AI · CSTU**
**Branch:** `capstone-option-c`

An agentic DevOps pipeline integrating IaC, predictive deployment,
observability, and auto-remediation into one system operating against a
real service (`order-svc`) — built with a deliberate emphasis on real
infrastructure over simulation: real Kubernetes, real Prometheus data,
real API calls, and a real executed canary promote.

**Start here if you're grading or reviewing this project** — the rest
of this README tells you what's built, what isn't, and where to look
for evidence of each.

---

## Read this first

| Document | What it's for |
|---|---|
| **`docs/capstone-report.md`** | The written report (Document 6) — start here for a narrative account of the whole project |
| **`docs/demo-script.md`** | 15-minute live-demo walkthrough (Document 7), with the exact commands used |
| **`docs/architecture.md`** | Design, diagrams, and the rubric-mapping table (§7) — what satisfies each grading criterion |
| **`docs/RUNBOOK.md`** | Every command needed to reproduce every stage, organized by finished stage |
| **`docs/decisions.md`** | Chronological log of every real decision and bug found (D1-D30), with reasoning |
| **`docs/CONTINUATION.md`** | Full project state — repo structure, environment reference, open items |
| **`docs/MASTER-GUIDE.md`** | Everything above, combined into one linear, chronological build narrative |

If you only read one thing: **`docs/capstone-report.md`**. If you want
to run something live: **`docs/RUNBOOK.md`** or **`docs/demo-script.md`**.

---

## What's actually built

| Stage | Status |
|---|---|
| Stage 2 — Agentic IaC | ✅ Done, fully verified (Terraform + OPA/conftest + SLSA provenance) |
| Stage 4 — Observability | ✅ Done, fully production-shaped (K8s + Prometheus + Grafana + real anomaly detection → RCA chain) |
| Stage 5 — Auto-remediation | ✅ Done, all 4 outcome paths verified against real behavior |
| Stage 3 — Predictive deploy | 🔶 Phases 1-2 done — real risk scoring + a **real, executed canary promote**. Phases 3-4 (FinOps, full orchestrator wiring) not built |
| Full 5-stage end-to-end wiring | 🔶 Stages 4→5 chained via `subprocess`; Stage 3 built and verified standalone, not yet wired in |
| Orchestration options | Only **Option C** (heterogeneous platforms) built. Options B (GitHub Actions) and A (single script) not started |

**This is a deliberate scope decision, not an oversight** — see
`docs/capstone-report.md` §3 for the full statement of what's out of
scope and why.

**Current live state:** `order-svc-v2` is the production deployment as
of a real canary promote executed during Stage 3 Phase 2 testing.
`order-svc` (v1) is intentionally left at 0 replicas, not deleted, to
preserve rollback capability. This is expected, not broken — see
`docs/CONTINUATION.md` §3 before assuming otherwise.

---

## Real findings worth knowing about before you dig in

This project treats bugs found during real testing as evidence, not
something to quietly fix and hide. Thirty decisions are logged in
`docs/decisions.md`; a few of the more notable ones:

- **D28** — a real PromQL vector-matching bug silently broke error-rate
  calculations across two scripts since Stage 4, masked by an unrelated
  `.fillna(0.0)` call. Found, diagnosed, and fixed.
- **D29** — two real canary-testing infrastructure bugs: `kubectl
  port-forward` to a Service doesn't load-balance (so a comparison read
  one version as falsely idle), and an original polling design compared
  the two versions across two different windows of time rather than
  concurrently. Both found and fixed before the real promote was
  executed.
- **Two genuine, unstaged agent-behavior incidents** in the IaC lab: an
  unprompted `terraform apply` attempt, and a correctly-refused
  prompt-injection sequence — see `orchestrator-c-heterogeneous/iac/README.md`.

## Repo structure

```
week-07-capstone/
├── docs/                          [all documentation — see table above]
└── orchestrator-c-heterogeneous/  [Option C: the built implementation]
    ├── iac/                       [Stage 2]
    ├── remediation/               [Stage 5]
    ├── observability/             [Stage 4, incl. order-svc]
    ├── predictive-deploy/         [Stage 3, Phases 1-2]
    ├── k8s/monitoring/            [Prometheus/Grafana Helm configs]
    └── handoffs/                  [inter-stage JSON audit trail]
```

Full detail: `docs/CONTINUATION.md` §4.

---

## Environment quick-start

```bash
git clone https://github.com/kuldeepjain1920/cse636-coursework.git
cd cse636-coursework
git checkout capstone-option-c
cd week-07-capstone
cat docs/RUNBOOK.md   # start here to reproduce anything
```

Full prerequisites and credentials reference: `docs/RUNBOOK.md` §0,
`docs/CONTINUATION.md` §3.
