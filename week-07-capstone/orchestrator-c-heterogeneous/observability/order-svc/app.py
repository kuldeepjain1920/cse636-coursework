# app.py
# order-svc -- Capstone Stage 4's "deployed service" being observed.
# /order does genuine CPU-bound work (not sleep()), so CPU saturation under
# load is real, measurable via psutil -- not scripted or faked. Once CPU
# crosses a threshold, /order starts probabilistically failing, so the error
# rate rises as a real consequence of load, matching the INC-002 narrative
# (CPU saturation driving latency/error degradation) instead of an
# independently scripted number.

import time
import random
import hashlib
import psutil
from flask import Flask, jsonify
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.resources import Resource
# Phase 2: Prometheus-format metrics, alongside (not replacing) the existing
# custom JSON /metrics -- lets Prometheus scrape real, independently-generated
# telemetry instead of a load-generator self-reporting its own traffic.
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

_process = psutil.Process()
_process.cpu_percent()

# Note: cpu_pct can exceed 100% -- Process.cpu_percent() reports the
# percentage of ONE core's worth of time; concurrent/multi-core work
# (e.g. hashlib releasing the GIL during hashing) can genuinely consume
# more than one core's worth simultaneously. This is expected, not a bug.

# --- OTel setup: service-level spans, distinct from Week 5's gen_ai.*
# agent-level spans. This is real HTTP request telemetry, using standard
# OTel semantic conventions (http.*) rather than the GenAI namespace. ---
resource = Resource.create({"service.name": "order-svc"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("order-svc")

# --- Prometheus metric definitions (module-level: created once, updated on
# every request). These are what Phase 3's Prometheus scrape target will
# pull, and what Phase 4's PromQL queries will read instead of a CSV. ---
CPU_GAUGE = Gauge(
    "order_svc_cpu_percent",
    "Current process CPU percent (per-process; can exceed 100 on multi-core work)",
)
REQUEST_COUNTER = Counter(
    "order_svc_requests_total",
    "Total /order requests processed, labeled by outcome",
    ["status"],  # "200" or "500" -- lets PromQL compute error rate via label filtering
)
REQUEST_DURATION = Histogram(
    "order_svc_request_duration_seconds",
    "Time spent processing /order requests, in seconds",
)

app = Flask(__name__)

CPU_ERROR_THRESHOLD = 75.0  # % -- above this, /order starts failing probabilistically
_request_count = 0
_error_count = 0
_peak_cpu_pct = 0.0


def cpu_bound_work(iterations: int = 200_000) -> str:
    """Genuine CPU work: repeated hashing. Not a sleep() -- this actually
    competes for real CPU cycles, so concurrent requests genuinely drive
    utilization up under load."""
    digest = b"order-payload"
    for _ in range(iterations):
        digest = hashlib.sha256(digest).digest()
    return digest.hex()


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/order", methods=["POST"])
def order():
    global _request_count, _error_count, _peak_cpu_pct
    _request_count += 1
    order_id = _request_count  # snapshot immediately -- fixes the race condition

    with tracer.start_as_current_span("order.process") as span:
        span.set_attribute("http.method", "POST")
        span.set_attribute("http.route", "/order")
        span.set_attribute("order.id", order_id)

        start = time.perf_counter()

        cpu_pct = _process.cpu_percent(interval=0.1)
        _peak_cpu_pct = max(_peak_cpu_pct, cpu_pct)
        span.set_attribute("order.cpu_pct", cpu_pct)
        CPU_GAUGE.set(cpu_pct)  # Prometheus: always reflects the most recent reading

        # Error rate rises as a real consequence of CPU pressure, not a fixed
        # scripted probability -- this is what makes the RCA's conclusion
        # ("CPU saturation likely driving...") an earned one, not assumed.
        if cpu_pct > CPU_ERROR_THRESHOLD:
            fail_probability = min((cpu_pct - CPU_ERROR_THRESHOLD) / 25.0, 0.9)
            if random.random() < fail_probability:
                _error_count += 1
                latency_ms = (time.perf_counter() - start) * 1000
                span.set_attribute("http.status_code", 500)
                span.set_attribute("order.error_reason", "resource_exhaustion")
                span.set_attribute("order.latency_ms", round(latency_ms, 2))
                span.set_status(trace.StatusCode.ERROR, "resource_exhaustion")
                REQUEST_COUNTER.labels(status="500").inc()
                REQUEST_DURATION.observe(latency_ms / 1000.0)
                return jsonify({
                    "error": "internal_server_error",
                    "reason": "resource_exhaustion",
                    "cpu_pct": cpu_pct,
                }), 500

        result_hash = cpu_bound_work()
        latency_ms = (time.perf_counter() - start) * 1000

        span.set_attribute("http.status_code", 200)
        span.set_attribute("order.latency_ms", round(latency_ms, 2))
        span.set_status(trace.StatusCode.OK)
        REQUEST_COUNTER.labels(status="200").inc()
        REQUEST_DURATION.observe(latency_ms / 1000.0)

        return jsonify({
            "order_id": order_id,  # uses the snapshot, not the (possibly-changed) global
            "status": "processed",
            "cpu_pct": cpu_pct,
            "latency_ms": round(latency_ms, 2),
            "result_hash": result_hash[:16],
        }), 200


@app.route("/metrics")
def metrics():
    # unchanged -- kept exactly as-is per the Phase 2 plan; still used for
    # manual curl checks and by Stage 5's remediation_agent.py
    return jsonify({
        "cpu_pct": _process.cpu_percent(interval=0.1),
        "peak_cpu_pct": _peak_cpu_pct,
        "total_requests": _request_count,
        "total_errors": _error_count,
        "error_rate": round(_error_count / _request_count, 4) if _request_count else 0.0,
    }), 200


@app.route("/metrics/prometheus")
def metrics_prometheus():
    # Separate endpoint, Prometheus text-exposition format -- what Phase 3's
    # scrape config will target. Refresh the CPU gauge here too, so it's
    # current even if no /order request has landed recently (a pure scrape
    # with no traffic would otherwise show a stale value).
    CPU_GAUGE.set(_process.cpu_percent(interval=0.1))
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
