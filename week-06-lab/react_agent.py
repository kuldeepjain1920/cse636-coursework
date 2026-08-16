# react_agent.py
# ---------------------------------------------------------------------------
# ReAct-style agent: reasons about a simulated incident using Anthropic's
# tool_use API, and can only reach the destructive action (execute_rollback)
# through a human approval gate -- same pattern as Week 3's build-fixer
# agent pausing before a PR merge.
# ---------------------------------------------------------------------------
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()  # walks up from cwd and loads ANTHROPIC_API_KEY from the repo-root .env

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env / .env

# Tool schemas mirror the MCP server 1:1 -- in a full MCP integration these
# would be fetched live via list_tools() instead of duplicated here.
TOOLS = [
    {
        "name": "get_metrics",
        "description": "Get current error rate and latency for a service",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string", "description": "Service name"}},
            "required": ["service"],
        },
    },
    {
        "name": "get_recent_logs",
        "description": "Get recent error log lines for a service (last N lines)",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}, "tail": {"type": "integer"}},
            "required": ["service"],
        },
    },
    {
        "name": "get_deployment_history",
        "description": "Get recent deployment history for a service",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
    {
        "name": "dry_run_rollback",
        "description": "Preview a rollback without executing it. Always run this before execute_rollback.",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
    {
        "name": "execute_rollback",
        "description": (
            "Request execution of a rollback. Call this as soon as dry_run_rollback "
            "confirms it is safe -- calling it triggers a mandatory human approval "
            "pause before anything actually executes. You do not need to supply "
            "approved_by; the orchestration layer fills it in after a human confirms."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}, "approved_by": {"type": "string"}},
            "required": ["service"],
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Simulated tool execution (a real system calls the MCP server instead)."""
    if tool_name == "get_metrics":
        s = tool_input["service"]
        if s == "payment-svc":
            return json.dumps({"error_rate": 0.08, "p99_latency_ms": 450, "error_budget_remaining": 0.42})
        return json.dumps({"error_rate": 0.003, "p99_latency_ms": 120, "error_budget_remaining": 0.85})

    elif tool_name == "get_recent_logs":
        s = tool_input["service"]
        if s == "payment-svc":
            return (
                "ERROR NullPointerException in PaymentProcessor.process() line 142\n"
                "ERROR NullPointerException in PaymentProcessor.process() line 142\n"
                "WARN Cart total $12,450.00 exceeded expected range\n"
            )
        return "INFO Request processed in 115ms\nINFO Healthcheck OK"

    elif tool_name == "get_deployment_history":
        s = tool_input["service"]
        if s == "payment-svc":
            return json.dumps(
                {"current": "v1.4.2", "previous": "v1.4.1", "deployed_at": "8 minutes ago", "migration_pending": False}
            )
        return json.dumps({"current": "v2.1.0", "deployed_at": "2 hours ago"})

    elif tool_name == "dry_run_rollback":
        s = tool_input["service"]
        return f"DRY RUN: Would revert {s} v1.4.2 -> v1.4.1. No migration pending. Safe to proceed."

    elif tool_name == "execute_rollback":
        s = tool_input["service"]
        approver = tool_input.get("approved_by", "unknown")
        return f"ROLLBACK EXECUTED: {s} reverted to v1.4.1. Approved by {approver}. ETA 45s."

    return f"Unknown tool: {tool_name}"


def request_human_approval(action: str) -> tuple[bool, str]:
    """
    THE approval gate. In production this posts to Slack/PagerDuty and waits
    for a reply; here it's a terminal prompt -- fine for a lab, not for real
    prod traffic.
    """
    print(f"\n{'='*60}")
    print(f"[APPROVAL GATE] Agent requests permission to: {action}")
    print(f"{'='*60}")
    response = input("Approve? (yes/no): ").strip().lower()
    if response == "yes":
        approver = input("Enter your name for the audit log: ").strip()
        return True, approver
    return False, ""


def run_agent(incident: str):
    print(f"\n[Agent] Starting triage for incident: {incident}\n")

    system_prompt = """You are an agentic SRE (Site Reliability Engineer).
Your job is to triage incidents using the available tools and recommend or execute remediations.

Rules you MUST follow:
1. Always run dry_run_rollback BEFORE execute_rollback.
2. Once dry_run_rollback confirms it is safe, CALL the execute_rollback tool
   directly (you do not need approved_by filled in yourself -- omit it or leave
   it blank). Calling this tool is how you REQUEST human approval: the
   orchestration layer will intercept the call, pause, and ask a human to
   confirm before anything executes. Do not just describe the rollback in text
   and stop -- you must actually invoke the tool to trigger the approval gate.
3. Always explain your reasoning before each tool call.
4. If you are not confident (e.g., no matching pattern, migration pending), recommend
   escalation to the human on-call rather than taking action.
5. After resolving an incident (or escalating), summarize what happened in 3-5 bullet points
   suitable for a postmortem draft.
"""

    messages = [
        {
            "role": "user",
            "content": f"Incident alert: {incident}\n\nPlease triage this incident and determine the appropriate remediation.",
        }
    ]

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        for block in response.content:
            if hasattr(block, "text"):
                print(f"[Agent Thought] {block.text}")  # the "Thought" -- logged before any action runs

        if response.stop_reason == "end_turn":
            print("\n[Agent] Triage complete.")
            break
        if response.stop_reason != "tool_use":
            print(f"[Agent] Unexpected stop reason: {response.stop_reason}")
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                print(f"\n[Agent Action] Calling tool: {tool_name}({json.dumps(tool_input)})")

                if tool_name == "execute_rollback":
                    approved, approver = request_human_approval(
                        f"execute_rollback on {tool_input.get('service')}"
                    )
                    if not approved:
                        tool_result = "Rollback DECLINED by operator. Escalate to human on-call for manual intervention."
                    else:
                        tool_input["approved_by"] = approver
                        tool_result = execute_tool(tool_name, tool_input)
                else:
                    tool_result = execute_tool(tool_name, tool_input)

                print(f"[Tool Result] {tool_result}")
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": tool_result})

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    incident_description = (
        "ALERT: payment-svc error rate has been above 5% for the past 4 minutes. "
        "This started approximately 8 minutes after a deployment. "
        "Cart-svc latency is also slightly elevated. "
        "Please investigate and remediate."
    )
    run_agent(incident_description)
