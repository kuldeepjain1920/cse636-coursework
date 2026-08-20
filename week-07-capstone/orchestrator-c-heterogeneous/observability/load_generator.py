# load_generator.py
# Drives order-svc through a calm -> spike -> recovery traffic pattern,
# matching the INC-002 narrative (Week 5/6): a real service under real
# load, generating real CPU saturation and correlated errors -- not
# scripted metric values.

import time
import requests
import concurrent.futures

BASE_URL = "http://localhost:8080"

BASELINE_REQUESTS = 10
BASELINE_INTERVAL_SEC = 1.0   # spaced out -- light, steady traffic

SPIKE_REQUESTS = 40
SPIKE_CONCURRENCY = 20        # fired mostly at once -- the incident

RECOVERY_REQUESTS = 10
RECOVERY_INTERVAL_SEC = 1.0


def send_order():
    try:
        resp = requests.post(f"{BASE_URL}/order", timeout=10)
        return resp.status_code, resp.json()
    except requests.RequestException as e:
        return None, {"error": str(e)}


def baseline_phase():
    print(f"\n=== BASELINE: {BASELINE_REQUESTS} requests, {BASELINE_INTERVAL_SEC}s apart ===")
    for i in range(BASELINE_REQUESTS):
        status, body = send_order()
        print(f"  [baseline {i+1}/{BASELINE_REQUESTS}] status={status} cpu_pct={body.get('cpu_pct')}")
        time.sleep(BASELINE_INTERVAL_SEC)


def spike_phase():
    print(f"\n=== SPIKE: {SPIKE_REQUESTS} requests, concurrency={SPIKE_CONCURRENCY} ===")
    errors = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=SPIKE_CONCURRENCY) as executor:
        futures = [executor.submit(send_order) for _ in range(SPIKE_REQUESTS)]
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            status, body = future.result()
            if status == 500:
                errors += 1
            print(f"  [spike {i+1}/{SPIKE_REQUESTS}] status={status} cpu_pct={body.get('cpu_pct')}")
    print(f"  Spike phase errors: {errors}/{SPIKE_REQUESTS}")


def recovery_phase():
    print(f"\n=== RECOVERY: {RECOVERY_REQUESTS} requests, {RECOVERY_INTERVAL_SEC}s apart ===")
    for i in range(RECOVERY_REQUESTS):
        status, body = send_order()
        print(f"  [recovery {i+1}/{RECOVERY_REQUESTS}] status={status} cpu_pct={body.get('cpu_pct')}")
        time.sleep(RECOVERY_INTERVAL_SEC)


if __name__ == "__main__":
    print("Starting load pattern against order-svc: calm -> spike -> recovery")
    baseline_phase()
    spike_phase()
    recovery_phase()

    metrics = requests.get(f"{BASE_URL}/metrics").json()
    print(f"\n=== FINAL METRICS ===\n{metrics}")
