# Build-Fixer Agent — Week 3 (runnable demo)

A minimal, runnable version of the **Week 3 lab**: a CI pipeline detects a
failing test, an AI agent reads the build log, proposes the *minimal* fix, and
opens a pull request that **a human must approve before it can merge**. The
approval gate is the point — see [week-03-notes.md](../../weeks/week-03/week-03-notes.md)
on guardrails and blast-radius limits.

This starter mirrors the others (`Makefile`, a unit-tested pure core, a heavier
driver). The pure core ([scripts/logparse.py](scripts/logparse.py)) parses
pytest output with no dependencies and is covered by `make test`. The driver
([scripts/build_fixer_agent.py](scripts/build_fixer_agent.py)) calls Claude and
needs the `anthropic` SDK.

## Layout

| Path | What it is |
|---|---|
| [src/calculator.py](src/calculator.py) | A deliberately buggy app (`add` subtracts) — the red build |
| [tests/test_calculator.py](tests/test_calculator.py) | `test_add` fails, `test_multiply` passes |
| [scripts/logparse.py](scripts/logparse.py) | Pure pytest-log parser (unit-tested core) |
| [scripts/build_fixer_agent.py](scripts/build_fixer_agent.py) | The agent: log → Claude → proposed fix → PR |
| [.github/workflows/ci.yml](.github/workflows/ci.yml) | `test` job + gated `agent-fix` job |
| [mcp_servers/actions_status.py](mcp_servers/actions_status.py) | Week 2 MCP server (GitHub Actions variant): reports this repo's CI status to Claude Code |

## Run it locally (no GitHub needed)

You only need an Anthropic API key for the agent; the parser tests need nothing.

```bash
make setup                      # venv + pytest + anthropic + PyGithub
make test                       # pure log-parser tests — should pass (4 passed)

export ANTHROPIC_API_KEY=sk-ant-...
make demo                       # produce the red build, then print the agent's fix
```

`make demo` runs the buggy tests into `build_log.txt`, then dry-runs the agent,
which prints the root cause and the corrected file **without opening a PR**.
Set `MODEL=claude-haiku-4-5` for a cheaper run (defaults to `claude-opus-4-8`).

## Run it as CI with the approval gate (GitHub)

1. Push the **contents** of this folder as a new GitHub repo (so `ci.yml` lands
   at the repo root — GitHub only runs workflows there).
2. **Settings → Secrets and variables → Actions**: add `ANTHROPIC_API_KEY` and
   `GH_TOKEN` (a token with `repo` scope).
3. **Settings → Environments → New environment** named `agent-proposed`; enable
   **Required reviewers** and add yourself. This is the approval gate.
4. Push a commit. Watch the `test` job go red, then the `agent-fix` job **pause**
   for your approval. Approve it; the agent opens a PR with the fix. Review and
   merge the PR yourself — the agent's token opens PRs but never merges.

## Week 2 bonus: ask an agent "is my build green?"

[mcp_servers/actions_status.py](mcp_servers/actions_status.py) is the GitHub
Actions counterpart to the Week 2 Jenkins MCP server. It lets Claude Code query
*this* repo's live Actions runs. Its deps are separate from the CI path:

```bash
pip install mcp requests
GH_TOKEN=<token-with-actions:read> REPO=<you>/build-fixer \
  python mcp_servers/actions_status.py        # runs standalone for a smoke test
```

Register it in `~/.claude/claude.json` and ask: *"Is the latest run on main
green?"* — full steps in [weeks/week-02/week-02-lab.md](../../weeks/week-02/week-02-lab.md)
(Part 2, GitHub Actions variant). A fine-grained PAT scoped to this one repo is
all it needs — much narrower than the Jenkins server's admin token.

## Why this shape is the guardrail

- The agent edits **one** source file, never tests or infra (enforced by the
  system prompt and reviewable in the PR diff).
- In CI it can **open** a PR but cannot **merge** — merging is a human action.
- The `agent-proposed` environment **pauses** the job until a reviewer approves;
  a timeout aborts, it never auto-approves.

Remove the human and nothing dangerous can still happen — that is the test of a
real gate.
