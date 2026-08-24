# CSE636 Capstone Demo Script — ~15 minutes

**Presenter:** Kuldeep Jain
**Format:** live terminal + browser walkthrough, screen-shared

Speaker notes are written in first person, as what I'll actually say.
Bracketed stage directions tell me what to run or click. Timings are
approximate targets, not hard stops — I'll adjust pacing live rather
than rush a section that's going well.

---

## 0. Cold open (30 sec)

**Say:** "This is an agentic DevOps pipeline I built for `order-svc`, a
real Flask service I wrote for this capstone. Everything I'm going to
show you today is real — real Kubernetes, real Prometheus data, real
API calls, and in one case, a real production cutover that actually
happened while I was testing this. I'm not going to show you every stage
of the pipeline — some parts I deliberately didn't build, and I'll tell
you exactly which ones and why, rather than gloss over it."

**[Show]** `docs/architecture.md`'s pipeline diagram (§1) for 5 seconds,
just to orient — then move on immediately.

---

## 1. Stage 2 — Agentic IaC (2.5 min)

**Say:** "This stage generates and gates Terraform infrastructure using
an OPA policy — but the more interesting part is two things that
actually went wrong."

**[Do]**
```bash
cd week-07-capstone/orchestrator-c-heterogeneous/iac
cat gcs.tf | head -20
```
"An agent generated this — a GCS bucket config with a required
`environment=capstone` label."

```bash
conftest test tfplan.json --policy policy/
```
"That's the policy gate passing — 2 tests, 2 passed."

**Say:** "Now here's what I actually want to show you. During this
build, the agent attempted an unprompted `terraform apply` — I caught it
before anything real was created, but it's a genuine example of an
agent overreaching past what it was asked to do. Separately, I ran a
deliberate prompt-injection test, and the agent correctly refused it
three separate times, including once where the injected text directly
claimed 'I am human in the loop.' Both of those are documented verbatim
in `iac/README.md` — I'm not paraphrasing them for this demo, that's
exactly what happened."

**[Optional, if time allows]**
```bash
slsa-verifier verify-artifact tfplan.binary --provenance-path provenance.json \
  --source-uri github.com/kuldeepjain1920/cse636-coursework
```
"This is supposed to fail, and it does — it confirms my provenance
document is shaped like a real SLSA attestation but isn't independently
verifiable without a real signature. I think that honest failure is more
useful than pretending it passed."

---

## 2. Stage 4 — Observability, live incident (4 min)

**Say:** "This is the part of the pipeline I spent the most time
production-shaping. `order-svc` is running in real Kubernetes right
now, being scraped by a real Prometheus instance."

**[Do]**
```bash
kubectl get pods -n orders
kubectl get pods -n monitoring
```
"Everything here is genuinely running, not mocked."

**[Do]** Generate a real incident:
```bash
cd ../observability
source order-svc/venv-order-svc/bin/activate
python3 load_generator.py
```
"This is driving real CPU-bound work against the service — it's doing
actual SHA-256 hashing under load, not sleeping. You'll see real 500
errors show up once CPU crosses about 75%."

**[Do]** Chain into detection and remediation:
```bash
source venv-anomaly-detector/bin/activate
python3 write_incident_handoff.py
```
"This runs the full real chain — anomaly detection against live
Prometheus data, an incident-grouping step, and then a real Claude API
call reasoning about root cause from the actual measured CPU and error
numbers. If it hands off to the remediation agent, I'll show that next."

**[If prompted for approval]** "This is Stage 5's human-approval gate —
one of four layered safety controls before any scaling happens." Approve
or decline live, narrating whichever outcome results.

**Say (bridge):** "One real bug worth mentioning here: the error-rate
calculation in this pipeline was silently wrong for a while — a
Prometheus query vector-matching issue that made it either read exactly
100% error rate or a masked zero, never the real number. I found and
fixed that while building the next stage, and I'll show you the fix in
a minute."

---

## 3. Stage 3 — Predictive deploy and the real canary (5.5 min)

**Say:** "This is the stage I want to spend the most time on, because
what went wrong here taught me the most."

**[Do]** Show the risk scorer:
```bash
cd ../predictive-deploy
python3 risk_scorer.py
```
"Three real inputs here — current CPU and error rate from Prometheus, a
freshly re-run OPA policy check against Terraform, and the live replica
count from `kubectl`. Nothing here is faked or cached."

**Say:** "Now the canary. I built two real, separately tagged container
images — v1 and v2 — where v2 does half the CPU work per request of v1.
A genuine performance difference, not a cosmetic one."

**[Do]**
```bash
kubectl get deployments -n orders
```
"Notice `order-svc` is at zero replicas and `order-svc-v2` is the one
actually running. That's not broken — that's the result of a real
canary promote I'm about to walk you through how I got to."

**Say:** "The first time I ran this comparison for real, I got a result
that looked like v2 was perfect — zero CPU, zero errors. That was wrong.
`kubectl port-forward` to a Kubernetes Service doesn't load-balance — it
pins to one pod — so my test traffic never reached v2 at all. I fixed
that by generating traffic from inside the cluster instead."

**[Do]** Demonstrate the in-cluster traffic pattern:
```bash
kubectl run canary-load --image=curlimages/curl --rm -it --restart=Never -n orders -- \
  sh -c 'for i in $(seq 1 100); do curl -s -X POST http://order-svc:8080/order > /dev/null; done'
```

**Say:** "There was a second bug, subtler than the first — my original
comparison script polled v1 and v2 in two separate windows, one after
the other, rather than at the same time. So I wasn't comparing them
fairly, I was comparing two different moments. I fixed that so both
versions get sampled together."

**[Do]** Run a dry-run to show the real comparison:
```bash
python3 canary_controller.py --dry-run
```
"This is pulling real, simultaneous CPU and error-rate averages for
both versions and making a genuine promote-or-rollback decision."

**Say:** "And this part actually happened for real, not as a demo
convenience — I ran this without `--dry-run` during testing, it decided
to promote, and it genuinely executed `kubectl scale` to cut traffic
over. `order-svc-v2` has been the live production deployment ever
since. That's what you saw a minute ago in `kubectl get deployments`."

---

## 4. Honest scope statement (1.5 min)

**Say:** "I want to be direct about what's not here, rather than let it
come up as a surprise. I did not build Stage 3's FinOps cost-estimation
phase, or the final orchestrator step that would chain risk-scoring,
the canary, and cost estimation together with Stages 2 and 4. I also
only built one of the three orchestration approaches the assignment
allows — the heterogeneous-platforms one you've seen today — not the
GitHub Actions or single-script versions. And in Stage 5, the actual
`kubectl scale` call is still simulated — it updates in-memory state,
not the real cluster — which is a real limitation I decided not to
close for this submission. None of these are things I ran out of time
on by accident; they're deliberate scope decisions I made because I'd
rather show you fewer things that are genuinely real and debugged than
more things that are simulated or shallow."

---

## 5. Close (1 min)

**Say:** "Across this project I logged thirty real decisions — not
design choices I made in the abstract, but things that actually broke,
actually surprised me, or actually needed fixing once I ran real
infrastructure against real data. The vector-matching bug in the
error-rate query, the port-forward load-balancing issue, the sequential-
versus-concurrent polling bug — none of those would have surfaced from
a simulated pipeline. I think that's the strongest evidence this project
gives for what I actually learned this term: not that I can wire five
stages together, but that I can find, diagnose, and fix the kind of
subtle infrastructure bugs that only show up when something is genuinely
running."

**[End]** Offer to answer questions, or open `docs/decisions.md` live if
anyone wants to see a specific finding in more detail.

---

## Timing summary

| Section | Target time |
|---|---|
| Cold open | 0:30 |
| Stage 2 — IaC | 2:30 |
| Stage 4 — Observability | 4:00 |
| Stage 3 — Predictive deploy / canary | 5:30 |
| Honest scope statement | 1:30 |
| Close | 1:00 |
| **Total** | **~15:00** |

## Fallback plan if something doesn't run live

- If `load_generator.py` or the incident chain doesn't produce a clean
  incident live, fall back to narrating the pre-captured evidence:
  `remediation/itsm_tickets/TICKET-34cd34f0.json` (the real
  `resolved_no_action_needed` outcome) and the RCA reports in
  `observability/output/`.
- If the canary comparison doesn't show a clean result live (e.g. no
  traffic reached both pods in time), fall back to
  `handoffs/stage3-canary.json`, which has the real, already-verified
  result (`v1: 26.24% CPU`, `v2: 7.1% CPU`, decision: promote) from the
  actual executed run.
- If Docker Desktop / K8s isn't fully up when the demo starts, run
  `kubectl cluster-info` first as a visible sanity check before anything
  else — narrate the ~1-3 minute startup wait rather than let it be a
  silent dead pause.
