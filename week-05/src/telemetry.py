"""
telemetry.py
------------
Central OpenTelemetry setup for the assignment. Every tool call and LLM
call in rca_agent.py goes through this file so all spans share one
TracerProvider and one exporter, and rca_agent.py stays free of OTel
boilerplate.
"""

import json
import os
import time
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor


def init_tracing(service_name: str = "week5-rca-agent", export_path: str = None):
    """
    Wire up a TracerProvider once per process. If export_path is given,
    spans get written there instead of just printed to the terminal —
    that's what produces output/spans_sample.json.
    """
    provider = TracerProvider()

    if export_path:
        # Make sure output/ exists before trying to open a file in it —
        # this was the exact bug caught earlier when building this pattern.
        os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)

    out_stream = open(export_path, "a") if export_path else None
    exporter = ConsoleSpanExporter(out=out_stream) if out_stream else ConsoleSpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


@contextmanager
def traced_llm_call(tracer, *, model: str, system: str = "anthropic", input_text: str = ""):
    """
    Wraps one LLM call in a gen_ai.chat span — same pattern as Lab Part B,
    just packaged so rca_agent.py doesn't repeat this boilerplate for
    every call it makes.
    """
    span_ctx = {"input_tokens": 0, "output_tokens": 0}
    start = time.perf_counter()

    with tracer.start_as_current_span("gen_ai.chat") as span:
        span.set_attribute("gen_ai.system", system)
        span.set_attribute("gen_ai.request.model", model)

        yield span_ctx  # caller fills in span_ctx["input_tokens"] / ["output_tokens"]

        latency_ms = (time.perf_counter() - start) * 1000
        span.set_attribute("gen_ai.usage.input_tokens", span_ctx["input_tokens"])
        span.set_attribute("gen_ai.usage.output_tokens", span_ctx["output_tokens"])
        span.set_attribute("gen_ai.response.latency_ms", round(latency_ms, 2))


@contextmanager
def traced_tool_call(tracer, *, tool_name: str, args: dict = None):
    """
    Wraps one tool call (get_metrics_window, get_logs_window) in its own
    span, separate from the LLM span — this is what lets you see "the
    agent spent 2ms on the metrics tool and 1.2s on the LLM" instead of
    one opaque blob of time.
    """
    with tracer.start_as_current_span(f"tool.{tool_name}") as span:
        span.set_attribute("gen_ai.tool.name", tool_name)
        if args:
            span.set_attribute("gen_ai.tool.args", json.dumps(args)[:500])
        start = time.perf_counter()

        yield span

        span.set_attribute("gen_ai.tool.latency_ms", round((time.perf_counter() - start) * 1000, 2))
