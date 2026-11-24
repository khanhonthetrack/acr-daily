# Multi-Region GKE Architecture, Automatic GitOps Rollouts & Raspberry Pi Listener Guide

This directory contains the Kubernetes manifests for running **ACR Daily** across 3 dedicated regional GKE clusters (`acr-eu`, `acr-uk`, `acr-jp`), federated in an $N^2$ mesh over Google's private VPC backbone, updated automatically from GitHub, and backed up continuously to the UK Raspberry Pi listener.

## 1. Regional Clusters & Endpoints

| Cluster | Zone / Region | Workloads | Public HTTPS / WSS (`Ingress` + Auto-TLS) | Custom Domain |
|---|---|---|---|---|
| **`acr-eu`** | `europe-west3-a` (Frankfurt) | `StatefulSet/acr-daily` (Primary SQLite WAL + 15 GiB PVC + Cron + RPi Sync) + `Deployment/acr-relay` + `Deployment/acr-rollout-watcher` | `https://acrdaily-eu.34-49-33-253.sslip.io`<br/>`wss://acrdaily-eu.34-49-33-253.sslip.io/live` | `acrdaily.com` -> `34.49.33.253` |
| **`acr-uk`** | `europe-west2-a` (London) | `Deployment/acr-daily` (Edge Cache + Proxy) + `Deployment/acr-relay` + `Deployment/acr-rollout-watcher` | `https://acrdaily-uk.34-117-213-59.sslip.io`<br/>`wss://acrdaily-uk.34-117-213-59.sslip.io/live` | *(internal to desktop client)* |
| **`acr-jp`** | `asia-northeast1-a` (Tokyo) | `Deployment/acr-daily` (Edge Cache + Proxy) + `Deployment/acr-relay` + `Deployment/acr-rollout-watcher` | `https://acrdaily-jp.136-82-36-100.sslip.io`<br/>`wss://acrdaily-jp.136-82-36-100.sslip.io/live` | *(internal to desktop client)* |

Each cluster runs `e2-standard-2` (2 dedicated vCPUs, 8 GiB RAM, 30 GB SSD) with Cluster Autoscaler (`1..3` nodes), comfortably handling **350–500 concurrent 50 Hz drivers per region simultaneously**.

---

## 2. Automatic GitHub -> GKE Zero-Drop Rollouts (`deploy-gke.yml` + `acr-rollout-watcher`)

1. Whenever `server/**`, `live/**`, `routes/**`, or `Dockerfile` changes on `main`, `.github/workflows/deploy-gke.yml` runs all server & mesh tests and publishes `ghcr.io/<owner>/acr-daily-server:main` (using built-in `GITHUB_TOKEN`, zero external cloud secrets needed; make the GHCR package visibility **Public** once in GitHub Package Settings).
2. Inside each GKE cluster, `Deployment/acr-rollout-watcher` (`tools/auto_rollout_watcher.py`) polls `ghcr.io` every 90 seconds for new immutable `sha256:...` digests and automatically patches `acr-relay` and `acr-daily`.
3. `Deployment/acr-relay` rolls out with `maxSurge: 1, maxUnavailable: 0` and `terminationGracePeriodSeconds: 1800` (30 minutes): new drivers join the new pod while draining pods keep active mid-stage drivers connected, bridge 50 Hz ghosts bidirectionally with the new pod, and exit immediately once the last driver finishes their stage.

---

## 3. Raspberry Pi Passive Backup Listener (Zero `kubectl` Needed)

On the Raspberry Pi (no live player traffic touches the Pi; it runs an HMAC-authenticated HTTP listener that receives continuous chunked SQLite + trace backups from `acr-eu`, and serves chunked `HTTP 206 Range` DB bootstrap to `acr-eu` so snapshots >80 MiB never hit Tailscale Funnel's 40-second per-request timeout):

```bash
git fetch https://github.com/jdzikowski/acr-daily.git multi-region-research
git checkout -B multi-region-research FETCH_HEAD
bash live/install_pi_listener.sh
```
This single script auto-detects the Linux user, preserves any existing `~/acr-standby/standby.key` and `~/acr-standby/data/acr-daily.sqlite`, installs/restarts `acr-standby.service` on `127.0.0.1:9876`, keeps any existing service on `:8443/` (e.g. `127.0.0.1:8095`) intact, and exposes `/internal/standby` at `:8443/internal/standby`.
Share that printed 64-hex `STANDBY_KEY` once with the cluster admin (or derive it from the shared `ADMIN_KEY`); `acr-eu` will automatically stream `.sqlite.gz` snapshots (in 8 MiB chunks when >8 MiB) + `.json.gz` traces to the Pi every 60 seconds after durable writes. Also pass `--node-id 4` to the Pi's fallback `live/relay.py` (`wss://immich.tail0d617f.ts.net:10000/live`).

---

## 4. Production Cutover from Cloudflare D1 via the Raspberry Pi Listener

1. **Initial base export (once, ahead of cutover)**: Export Cloudflare D1 into `~/acr-standby/data/acr-daily.sqlite` on the Raspberry Pi:
   ```bash
   python3 tools/export_d1_to_pi.py ~/acr-standby/data
   ```
   `acr-eu` automatically downloads the 80+ MiB base DB in 12 MiB `HTTP 206 Range` chunks (`GET /healthz` shows `"db": {"players": ..., "runs": ...}`).
2. **Fast incremental delta at cutover (`--delta`, ~1 MiB instead of 80+ MiB!)**: Right before switching DNS, sync only the new runs/players/sessions created since the base export (no listener restart needed!):
   ```bash
   python3 tools/export_d1_to_pi.py --delta ~/acr-standby/data
   ```
   Within ~25 seconds, `acr-eu` automatically detects and merges the ~1 MiB delta (`GET /healthz` updates `db.runs`, `db.players`, and `db.appliedDeltaId`), keeping every player signed in (`sessions` table).
3. In Cloudflare DNS, remove the Worker custom domain route and set **`A` `acrdaily.com` -> `34.49.33.253`** (**DNS Only / grey cloud**), then flip `SERVER_URL` in `.github/workflows/release.yml` to `https://acrdaily.com`.
