# Week 5 Reflection

## What worked

The full pipeline — detect, group, investigate, report, trace — ran end
to end on the first real attempt without silent failures. IsolationForest
at contamination=0.04, tuned during the Lab's sweep, correctly separated
the real 16-point incident from noise in the Assignment's grouping step
too, which was a good sign the two stages compose correctly.

## What broke

[If you did the "remove os.makedirs and rerun" exercise, describe that
bug and fix here — a genuine FileNotFoundError when telemetry.py's
exporter tries to open output/spans_sample.json before the output/
directory exists, fixed with os.makedirs(..., exist_ok=True). If you
didn't hit a real bug of your own, be upfront: "I didn't hit a build
failure of my own this time, since I started from an already-debugged
version of telemetry.py — the main iteration was in the Lab's contamination
and eps/min_samples sweeps, not in the Assignment's plumbing."]

## What I'd do differently with more time

- Wire in a real `ANTHROPIC_API_KEY` and compare the simulated
  threshold-based RCA against actual model reasoning on the same
  incident — the simulated version is honest about being low-confidence,
  but I don't know how much better a real call would actually be here.
- The DBSCAN comparison from Part A (eps=0.5 beat IsolationForest's F1,
  0.89 → 1.00) suggests it's worth trying DBSCAN as the Assignment's
  primary detector instead of IsolationForest, not just as a Lab bonus.
- Alert grouping is purely time-based right now — a real system would
  also want to correlate against deploy events or config changes in the
  same window, which this synthetic dataset doesn't have.

## Honest limitation

The RCA reports are threshold logic, not AI reasoning — "if CPU > 80%,
say CPU saturation" is a reasonable first pass but wouldn't generalize
to incident types this dataset doesn't model (e.g. a memory leak with
normal CPU, or a slow downstream dependency with no metrics of its own).

- Swap the Assignment's detector from IsolationForest to DBSCAN
  (eps=0.5, min_samples=5) — the Lab bonus showed it outperforms
  IsolationForest here (F1 1.00 vs 0.89), but I kept IsolationForest in
  the pipeline for the write-up's `contamination` framing and didn't
  circle back to swap it in.
