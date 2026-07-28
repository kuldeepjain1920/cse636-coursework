# Guardrails: Auto-Remediation Agent (Missing Dependency)

## Approval gate
The agent (scripts/remediation_agent.py) never merges its own PR. It opens
a branch (bot/fix-deps-<run-id>) and a PR; a human must review and merge.

## Blast-radius limits
- The agent can ONLY modify requirements.txt -- no other file, ever.
- It can only APPEND a line -- it never removes or rewrites existing lines
  (enforced in code: new_text = current_text + new_line, not a full rewrite).
- It only acts on ONE narrow failure signature: ModuleNotFoundError. A cheap
  regex pre-check runs before ever calling the Anthropic API, so unrelated
  failures never reach the agent at all.
- The GH_TOKEN credential is scoped to open PRs; it cannot merge or push to
  a protected branch directly.

## What it is explicitly NOT allowed to do
- Modify source code, tests, CI workflow files, or any file besides
  requirements.txt.
- Guess at a fix when the log does NOT contain a ModuleNotFoundError --
  it explicitly reports "nothing to remediate" instead.
