# Stage 4 Production-Shaping — Monitoring Stack (Prometheus + Grafana)

This folder captures the Helm configuration and Grafana dashboard used in
Stage 4's production-shaping Phases 3-5. These were originally set up
imperatively (`helm install`/`helm upgrade --set ...` and clicking through
Grafana's UI) — these files exist so the setup is reproducible from a
fresh clone, per Option C's design goal, rather than living only as
Kubernetes cluster state and this project's own history.

## Reinstalling from scratch

```bash
# 1. Add Helm repos (skip if already added)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# 2. Create the namespace
kubectl create namespace monitoring

# 3. Install Prometheus with the production-shaping scrape config (D24)
helm install prometheus prometheus-community/prometheus \
  --namespace monitoring \
  -f prometheus-values.yaml

# 4. Install Grafana (admin password auto-generated, not hardcoded)
helm install grafana grafana/grafana \
  --namespace monitoring \
  -f grafana-values.yaml

# 5. Retrieve Grafana's auto-generated admin password
kubectl get secret --namespace monitoring grafana \
  -o jsonpath="{.data.admin-password}" | base64 --decode; echo
```

## Adding the Prometheus datasource

Grafana's Helm chart doesn't provision datasources automatically in this
setup. After logging in (username `admin`, password from step 5 above):

1. Connections → Data sources → Add data source → Prometheus
2. URL: `http://prometheus-server.monitoring.svc.cluster.local`
3. Name: `order-svc-prometheus`
4. Save & Test

## Re-importing the dashboard

`dashboard-order-svc-incident.json` is the exported "order-svc Incident
Dashboard" (Dashboards → Import → paste/upload this file).

**Known caveat:** the JSON has a hardcoded datasource UID
(`efvv1uagmf5kwd`) specific to the original Grafana install. A fresh
datasource created via the steps above will get a *different* UID, so
Grafana's import screen will likely need the datasource re-mapped by
name during import (it usually offers a dropdown for this) rather than
working automatically out of the box.

## Why scrape_interval=5s (D24)

Prometheus's default 60s scrape interval was too coarse to catch
`order_svc_cpu_percent` (a Gauge, sampled only at scrape time) during
brief load-generator spikes — the spike could complete entirely between
two scrape ticks. Reduced to 5s/4s timeout to make a catch ~12x more
likely. Full debugging narrative in `../../docs/decisions.md` D24.

## Access pattern (local dev only)

Both services are reached via `kubectl port-forward` for local
development — this is explicitly not production-realistic (see
`decisions.md` D22 for the same caveat as it applies to
`anomaly_detector.py`).

```bash
kubectl port-forward -n monitoring svc/prometheus-server 9090:80
kubectl port-forward -n monitoring svc/grafana 3000:80
```
