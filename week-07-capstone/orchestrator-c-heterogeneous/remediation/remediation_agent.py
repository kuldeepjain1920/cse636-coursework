# remediation_agent.py
# Capstone Stage 5 (Auto-remediation), built on week-06-assignment/src/react_agent.py's
# design: same ReAct loop, same blast-radius controls (kill switch, rate limit,
# error-budget gate, human approval), but reads a real Stage 4 incident handoff
# instead of a hardcoded SERVICE_STATE dict, and adds an ITSM ticket stub +
# a Stage 5 handoff output -- the two pieces the capstone needs beyond Week 6.

import os
import sys
import json
import time
import math
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()

RATE_LIMIT_SECONDS = 600  # one automated scale action per service per 10 minutes
_last_scale_action: dict[str, float] = {}

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
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
]


def load_incident(path: str) -> dict:
    """Reads the Stage 4 handoff file -- this is the new bit vs Week 6, which
    had this data hardcoded in SERVICE_STATE."""
    with open(path) as f:
        return json.load(f)


def autonomy_enabled() -> bool:
    return os.environ.get("AUTONOMY_KILL_SWITCH", "on") != "off"


def rate_limit_ok(service: str) -> bool:
    last = _last_scale_action.get(service, 0)
    return time.time() - last >= RATE_LIMIT_SECONDS


def compute_target_replicas(state: dict) -> int:
    return math.ceil(state["current_replicas"] * state["cpu_utilization_pct"] / state["target_cpu_pct"])


def execute_tool(tool_name: str, tool_input: dict, state: dict) -> str:
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
    elif tool_name == "dry_run_scale":
        target = min(compute_target_replicas(state), state.get("max_replicas", 0))
        return (
            f"DRY RUN: Would scale {tool_input['service']} from {state.get('current_replicas')} "
            f"-> {target} replicas (target CPU {state.get('target_cpu_pct')}%)."
        )
    elif tool_name == "execute_scale":
        approver = tool_input.get("approved_by", "unknown")
        target = min(compute_target_replicas(state), state.get("max_replicas", 0))
        _last_scale_action[tool_input["service"]] = time.time()
        state["current_replicas"] = target
        return f"SCALE EXECUTED: {tool_input['service']} scaled to {target} replicas. Approved by {approver}."
    return f"Unknown tool: {tool_name}"


def request_human_approval(action_description: str) -> tuple[bool, str]:
    """THE approval gate -- a terminal prompt here, same as Week 6.
    Real production would post to Slack/PagerDuty and wait for a reply."""
    print(f"\n[APPROVAL REQUIRED] {action_description}")
    resp = input("Approve? [y/N]: ").strip().lower()
    if resp == "y":
        approver = input("Approver name: ").strip() or "unknown"
        return True, approver
    return False, ""


def create_itsm_ticket(incident: dict, outcome: str) -> dict:
    """ITSM ticket stub -- new for the capstone. A real integration would call
    PagerDuty/ServiceNow's API; this writes a structured local record instead,
    which is enough to demonstrate the pattern and gives Stage 4 something
    concrete to loop back and observe."""
    ticket = {
        "ticket_id": f"TICKET-{uuid.uuid4().hex[:8]}",
        "incident_id": incident["incident_id"],
        "service": incident["service"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
        "rca_summary": incident.get("rca_summary", {}),
    }
    os.makedirs("itsm_tickets", exist_ok=True)
    path = f"itsm_tickets/{ticket['ticket_id']}.json"
    with open(path, "w") as f:
        json.dump(ticket, f, indent=2)
    print(f"[ITSM] Ticket created: {path}")
    return ticket


def write_stage5_handoff(incident: dict, outcome: str, ticket: dict, summary: str):
    """Writes handoffs/stage5-output.json -- closes the loop back to Stage 4
    per the agreed handoff design."""
    out = {
        "incident_id": incident["incident_id"],
        "outcome": outcome,
        "ticket_id": ticket["ticket_id"],
        "postmortem_summary": summary,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs("../handoffs", exist_ok=True)
    with open("../handoffs/stage5-output.json", "w") as f:
        json.dump(out, f, indent=2)
    print("[HANDOFF] Wrote ../handoffs/stage5-output.json")


def run_remediation(incident_path: str):
    incident = load_incident(incident_path)
    state = dict(incident["peak_metrics"])
    service = incident["service"]

    system_prompt = f"""You are an agentic SRE handling incident {incident['incident_id']} on {service}.
RCA summary: {incident.get('rca_summary', {}).get('probable_cause', 'unknown')}

Rules:
1. Always run dry_run_scale BEFORE execute_scale.
2. Once dry_run_scale confirms it is safe, CALL execute_scale directly -- calling
   it is how you REQUEST human approval; the orchestration layer intercepts the
   call and pauses for confirmation. Do not just describe the plan in text.
3. If current_replicas is already at or near max_replicas, or error_budget_remaining
   is low, recommend escalation instead of scaling.
4. After resolving or escalating, summarize what happened in 3-5 bullet points."""

    messages = [{
        "role": "user",
        "content": (
            f"ALERT {incident['incident_id']}: {service} CPU utilization at "
            f"{state['cpu_utilization_pct']}%, error rate {state['error_rate']}, "
            f"p99 latency {state['p99_latency_ms']}ms. Triage and remediate."
        ),
    }]

    outcome = "unresolved"
    final_summary = ""

    for _ in range(8):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_summary = "".join(b.text for b in response.content if b.type == "text")
            break

        tool_results = []
        for block in response.content:
            if block.type == "text":
                print(f"[Agent Thought] {block.text}")
            elif block.type == "tool_use":
                tool_name, tool_input = block.name, block.input

                if tool_name == "execute_scale":
                    if not autonomy_enabled():
                        tool_result = "REFUSED: autonomy kill switch is OFF. Escalating to human on-call."
                        outcome = "escalated_kill_switch"
                    elif not rate_limit_ok(service):
                        tool_result = f"REFUSED: {service} was scaled within the last {RATE_LIMIT_SECONDS//60} minutes. Escalating."
                        outcome = "escalated_rate_limit"
                    elif state.get("error_budget_remaining", 1.0) <= 0.10:
                        tool_result = "REFUSED: error budget critically low. Escalating instead of autonomous action."
                        outcome = "escalated_error_budget"
                    else:
                        approved, approver = request_human_approval(f"execute_scale on {service}")
                        if not approved:
                            tool_result = "Scale-out DECLINED by operator. Escalate to human on-call."
                            outcome = "escalated_declined"
                        else:
                            tool_input["approved_by"] = approver
                            tool_result = execute_tool(tool_name, tool_input, state)
                            outcome = "remediated"
                else:
                    tool_result = execute_tool(tool_name, tool_input, state)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_result,
                })
        messages.append({"role": "user", "content": tool_results})

    ticket = create_itsm_ticket(incident, outcome)
    write_stage5_handoff(incident, outcome, ticket, final_summary)
    print(f"\n[RESULT] {incident['incident_id']}: {outcome}")


if __name__ == "__main__":
    incident_file = sys.argv[1] if len(sys.argv) > 1 else "../handoffs/stage4-incident.json"
    run_remediation(incident_file)
