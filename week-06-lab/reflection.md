# Week 6 Lab — Reflection

**At what level of autonomy did your agent operate? Was that the right choice?**

The agent operated at Level 2 ("draft & confirm"): it could investigate
freely, run a dry-run preview, and even formulate a full remediation plan
on its own, but the one destructive action — `execute_rollback` — required
explicit human approval before anything actually ran. This was the right
choice for a rollback. The action is reversible in principle but not free
(a rollback that turns out to be wrong is its own incident), and the cost
of a short human-in-the-loop pause is trivial compared to the cost of an
autonomous system rolling back the wrong service based on a
misinterpreted signal.

**What guardrails did you implement beyond the approval gate?**

The main additional guardrail was a *mandatory dry-run before execution* —
the system prompt required `dry_run_rollback` to run before
`execute_rollback` was ever called, so the agent always previewed the
exact version change and confirmed no migration was pending before
proposing anything irreversible. The MCP server's tool surface was also
deliberately narrow (five tools, nothing else exposed), which limits the
agent's blast radius by construction rather than by policy alone.

**What would you need to add to deploy this agent against a real Kubernetes cluster safely?**

Real metrics and logs (Prometheus/log aggregator queries instead of a
hardcoded dict), a real approval channel (Slack/PagerDuty wait-for-reply
instead of a terminal `input()`, which can't scale beyond one person at
one keyboard), scoped RBAC credentials for whatever actually executes the
rollback, and persistent audit logging of every Thought and tool call —
not just console output that disappears when the terminal closes.

**What surprised you about the agent's reasoning?**

The biggest surprise was a real bug, not a hypothetical one: my first
three runs never actually triggered the approval gate at all. The model
read "you need human approval before this" and interpreted it as a
*conversational* stopping point — it wrote out a full, well-reasoned
request for approval in plain text and then ended its turn, without ever
calling the `execute_rollback` tool. Since the approval logic lives
*inside* that tool call in my code, the gate simply never fired — the
agent looked cautious, but was actually just silently declining to act.
Fixing it required rewriting the system prompt to explicitly state that
calling the tool *is* how you request approval, not something you do
after receiving it in words.
