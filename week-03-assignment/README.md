# Week 3 Assignment — Agent-Optimized CI Pipeline

A GitHub Actions pipeline with two agent-driven features: test-impact
analysis (skip irrelevant tests) and auto-remediation of one specific
failure class (a missing `requirements.txt` entry).

## Pipeline overview

Two jobs, `select-and-test` and `remediate`, chained via `needs:`.
`select-and-test` always runs; `remediate` only runs when the first job's
tests genuinely failed. See `.github/workflows/ci.yml` (at the repo root,
since GitHub Actions only discovers workflow files there — not in a
subfolder — even though this is a subfolder-based monorepo).

## Task 1: Test-impact analysis

`scripts/select_tests.py` compares `git diff --name-only --relative HEAD~1
HEAD` against the previous commit, maps any changed `src/<name>.py` to its
matching `tests/test_<name>.py` by naming convention, and prints only the
matching test paths. The CI workflow runs only those, instead of the full
suite on every push.

**Evidence (three states verified in the Actions tab):**
- Zero `src/` changes → zero test files selected, `pytest` step skipped entirely.
- One `src/` file changed (`stringutils.py`) → exactly one test file selected
  (`test_stringutils.py`) and executed, correctly excluding the unrelated
  `test_calculator.py`.
- Repeated for `calculator.py` and `weatherinfo.py` independently, each time
  selecting only its own matching test.

**Design note:** the `--relative` flag on `git diff` is required specifically
because this repo is a subfolder-based monorepo (`week-03-assignment/` is
not the repo root) — without it, changed-file paths are reported relative to
the repo root and never match the script's `src/` prefix check.

## Task 2: Auto-remediation (missing dependency)

**Failure class:** a source file imports a package (`requests`, in
`src/weatherinfo.py`) that isn't listed in the test dependencies file,
causing `ModuleNotFoundError` in a clean CI environment.

`scripts/remediation_agent.py`:
1. Does a cheap local regex check for `ModuleNotFoundError` in the build log
   *before* ever calling the Anthropic API — unrelated failures never reach
   the agent or cost a token.
2. If found, asks Claude (structured JSON output, `output_config.format`)
   to confirm the missing package name and propose one `requirements-app.txt`
   line.
3. Opens a PR that **only appends** that one line — enforced in code
   (`current_text + new_line`, never a full-file rewrite) — and never
   merges it itself.

**Evidence:** PR #2
(https://github.com/kuldeepjain1920/cse636-coursework/pull/2) — detected
`requests`, proposed `requests>=2.28.0`, opened cleanly, reviewed and merged
manually, and a subsequent push confirmed the pipeline now passes.

## Guardrails

See `docs/guardrails.md`. Summary: the remediation agent can only ever touch
one file (`requirements-app.txt`), can only append (never rewrite/remove),
and only activates on one narrow, unambiguous failure signature. It cannot
merge its own PR; a human must.

## Reflection: what surprised me

Two real issues came up during development, both worth naming honestly:

1. **A masked failure, not a missing one.** The first attempt at the planted
   bug didn't actually fail in CI at all — `requirements.txt` bundled
   `PyGithub`, which transitively depends on `requests`, so the "missing"
   package was silently installed anyway. The fix was splitting app test
   dependencies (`requirements-app.txt`) from CI-tooling dependencies
   (`requirements.txt`) so the planted failure was genuine.
2. **The agent did exactly what it was told, to the wrong file.** After that
   split, the remediation agent's `--requirements` flag still pointed at the
   old `requirements.txt`, so it correctly diagnosed the bug and correctly
   patched *a* file — just not the one the test job actually installs from.
   The agent's reasoning wasn't wrong; a piece of wiring around it (a CLI
   flag) had gone stale after an earlier refactor. This was a good reminder
   that an agent's output is only as correct as the context and configuration
   it's given, and that "the agent worked correctly" and "the pipeline
   worked correctly" are two different claims that both need to be checked.

## AI tool use disclosure

Claude (Anthropic) was used to help design and draft `select_tests.py`,
`remediation_agent.py`, the GitHub Actions workflow, and this README. All
code was run and independently verified against real CI output (not just
local testing) before being considered working, and the two issues in the
Reflection section above were found through that verification, not assumed
away.
