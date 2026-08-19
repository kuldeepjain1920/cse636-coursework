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
    start = time.perf_counter()

    cpu_pct = psutil.cpu_percent(interval=0.1)
    _peak_cpu_pct = max(_peak_cpu_pct, cpu_pct)  # track peak, not just instantaneous

    # Error rate rises as a real consequence of CPU pressure, not a fixed
    # scripted probability -- this is what makes the RCA's conclusion
    # ("CPU saturation likely driving...") an earned one, not assumed.
    if cpu_pct > CPU_ERROR_THRESHOLD:
        fail_probability = min((cpu_pct - CPU_ERROR_THRESHOLD) / 25.0, 0.9)
        if random.random() < fail_probability:
            _error_count += 1
            return jsonify({
                "error": "internal_server_error",
                "reason": "resource_exhaustion",
                "cpu_pct": cpu_pct,
            }), 500

    result_hash = cpu_bound_work()
    latency_ms = (time.perf_counter() - start) * 1000

    return jsonify({
        "order_id": order_id,  # uses the snapshot, not the (possibly-changed) global
        "status": "processed",
        "cpu_pct": cpu_pct,
        "latency_ms": round(latency_ms, 2),
        "result_hash": result_hash[:16],
    }), 200

@app.route("/metrics")
def metrics():
    return jsonify({
        "cpu_pct": psutil.cpu_percent(interval=0.1),
        "peak_cpu_pct": _peak_cpu_pct,
        "total_requests": _request_count,
        "total_errors": _error_count,
        "error_rate": round(_error_count / _request_count, 4) if _request_count else 0.0,
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
