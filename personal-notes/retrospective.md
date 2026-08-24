# Personal Retrospective — CSE636 Capstone

Not for submission. Just for me, for next time.

---

## What I'd do differently if I built this again

**Label everything for comparison from day one, not when I need it.**
The `VERSION` label on `order-svc`'s Prometheus metrics only exists
because Stage 3's canary needed it. If I'd added it back in Stage 4
Phase 2 when I first built the metrics endpoint, I'd have saved myself a
retrofit, and — more importantly — I'd have been in the habit of
thinking "what if I need to compare two versions of this later" much
earlier in the project. Cheap to add up front, annoying to bolt on
later.

**The first time I write a PromQL query that divides two vectors, stop
and think about label matching before trusting the number.** D28 sat
silently wrong across two separate scripts (`anomaly_detector.py` and
then `risk_scorer.py`) for what was probably weeks of real usage, masked
by a `.fillna(0.0)` call that assumed it was catching "insufficient
history." Nobody questioned that assumption until a completely
different script hit the same bug in a more visible way (a literal NaN
reaching a gate decision). The lesson isn't "check every query twice" —
it's specifically: **division of two `rate()` vectors with different
label sets is a known footgun**, and I should just know that pattern
now, the way I now know `psutil.cpu_percent()` vs.
`psutil.Process().cpu_percent()` matters inside a container.

**`kubectl port-forward` to a Service pinning to one pod is exactly the
kind of thing that's "obvious in hindsight, invisible until it bites
you."** I'd used port-forward successfully for months of this project
without ever needing it to load-balance — because nothing before the
canary needed two pods behind one Service simultaneously. The lesson
isn't really about port-forward specifically; it's a broader one: **a
tool that's worked correctly for every use case so far might still have
an untested assumption baked into how I'm using it**, and the
untested assumption only surfaces the moment the use case changes shape.
Worth asking "what would break if I needed two of these at once" earlier
in a design, not after building the thing that needs it.

**Test with real load-balanced traffic before writing the comparison
logic, not after.** I built `canary_controller.py`'s polling logic
first, then discovered the traffic-generation approach was broken.
If I'd built a tiny smoke test — "can two pods behind this Service both
independently receive traffic from outside the cluster" — as the very
first step of Stage 3 Phase 2, I'd have hit the port-forward limitation
immediately, in isolation, instead of after building the whole
comparison script around it.

**Sequential-vs-concurrent is a bug class I should watch for by
default whenever I write "compare A and B."** The `poll_and_average`
bug wasn't really about Prometheus or Kubernetes at all — it was a
general software design mistake: I wrote code that *looked* like a
comparison (two calls to the same function, one after another) but
wasn't actually comparing anything under the same conditions. That's a
pattern I should watch for any time I'm writing "get A, then get B, then
compare them" — the moment "getting A" and "getting B" both take
non-trivial time, sequential collection quietly becomes a design flaw,
not a coincidence.

## What actually worked well, worth repeating

**Writing `decisions.md` continuously, not at the end.** Having thirty
real entries with reasoning and verification attached made the report
almost write itself — I wasn't reconstructing "what did I even find"
from memory, I had it logged the moment it happened. This is the single
highest-leverage habit from this whole project and I want to carry it
into whatever I build next, capstone or not.

**Insisting on verifying claimed success independently, every time.**
Every real bug in this project — D26's `cwd` bug, D28's silent NaN, D29's
two canary bugs — was caught specifically because I checked actual state
(`cat` a file, `kubectl get` the real cluster, re-run a check) instead
of trusting a script's own printed success message. This one's worth
keeping as a hard rule, not just a nice habit.

**Choosing real infrastructure over simulation, even when it cost more
time.** Every deliberate "make this real, not simulated" decision (the
separate v1/v2 images, the real Billing API scoping, the real executed
promote instead of a dry-run-only demo) directly produced a bug I
wouldn't have found any other way. I think this is the actual thesis of
the whole project, and it held up: simulation is faster but teaches you
less.

## One thing I'm still not sure about

I deliberately left `execute_scale` in Stage 5 simulated rather than
making it real, reasoning that it would expand scope beyond what I'd
already verified. But given how much I learned from making Stage 3's
canary scaling genuinely real, I'm not fully convinced that reasoning
holds up — it's possible I left a comparably rich source of real bugs
undiscovered in Stage 5 by not doing the same thing there. Worth
revisiting if I ever pick this project back up.
