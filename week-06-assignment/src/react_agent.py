# react_agent.py (Assignment version)
# ---------------------------------------------------------------------------
# ReAct agent triaging Week 5's real INC-002 (CPU saturation), remediating
# via scale-out instead of the Lab's rollback. Adds a kill-switch check
# ahead of the approval gate -- the runbook.yaml's escalate_if condition
# "autonomy_kill_switch == off" is enforced here, not just documented.
# ---------------------------------------------------------------------------
import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "get_cpu_metrics",
        "description": "Get current CPU utilization, error rate, and latency for a service",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
    {
        "name": "get_replica_count",
        "description": "Get current and max replica count for a service",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
    {
        "name": "get_recent_logs",
        "description": "Get recent log lines for a service",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}, "tail": {"type": "integer"}},
            "required": ["service"],
        },
    },
    {
        "name": "dry_run_scale",
        "description": "Preview a scale-out action without executing it. Always run this before execute_scale.",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
    {
        "name": "execute_scale",
        "description": (
            "Request execution of a scale-out action. Call this as soon as dry_run_scale "
            "confirms it is safe -- calling it triggers a mandatory human approval pause."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}, "approved_by": {"type": "string"}},
            "required": ["service"],
        },
    },
]

# --- Simulated state, seeded from Week 5's real INC-002 -------------------
SERVICE_STATE = {
    "order-svc": {
        "cpu_utilization_pct": 91.56,
        "error_rate": 0.149,
        "p99_latency_ms": 3661.8,
        "error_budget_remaining": 0.34,
        "current_replicas": 4,
        "max_replicas": 10,
        "target_cpu_pct": 60,
    }
}

# --- Blast-radius control: rate limiting -----------------------------------
import time
_last_scale_action: dict[str, float] = {}
RATE_LIMIT_SECONDS = 600  # one automated scale action per service per 10 minutes


def rate_limit_ok(service: str) -> bool:
    last = _last_scale_action.get(service, 0)
    if time.time() - last < RATE_LIMIT_SECONDS:
        return False
    return True


# --- Blast-radius control: kill switch --------------------------------------
def autonomy_enabled() -> bool:
    return os.environ.get("AUTONOMY_KILL_SWITCH", "on") != "off"


def _compute_target_replicas(state: dict) -> int:
    import math
    return math.ceil(state["current_replicas"] * state["cpu_utilization_pct"] / state["target_cpu_pct"])


def execute_tool(tool_name: str, tool_input: dict) -> str:
    service = tool_input.get("service")
    state = SERVICE_STATE.get(service, {})

    if tool_name == "get_cpu_metrics":
        return json.dumps({
            "cpu_utilization_pct": state.get("cpu_utilization_pct"),
            "error_rate": state.get("error_rate"),
            "p99_latency_ms": state.get("p99_latency_ms"),
            "error_budget_remaining": state.get("error_budget_remaining"),
        })

    elif tool_name == "get_replica_count":
        return json.dumps({
            "current_replicas": state.get("current_replicas"),
            "max_replicas": state.get("max_replicas"),
        })

    elif tool_name == "get_recent_logs":
        return (
            "WARN Request queue depth exceeding 500, dispatch latency rising\n"
            "WARN Thread pool utilization at 98%\n"
            "INFO GC pause 340ms (elevated, not critical)"
        )

    elif tool_name == "dry_run_scale":
        target = min(_compute_target_replicas(state), state.get("max_replicas", 0))
        return (
            f"DRY RUN: Would scale {service} from {state.get('current_replicas')} "
            f"-> {target} replicas (target CPU {state.get('target_cpu_pct')}%)."
        )

    elif tool_name == "execute_scale":
        approver = tool_input.get("approved_by", "unknown")
        target = min(_compute_target_replicas(state), state.get("max_replicas", 0))
        _last_scale_action[service] = time.time()
        state["current_replicas"] = target
        return f"SCALE EXECUTED: {service} scaled to {target} replicas. Approved by {approver}."

    return f"Unknown tool: {tool_name}"


def request_human_approval(action: str) -> tuple[bool, str]:
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

    system_prompt = """You are an agentic SRE (Site Reliability Engineer) handling a CPU-saturation
incident (order-svc, sourced from an upstream anomaly-detection pipeline).

Rules you MUST follow:
1. Always run dry_run_scale BEFORE execute_scale.
2. Once dry_run_scale confirms it is safe, CALL the execute_scale tool directly --
   calling it is how you REQUEST human approval; the orchestration layer intercepts
   the call and pauses for confirmation. Do not just describe the plan in text.
3. Always explain your reasoning before each tool call.
4. If current_replicas is already at or near max_replicas, or error_budget_remaining
   is low, recommend escalation instead of scaling.
5. After resolving or escalating, summarize what happened in 3-5 bullet points
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
                print(f"[Agent Thought] {block.text}")

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

                if tool_name == "execute_scale":
                    service = tool_input.get("service")

                    # --- Kill switch: checked BEFORE the approval gate, per architecture.md ---
                    if not autonomy_enabled():
                        tool_result = "REFUSED: autonomy kill switch is OFF. Escalating to human on-call."
                    # --- Rate limit ---
                    elif not rate_limit_ok(service):
                        tool_result = f"REFUSED: {service} was scaled within the last {RATE_LIMIT_SECONDS//60} minutes. Escalating."
                    # --- Error-budget gate ---
                    elif SERVICE_STATE.get(service, {}).get("error_budget_remaining", 1.0) <= 0.10:
                        tool_result = "REFUSED: error budget critically low. Escalating instead of autonomous action."
                    else:
                        approved, approver = request_human_approval(f"execute_scale on {service}")
                        if not approved:
                            tool_result = "Scale-out DECLINED by operator. Escalate to human on-call for manual intervention."
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
    # INC-002, as produced by Week 5's alert_grouper.py + rca_agent.py
    incident_description = (
        "ALERT INC-002: order-svc CPU utilization has been above 85% for the past 15 minutes "
        "(peak 91.56%). Error rate elevated to 0.149, p99 latency at 3661.8ms. "
        "Root cause (per upstream RCA pipeline): CPU saturation, not a deployment regression. "
        "Please investigate and remediate."
    )
    run_agent(incident_description)
