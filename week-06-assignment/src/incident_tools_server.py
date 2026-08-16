# incident_tools_server.py (Assignment version)
# ---------------------------------------------------------------------------
# MCP server for the order-svc CPU-saturation scenario (Week 5's INC-002).
# Same least-privilege shape as the Lab's server: list_tools() is the
# agent's entire permission surface, call_tool() is the only path that
# touches (simulated) production data.
# ---------------------------------------------------------------------------
import asyncio
import json
import time
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("incident-tools-scaling")

# --- Simulated state, seeded from Week 5's real INC-002 output -----------
# peak_cpu/error_rate/latency below are the actual values alert_grouper.py
# produced for INC-002, not fabricated numbers.
SERVICE_STATE = {
    "order-svc": {
        "cpu_utilization_pct": 91.56,     # INC-002 peak
        "error_rate": 0.149,               # INC-002 peak
        "p99_latency_ms": 3661.8,          # INC-002 peak
        "error_budget_remaining": 0.34,
        "current_replicas": 4,
        "max_replicas": 10,                # matches Week 4's KEDA ScaledObject maxReplicaCount
        "target_cpu_pct": 60,              # matches Week 4's KEDA target
    }
}

# Blast-radius state (in-memory here; a real deployment persists this)
_last_scale_action: dict[str, float] = {}
RATE_LIMIT_SECONDS = 600  # 10-minute cooldown per service


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="get_cpu_metrics",
            description="Get current CPU utilization, error rate, and latency for a service",
            inputSchema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
        ),
        Tool(
            name="get_replica_count",
            description="Get current and max replica count for a service",
            inputSchema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
        ),
        Tool(
            name="get_recent_logs",
            description="Get recent log lines for a service",
            inputSchema={
                "type": "object",
                "properties": {"service": {"type": "string"}, "tail": {"type": "integer", "default": 20}},
                "required": ["service"],
            },
        ),
        Tool(
            name="dry_run_scale",
            description="Preview a scale-out action (computed target replica count) without executing it",
            inputSchema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
        ),
        Tool(
            name="execute_scale",
            description=(
                "Request execution of a scale-out action. Call this as soon as dry_run_scale "
                "confirms it is safe -- calling it triggers a mandatory human approval pause. "
                "You do not need to supply approved_by; the orchestration layer fills it in "
                "after a human confirms."
            ),
            inputSchema={
                "type": "object",
                "properties": {"service": {"type": "string"}, "approved_by": {"type": "string"}},
                "required": ["service"],
            },
        ),
    ]


def _compute_target_replicas(state: dict) -> int:
    """Same formula as Week 6 runbook.yaml's target_replica_calculation."""
    import math
    return math.ceil(state["current_replicas"] * state["cpu_utilization_pct"] / state["target_cpu_pct"])


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    service = arguments.get("service")
    state = SERVICE_STATE.get(service, {})

    if name == "get_cpu_metrics":
        data = {
            "cpu_utilization_pct": state.get("cpu_utilization_pct"),
            "error_rate": state.get("error_rate"),
            "p99_latency_ms": state.get("p99_latency_ms"),
            "error_budget_remaining": state.get("error_budget_remaining"),
        }
        return [TextContent(type="text", text=json.dumps(data))]

    elif name == "get_replica_count":
        data = {
            "current_replicas": state.get("current_replicas"),
            "max_replicas": state.get("max_replicas"),
        }
        return [TextContent(type="text", text=json.dumps(data))]

    elif name == "get_recent_logs":
        # INC-002 was CPU saturation, not an application error -- logs reflect that:
        # slow responses and queueing, not exceptions.
        logs = [
            "WARN Request queue depth exceeding 500, dispatch latency rising",
            "WARN Thread pool utilization at 98%",
            "INFO GC pause 340ms (elevated, not critical)",
        ]
        return [TextContent(type="text", text="\n".join(logs))]

    elif name == "dry_run_scale":
        target = _compute_target_replicas(state)
        target = min(target, state.get("max_replicas", target))
        result = (
            f"DRY RUN: Would scale {service} from {state.get('current_replicas')} "
            f"-> {target} replicas (target CPU {state.get('target_cpu_pct')}%). "
            f"Capped at max_replicas={state.get('max_replicas')}."
        )
        return [TextContent(type="text", text=result)]

    elif name == "execute_scale":
        # --- Blast-radius control: rate limit -------------------------------
        last = _last_scale_action.get(service, 0)
        if time.time() - last < RATE_LIMIT_SECONDS:
            return [TextContent(
                type="text",
                text=f"REFUSED: {service} was scaled less than {RATE_LIMIT_SECONDS//60} minutes ago. Escalating instead of re-scaling."
            )]

        # --- Blast-radius control: error-budget gate -------------------------
        if state.get("error_budget_remaining", 1.0) <= 0.10:
            return [TextContent(
                type="text",
                text=f"REFUSED: error_budget_remaining for {service} is critically low. Escalating to human on-call instead of autonomous action."
            )]

        approver = arguments.get("approved_by", "unknown")
        target = min(_compute_target_replicas(state), state.get("max_replicas"))
        _last_scale_action[service] = time.time()
        state["current_replicas"] = target  # simulate the scale taking effect
        result = f"SCALE EXECUTED: {service} scaled to {target} replicas. Approved by: {approver}."
        return [TextContent(type="text", text=result)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
