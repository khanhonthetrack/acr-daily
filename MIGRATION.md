# Production Cutover Runbook: Cloudflare D1 / Worker -> Multi-Region GKE (`EU / UK / JP`)

This runbook documents every step required to migrate **`acrdaily.com`** and all existing desktop clients (`ACR-Daily.exe`) from Cloudflare D1/Worker onto the 3 regional GKE clusters (`acr-eu`, `acr-uk`, `acr-jp`) with **zero lost runs**, **zero player sign-outs**, and **zero manual copy-pasting of secret keys**.

---

## Current Live State (Already Completed)
- **GKE Clusters (`v0.2.1`)**:
  - **EU Primary (`europe-west3-a`)**: `https://acrdaily-eu.34-49-33-253.sslip.io` ([live `/healthz`](https://acrdaily-eu.34-49-33-253.sslip.io/healthz), static Anycast IP `34.49.33.253`)
  - **UK Edge (`europe-west2-a`)**: `https://acrdaily-uk.34-117-213-59.sslip.io`
  - **JP Edge (`asia-northeast1-a`)**: `https://acrdaily-jp.136-82-36-100.sslip.io`
- **Base Database Pre-Loaded**: All **477 players, 2,916 runs (`maxRunId: 2922`), 990 active Steam sessions, 62 stages, 50 leagues, and 2 cups** are already loaded on `acr-eu`, paired with the UK Raspberry Pi passive backup listener (`inSync: true`).

---

## Phase 1 — Pre-Cutover Preparation (Zero Impact on Live Players)

### 1.1 Stage Cloudflare Secrets Encrypted on the Raspberry Pi (Repo / Cloudflare Owner)
Existing `v0.2.1` desktop apps connect to the Pi live ghost relay (`:10000`), which verifies live tickets signed with `sha256("live-relay|" + ADMIN_KEY)`. Importing your existing `ADMIN_KEY` (plus Discord/Steam/Twitch/AI keys) into `acr-eu` ensures live ghosts, Discord posts, and Steam profile lookups keep working seamlessly at cutover.

On the Raspberry Pi:
1. Pull the latest `multi-region-research` branch:
   ```bash
   git fetch https://github.com/jdzikowski/acr-daily.git multi-region-research
   git checkout -B multi-region-research FETCH_HEAD
   ```
2. Create `~/acr-standby/cloudflare.env` (`chmod 600`) containing your current Cloudflare Worker secrets (omit any you don't use):
   ```ini
   ADMIN_KEY=your_existing_cloudflare_admin_key
   STEAM_API_KEY=...
   DISCORD_WEBHOOK_URL=...
   DISCORD_CUPS_WEBHOOK_URL=...
   DISCORD_BOT_TOKEN=...
   DISCORD_PUBLIC_KEY=...
   TWITCH_CLIENT_SECRET=...
   ANTHROPIC_API_KEY=...
   AZURE_SPEECH_KEY=...
   REPORTS_KEY=...
   ```
3. Encrypt & stage the bundle using your existing private `~/acr-standby/standby.key` (`PBKDF2-HMAC-SHA256` + `Encrypt-then-MAC`):
   ```bash
   chmod 600 ~/acr-standby/cloudflare.env
   python3 tools/stage_secrets_on_pi.py ~/acr-standby/cloudflare.env
   ```
4. Ping the GKE admin ("secrets staged"). Once imported into `acr-eu`, clean up the local files on the Pi:
   ```bash
   python3 tools/stage_secrets_on_pi.py --cleanup
   shred -u ~/acr-standby/cloudflare.env
   ```

### 1.2 Verify the Raspberry Pi `:10000` Fallback `relay.py` & `--node-id 4` (Repo / Pi Owner)
> **Why `--node-id 4` failed if tried earlier:**
> If your `:10000` relay systemd service runs an older copy of `relay.py` (for example in `~/acr-live/relay.py` from `main` before this PR), that older file did not yet accept `--node-id` and exited with `unrecognized arguments: --node-id 4`.
>
> **Note:** Because the Pi `:10000` relay acts purely as an automatic last-resort fallback (when all 3 GKE clusters are unreachable) and is **not** connected as an active peer on VPC port `8766`, it already works even **without** `--node-id 4`! However, updating its `relay.py` copy from this branch is recommended so it also gets `v0.2.1` `CODRIVER` crew voice (`'x'`) + non-blocking send queues + `--node-id 4`.

To inspect and verify your `:10000` relay service on the Raspberry Pi:
```bash
# 1. Check which unit & path runs the :10000 relay:
ps -ef | grep '[r]elay.py'
systemctl list-units --type=service | grep -iE 'acr|live|relay'

# 2. Copy the updated live/relay.py from this checkout over the path shown in ExecStart (e.g. ~/acr-live/relay.py):
#    cp live/relay.py ~/acr-live/relay.py
#    Then --node-id 4 is supported (verify with: python3 ~/acr-live/relay.py --help | grep node-id)
```

---

## Phase 2 — Evening Production Cutover (~5 Minutes, Zero Lost Runs)

### Why We Proxy `workers.dev` During Cutover
All currently installed `v0.2.1` `ACR-Daily.exe` binaries on players' PCs were compiled against `https://acr-daily.acr-daily-server.workers.dev` (not `acrdaily.com`). Switching only `acrdaily.com` DNS would leave `v0.2.1` desktop apps writing to old Cloudflare D1!
Deploying `tools/cloudflare-cutover-proxy/` replaces the Worker on `workers.dev` with a transparent forwarder to `acr-eu` (preserving `POST` bodies, `Authorization` headers, and OAuth redirects — unlike HTTP `302`, which strips `POST` and `Authorization` in Python's `urllib`), while simultaneously detaching the Worker's custom domain route from `acrdaily.com`.

### Step-by-Step Sequence

1. **Pre-sync today's delta while live traffic is still running (Repo / Cloudflare Owner)**
   ```bash
   python3 tools/export_d1_to_pi.py --delta ~/acr-standby/data
   ```
   Wait ~25 seconds and check `https://acrdaily-eu.34-49-33-253.sslip.io/healthz` — `db.runs` and `db.appliedDeltaId` will update automatically (no 82 MiB transfer, ~1 MiB in a few seconds).

2. **30-second D1 write freeze + final delta + enable `workers.dev -> GKE` proxy (Repo / Cloudflare Owner)**
   *(Note: if any driver crosses the finish line during these ~30 seconds, `ACR-Daily.exe` saves the run to `pending.json` on `HTTP 503` and automatically re-submits it once step 2c runs!)*
   ```bash
   # 2a. Pause D1 writes for ~30s (also detaches Worker custom_domain route from acrdaily.com):
   npx wrangler deploy --config tools/cloudflare-cutover-proxy/wrangler.toml --var MAINTENANCE:1

   # 2b. Export any run submitted in the last minute & wait ~25s until /healthz shows the new appliedDeltaId:
   python3 tools/export_d1_to_pi.py --delta ~/acr-standby/data
   curl -s https://acrdaily-eu.34-49-33-253.sslip.io/healthz

   # 2c. Open live traffic through workers.dev -> GKE Primary (acr-eu):
   npx wrangler deploy --config tools/cloudflare-cutover-proxy/wrangler.toml
   ```

3. **Point `acrdaily.com` DNS to GKE in Cloudflare Dashboard (Repo / Cloudflare Owner)**
   - Go to **Cloudflare Dashboard -> `acrdaily.com` -> DNS -> Records**:
     - Add/update record **`A`**, Name: **`@`** (`acrdaily.com`), IPv4 address: **`34.49.33.253`**.
     - **For zero TLS wait time at cutover:** set Proxy status to **Proxied (orange cloud)** initially, and ensure **SSL/TLS -> Overview** is set to **Full** (not *Flexible*). `https://acrdaily.com` serves from GKE immediately in `0 s`.
     - *(Optional later in a quiet window: switch `acrdaily.com` to **DNS Only / grey cloud** so traffic goes directly to Google Anycast `34.49.33.253`; Google Managed Certificate `acr-main-domain-cert` becomes `Active` ~15 minutes after grey-cloud DNS points to `34.49.33.253`).*

4. **Merge PR #98, Enable Automatic GitOps Rollouts & Publish Multi-Region Client Release (Repo Owner)**
   1. Click **Merge pull request** on [PR #98](https://github.com/khanhonthetrack/acr-daily/pull/98).
   2. Once the **`Build & Publish GKE Server Image`** GitHub Action finishes (~1 min) on `main`, open your repo's **Packages -> `acr-daily-server` -> Package settings -> Change visibility -> Public** (one-time step; from then on, `acr-eu`, `acr-uk`, and `acr-jp` automatically roll out every future `main` commit within 90 seconds with 30-minute zero-drop relay draining).
   3. Publish the next client release (e.g. `v0.2.2`) so desktop apps switch from `workers.dev` directly to lowest-RTT regional endpoints **`AUTO (EU / UK / JP)`**.

---

## Phase 3 — Emergency Rollback to Cloudflare Worker + D1 (Zero Data Loss)

If you ever need to revert back to the original single-Worker Cloudflare D1 + Raspberry Pi `:10000` relay setup (even after drivers have already completed runs on GKE):

1. **Remove the manual `A` record in Cloudflare DNS (Repo / Cloudflare Owner)**
   - In **Cloudflare Dashboard -> `acrdaily.com` -> DNS -> Records**, delete the manual **`A` `acrdaily.com -> 34.49.33.253`** record (so `wrangler deploy` can re-attach `routes = [{ pattern = "acrdaily.com", custom_domain = true }]` automatically).

2. **Run the automated rollback script (Repo / Cloudflare Owner)**
   ```bash
   python3 tools/rollback_to_cloudflare.py ~/acr-standby/data
   ```
   What this single command does automatically:
   - Pauses `workers.dev` writes briefly (`MAINTENANCE:1`) and waits until `acr-eu` reports `standby.inSync == true` so `~/acr-standby/data/acr-daily.sqlite` on the Pi contains every run finished on GKE up to the last second.
   - Compares `~/acr-standby/data/acr-daily.sqlite` against remote Cloudflare D1 watermarks and pushes **only** the new runs/blobs + updated state tables back into Cloudflare D1 (no 82 MiB re-upload).
   - Redeploys the full original Cloudflare Worker (`server/wrangler.toml`) onto both `acr-daily.acr-daily-server.workers.dev` and `acrdaily.com`.

3. **Pause GKE endpoints so multi-region clients fail back automatically (GKE Admin)**
   ```bash
   GKE_PROJECT=<gcp-project-id> bash tools/scale_gke_traffic.sh pause
   ```
   Scaling the GKE workloads to `0` makes even newly released multi-region desktop apps automatically fail over in `0.25 s` to `https://acrdaily.com` (Cloudflare Worker) and `wss://immich.tail0d617f.ts.net:10000/live` (Raspberry Pi relay) — **no emergency `.exe` release required** (`resume` brings GKE back to `1` replica anytime).

