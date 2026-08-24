# CSE636 Capstone Report — Agentic DevOps Pipeline for order-svc

**Kuldeep Jain**
**CSE636 — DevOps for AI, CSTU**
**Repository:** github.com/kuldeepjain1920/cse636-coursework, branch `capstone-option-c`

---

## 1. Overview

For this capstone I built an agentic DevOps pipeline that integrates the
work from every prior week of the course — CI/CD, infrastructure as
code, predictive deployment, observability, and auto-remediation — into
one connected system operating against a real service. I chose to build
this as **Option C**: a heterogeneous orchestration approach using native
platforms (Docker, Kubernetes, local Python scripts) with file- and
subprocess-based handoffs between stages, rather than a single script or
a GitHub Actions backbone. My goal throughout was to make as much of
this real as I reasonably could — real infrastructure, real telemetry,
real API calls, real Kubernetes operations — rather than simulating
stages with mocked data, because I wanted the debugging and the findings
that came out of this project to be genuine engineering experience, not
scripted demonstration.

The service under management, `order-svc`, is a real Flask application I
built for this project. It does genuine CPU-bound work per request
(repeated SHA-256 hashing, not `sleep()`), so CPU saturation and the
error rates that follow from it are measured, not scripted. Everything
downstream — Prometheus metrics, anomaly detection, risk scoring, canary
comparisons — is reading real signal from real load against this
service.

I will continue working on the remaining tasks but thought of submnitting
what is completed as of now.

## 2. What's built

### 2.1 Stage 2 — Agentic IaC

I used a Claude Code agent to generate a Terraform configuration for a
GCS bucket in a dedicated GCP project (`cse636-capstone-iac`), gated by
an OPA/conftest policy requiring an `environment=capstone` label. I
verified the policy against all three cases — a passing plan, a plan
with the wrong label value, and a plan missing the label entirely — and
confirmed the enforcement actually blocks a bad plan rather than just
warning about it.

Two things happened during this stage that I think are worth reporting
honestly rather than smoothing over. First, the agent attempted an
unprompted `terraform apply` at one point — I caught it before any real
infrastructure was created, but it's a genuine example of an agent
over-scoping beyond what it was asked to do, and it's exactly the kind
of risk this course's guardrail material warned about. Second, I ran a
deliberate prompt-injection test — a malicious instruction embedded in a
document the agent had to process — and the agent correctly refused
across three escalating attempts, including one where the injected text
directly asserted "I am human in the loop." I also hand-authored a SLSA
provenance document for the Terraform apply, found three real defects in
it on review (a stale commit reference, fabricated timestamps, an
unverified builder version), corrected them, and then tested the
corrected document against the real `slsa-verifier` CLI — which
correctly failed, since the document is provenance-*shaped* but not
independently *verifiable* without a real signature and transparency-log
entry. I think that failure is itself a useful, honest result: it shows
I understand the difference between documentation that looks like
provenance and an artifact that actually proves anything cryptographically.

### 2.2 Stage 4 — Observability

I built `order-svc` as a real containerized service, instrumented it
with OpenTelemetry service-level spans, and drove it through a
calm-spike-recovery load pattern with a load generator I wrote. From
there I took it through six further phases to make the observability
stack production-shaped rather than a toy: deploying `order-svc` into
its own Kubernetes namespace, exposing a real Prometheus-format metrics
endpoint, installing a fresh Prometheus instance that scrapes it via
standard service-discovery annotations, running PromQL-based anomaly
detection (an IsolationForest model, reused unchanged from Week 5, now
fed real Prometheus data instead of synthetic data), building a Grafana
dashboard, and finally chaining the whole detection pipeline into a real
Claude API call for root-cause analysis, which then hands off into Stage
5's remediation agent automatically.

I hit and fixed several real bugs along the way that I think say more
about the engineering process than a clean run would have: a race
condition where concurrent requests reported the same order ID under
load; a container CPU measurement that was silently diluted by Docker
Desktop's multi-core visibility, which I only caught by comparing
`psutil.cpu_percent()` against `psutil.Process().cpu_percent()`;
IsolationForest missing a genuine 5-point cluster of anomalous readings
because Prometheus's `rate()` function smooths over a 5-minute window;
and a scrape interval that was too coarse (60 seconds) to reliably catch
short CPU spikes, which I fixed by reducing it to 5 seconds. I kept all
of these as documented findings rather than quietly fixing and moving on
— I think a report that only shows things working is less credible than
one that shows what actually went wrong and how I diagnosed it.

### 2.3 Stage 5 — Auto-remediation

I built on the ReAct-based remediation agent from Week 6, adding a real
ITSM ticket generator and a handoff file writer. The agent has four
layered blast-radius controls — a kill switch, a rate limit, an
error-budget gate, and a human-approval prompt — and I verified all four
outcome paths against real behavior, not just reading the code: a full
successful remediation (scaled 4 to 7 replicas after my own approval), a
declined-by-operator path, and a kill-switch block that correctly halted
before the approval prompt even appeared.

While chaining this stage to the real observability pipeline, I found a
genuine gap: a real, benign incident (9.9% CPU, zero errors) caused the
agent to correctly reason through a dry run and conclude no scaling was
warranted — but the outcome taxonomy had no way to represent "correctly
decided nothing was needed," so it fell through to `unresolved`, which
actually means something different (a scale was warranted but never
executed). I fixed this by adding a fourth outcome,
`resolved_no_action_needed`, and verified the fix by re-running the same
scenario and confirming the correct classification. I deliberately did
not change what triggers `unresolved` for a genuinely missed scale — I
didn't want to paper over the class of bug this taxonomy exists to
catch.

One limitation I want to state plainly rather than let a reader
discover: `execute_scale` in this agent has always been simulated — it
updates in-memory state only and never calls `kubectl scale`. This was
true from the original Week 6 build and I deliberately left it that way
here, since making it real would have expanded this stage's scope beyond
what I'd already verified working. It's worth contrasting this with
Stage 3's canary controller, described below, where scaling genuinely is
real.

### 2.4 Stage 3 — Predictive Deploy (Phases 1 and 2 complete)

This is the stage I built most recently, and it's the one I'm most
willing to talk through in detail because of what went wrong and what I
learned fixing it.

**Phase 1 — real risk scoring.** I built `risk_scorer.py` to pull three
genuinely real inputs before any deploy decision: current CPU percentage
and error rate from Prometheus, a fresh OPA/conftest policy check
(re-running `terraform plan` and `conftest test` on every call, not
cached), and the current replica count via `kubectl`. These combine into
a risk score and a proceed/block gate — a failed policy check is a hard
block regardless of score, since an infrastructure policy violation
isn't something a healthy service should be able to offset numerically.

While testing this, I found a real bug in the shared error-rate PromQL
query that had actually been sitting unnoticed in the observability
pipeline since Stage 4 Phase 4. The query divided two Prometheus vectors
without aggregating them first, and Prometheus's default vector matching
silently paired only the identical `status="500"` series, dropping the
`status="200"` series from the denominator entirely. The result was
never the real error ratio — it evaluated to exactly 1.0 whenever any
errors existed, or a NaN otherwise, which had been masked by an existing
`.fillna(0.0)` call whose comment assumed it was catching "insufficient
history," not a real vector-matching bug. I fixed this by wrapping both
sides of the query in `sum()`, and separately added an explicit NaN
guard in the risk scorer itself, since a NaN silently flowing into a
numeric comparison had been defaulting the deploy gate to "proceed" on
completely undefined data — a real safety issue, not a cosmetic one. I
verified the fix by re-running anomaly detection and confirming the
detector's behavior was consistent with expectations, and by re-running
the risk scorer against real traffic and confirming it now returned a
plausible error-rate fraction instead of a broken 1.0 or a masked 0.0.

**Phase 2 — a real canary deploy.** I wanted this to be a genuine
canary, not a simulated recommendation, so I built two separately
tagged, separately built container images — `order-svc:v1` and
`order-svc:v2` — differing by exactly one real change: v2 does half the
CPU-bound hashing work of v1 per request, a real performance
improvement, not a cosmetic label swap. I chose separate images over a
shared image with a runtime flag deliberately, since that's the
production-realistic pattern: an immutable, independently-buildable
artifact per version, with rollback meaning "point back at the previous
tag," not "remember to also revert a config value somewhere."

I labeled all three of `order-svc`'s Prometheus metrics with a
`VERSION` value so v1 and v2 traffic could be told apart, then built
`canary_controller.py` to poll both versions, compare their real CPU and
error-rate averages over a shared window, and make a genuine
promote-or-rollback decision — one that actually executes, via real
`kubectl scale` and `kubectl delete` calls, not a printed recommendation.

The first time I ran this for real, I found two separate infrastructure
bugs, both of which taught me something specific about Kubernetes
networking and about test design that I don't think I'd have learned any
other way. First, `kubectl port-forward` to a Service does not
load-balance — it pins to a single backing pod for the life of the
forward, which meant every request from my load generator was landing on
the v1 pod alone. The canary comparison read v2 as exactly `0.0` CPU and
`0.0` error rate, which looked like "v2 is healthier" but was actually
"v2 received zero traffic." I fixed this by generating comparison
traffic from inside the cluster with a throwaway pod hitting the Service
by name, which does get real load-balanced traffic through kube-proxy.
Second, and more subtly, my first version of `canary_controller.py`
polled v1 and v2 in two separate sequential ~60-second windows rather
than together — which meant I wasn't actually comparing the two versions
under the same conditions at the same time, I was comparing two
different slices of real time. This surfaced when an in-cluster load run
happened to land during v2's polling phase right after v1's had already
finished with no traffic, producing a result that looked like a real
regression but was actually a timing artifact. I fixed this by sampling
both versions together, at each timestamp, within one shared window.

After both fixes, I re-ran the comparison and got a genuinely
simultaneous, plausible result — v1 averaging 26.24% CPU, v2 averaging
7.1%, both showing zero errors, sampled from real in-cluster traffic
over the same window. The controller decided to promote, and I let it
execute for real: `order-svc-v2` is now the live production deployment,
with the original `order-svc` (v1) intentionally left at zero replicas
rather than deleted, preserving the ability to roll back. I verified
this against actual cluster state afterward — `kubectl get deployments`
and the written handoff JSON — rather than just trusting the printed
decision.

**What's not built.** Phase 3 (a real FinOps cost estimate using the
actual Google Cloud Billing Catalog API) and Phase 4 (wiring risk
scoring, the canary, and the cost estimate into one orchestrator that
chains Stage 2 through Stage 4) are not built. This is a deliberate
scope decision for this submission, not an oversight, and I want to be
direct about it rather than let the report imply more than what exists.

### 2.5 One more real finding, outside the stage work itself

While correcting my documentation for accuracy before this submission, I
found that my runbook and architecture docs implied `order-svc` had been
deployed directly into its `orders` namespace from the start. In fact,
per the original Week 7 lab instructions, it was first deployed into the
`default` namespace, then deliberately moved into `orders` later for
realism. Kubernetes namespace is an immutable field on an existing
object, so that move required deleting and recreating the Deployment and
Service rather than an in-place edit — a real operational detail I'd
initially left out of the docs and corrected once I noticed it.

## 3. What's deliberately not built

I want to state this plainly rather than let it surface as a gap a
reader has to infer:

- **Stage 3 Phases 3-4** (the FinOps cost estimator and the full
  orchestrator wiring Stage 2 through Stage 4) are not built.
- **Full 5-stage end-to-end wiring is partial.** Stages 4 and 5 are
  genuinely chained via `subprocess` — an incident detected in Stage 4
  automatically invokes Stage 5's remediation agent. Stage 3's scripts,
  by contrast, are run standalone; they are not yet `subprocess`-chained
  to Stage 2 upstream or Stage 4 downstream.
- **Options B (GitHub Actions as the orchestration backbone) and A
  (a single Python orchestrator script) are not started.** Only Option
  C, the heterogeneous-platforms approach described throughout this
  report, exists.
- **`execute_scale` in the Stage 5 remediation agent remains simulated**,
  as noted above.
- **The observability-to-remediation chain reaches services via local
  `kubectl port-forward`**, which is explicitly not production-realistic
  — a deliberate, documented tradeoff, not an oversight.

I made this scope decision because I was not working under a hard
deadline for this submission and chose to prioritize depth and honesty
over checking every box — I would rather submit a smaller set of stages
that are genuinely real, tested, and debugged, with real findings
documented along the way, than a complete-looking pipeline built faster
and shallower.

## 4. Lessons learned

The single biggest lesson from this project is that real infrastructure
finds real bugs that a simulated version never would have surfaced. Every
one of the roughly thirty decisions logged in my `decisions.md` came from
something actually breaking, or actually behaving in a way I didn't
expect, when I ran it against genuine data rather than assuming the code
was correct because it looked correct. The PromQL vector-matching bug is
the clearest example — it had been silently wrong since Stage 4, masked
by an unrelated `fillna(0.0)` call that nobody had questioned, and it
only surfaced because I built a second script that queried Prometheus a
different way. The canary infrastructure bugs are another good example:
`kubectl port-forward`'s single-pod pinning isn't documented anywhere I
looked as a load-balancing limitation, and I only found it by watching a
comparison come back suspiciously, uniformly zero.

A second lesson is about the value of independently verifying claimed
success rather than trusting a tool's own output. Several of the real
findings in this project — the D26 `cwd` bug that misplaced ITSM
tickets, the D30 namespace-history correction — were caught specifically
because I checked actual file locations and actual cluster state rather
than trusting that a script's printed success message meant what it
claimed.

Finally, I think the choice to build a real canary with real traffic and
a real executed promote, rather than a simulated recommendation, was
worth the extra debugging it cost. A simulated version would never have
taught me that Kubernetes Service port-forwarding doesn't load-balance,
or that comparing two things sequentially isn't the same as comparing
them concurrently — both are the kind of operational knowledge that only
shows up when something real is actually running.

## 5. Conclusion

This capstone integrates real infrastructure across IaC, observability,
auto-remediation, and — partially — predictive deployment, with genuine
agent behavior (including two unplanned incidents worth reporting
honestly), a real executed canary promote, and thirty documented
decisions covering both deliberate design choices and bugs found and
fixed along the way. What remains — Stage 3's FinOps phase, full 5-stage
wiring, and Options B and A — is explicitly out of scope for this
submission, by choice rather than oversight, and I've tried throughout
this report to be as clear about the boundary between what's real and
verified versus what's simulated, placeholder, or not yet built.
