# incident_tools_server.py
# ---------------------------------------------------------------------------
# MCP server exposing the "operations toolbox" for the triage agent.
# Same shape as Week 2's jenkins_status.py: list_tools() advertises what the
# agent is allowed to call; call_tool() is the only code path that can
# actually touch (simulated) production data. The agent has zero access
# outside these five functions -- that boundary IS the least-privilege
# control, not a suggestion.
# ---------------------------------------------------------------------------
import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("incident-tools")

# --- Simulated data store -----------------------------------------------
# In a real deployment this dict is replaced by calls to Prometheus (metrics),
# a log aggregator (Loki/CloudWatch), and your CD system's deploy history --
# see Week 4's Prometheus/KEDA stack for a real metrics source you already have.
DEPLOYMENTS = {
    "payment-svc": {
        "current_version": "v1.4.2",
        "previous_version": "v1.4.1",
        "deployed_at": "8 minutes ago",
        "migration_pending": False,  # blast-radius check: never auto-rollback across a pending migration
    },
    "cart-svc": {
        "current_version": "v2.1.0",
        "previous_version": "v2.0.9",
        "deployed_at": "2 hours ago",
        "migration_pending": False,
    },
}


@server.list_tools()
async def list_tools():
    # This list IS the agent's entire permission surface.
    # Adding a tool here is the only way to grant new capability -- keep it small.
    return [
        Tool(
            name="get_metrics",
            description="Get current error rate and latency for a service",
            inputSchema={
                "type": "object",
                "properties": {"service": {"type": "string", "description": "Service name"}},
                "required": ["service"],
            },
        ),
        Tool(
            name="get_recent_logs",
            description="Get recent error log lines for a service",
            inputSchema={
                "type": "object",
                "properties": {"service": {"type": "string"}, "tail": {"type": "integer", "default": 20}},
                "required": ["service"],
            },
        ),
        Tool(
            name="get_deployment_history",
            description="Get deployment history for a service",
            inputSchema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
        ),
        Tool(
            name="dry_run_rollback",
            description="Show what a rollback would do, without executing it",
            inputSchema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
        ),
        Tool(
            name="execute_rollback",
            # The description itself nudges the model toward the approval workflow --
            # cheap, effective defense-in-depth alongside the real gate in react_agent.py.
            description="Execute a rollback. REQUIRES prior human approval.",
            inputSchema={
                "type": "object",
                "properties": {
                    "service": {"type": "string"},
                    "approved_by": {"type": "string", "description": "Name of approver"},
                },
                "required": ["service", "approved_by"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    # Single dispatch point -- every tool call the agent makes funnels through here,
    # so this is also the natural place to add audit logging in a real deployment.
    if name == "get_metrics":
        service = arguments["service"]
        if service == "payment-svc":
            data = {"error_rate": 0.08, "p99_latency_ms": 450, "error_budget_remaining": 0.42}
        else:
            data = {"error_rate": 0.003, "p99_latency_ms": 120, "error_budget_remaining": 0.85}
        return [TextContent(type="text", text=json.dumps(data))]

    elif name == "get_recent_logs":
        service = arguments["service"]
        if service == "payment-svc":
            logs = [
                "ERROR NullPointerException in PaymentProcessor.process() line 142",
                "ERROR NullPointerException in PaymentProcessor.process() line 142",
                "WARN Cart total $12,450.00 exceeded expected range",
                "ERROR NullPointerException in PaymentProcessor.process() line 142",
            ]
        else:
            logs = ["INFO Request processed in 115ms", "INFO Healthcheck OK"]
        return [TextContent(type="text", text="\n".join(logs))]

    elif name == "get_deployment_history":
        info = DEPLOYMENTS.get(arguments["service"], {})
        return [TextContent(type="text", text=json.dumps(info))]

    elif name == "dry_run_rollback":
        # Blast-radius control #1: dry-run. The agent must call this before
        # execute_rollback is even meaningful.
        service = arguments["service"]
        info = DEPLOYMENTS.get(service, {})
        result = (
            f"DRY RUN: Would revert {service} from {info.get('current_version')} "
            f"-> {info.get('previous_version')}. Migration pending: {info.get('migration_pending')}"
        )
        return [TextContent(type="text", text=result)]

    elif name == "execute_rollback":
        # This function assumes approval already happened -- react_agent.py is
        # responsible for never calling it without a human-provided approver name.
        service = arguments["service"]
        approver = arguments["approved_by"]
        info = DEPLOYMENTS.get(service, {})
        result = (
            f"ROLLBACK EXECUTED: {service} reverted from {info.get('current_version')} "
            f"-> {info.get('previous_version')}. Approved by: {approver}. ETA: 45 seconds."
        )
        return [TextContent(type="text", text=result)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    # stdio transport -- Claude Code / react_agent.py talks to this process
    # over stdin/stdout, same transport Week 2's jenkins_status.py used.
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
