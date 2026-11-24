#!/usr/bin/env bash
# Seamless 1-command migration of ACR Daily from Cloudflare Workers + D1 (and optional R2) onto GKE (`acr-eu`, `acr-uk`, `acr-jp`).
# Preserves 100% of players, runs, leagues, cups, credits, liveries, AND active browser/app Steam login sessions (`sessions` table).
#
# Usage (run by whoever holds Cloudflare wrangler access + GKE cluster access):
#   export GKE_PROJECT="<gcp-project-id>"
#   export ADMIN_KEY="<existing-Cloudflare-ADMIN_KEY>"
#   # Optional secrets if configured on Cloudflare:
#   export STEAM_API_KEY="..."
#   export DISCORD_WEBHOOK_URL="..."
#   export DISCORD_CUPS_WEBHOOK_URL="..."
#   export DISCORD_BOT_TOKEN="..."
#   export REPORTS_KEY="..."
#   bash tools/migrate_cloudflare_to_gke.sh [optional-path-to-d1-dump.sql]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="${GKE_PROJECT:?Set GKE_PROJECT=<gcp-project-id>}"
ADMIN_KEY_VAL="${ADMIN_KEY:?Set ADMIN_KEY=<existing-Cloudflare-ADMIN_KEY>}"
NS="acr-daily"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

DUMP_SQL="${1:-$WORK_DIR/d1-export.sql}"
if [[ ! -f "$DUMP_SQL" ]]; then
  echo "=== [1/4] Exporting remote Cloudflare D1 database (acr-daily) ==="
  (cd server && npx wrangler d1 export acr-daily --remote --output="$DUMP_SQL")
else
  echo "=== [1/4] Using provided D1 SQL export: $DUMP_SQL ==="
fi

echo "=== [2/4] Building verified SQLite database & marking applied migrations ==="
SQLITE_OUT="$WORK_DIR/acr-daily.sqlite"
DUMP_SQL="$DUMP_SQL" SQLITE_OUT="$SQLITE_OUT" MIG_DIR="$ROOT/server/migrations" python3 - <<'EOF'
import glob, os, re, sqlite3, time

dump_path = os.environ["DUMP_SQL"]
db_path = os.environ["SQLITE_OUT"]
mig_dir = os.environ["MIG_DIR"]

with open(dump_path, "r", encoding="utf-8") as f:
    raw_sql = f.read()

# Strip Cloudflare-internal metadata tables (`_cf_KV`, `d1_migrations`) if present in wrangler export
filtered_lines = []
skip_stmt = False
for line in raw_sql.splitlines():
    if re.match(r'^\s*(CREATE|INSERT\s+INTO|DROP)\s+(TABLE\s+)?(IF\s+EXISTS\s+|IF\s+NOT\s+EXISTS\s+)?["`]?(_cf_KV|d1_migrations)["`]?\b', line, re.I):
        skip_stmt = not line.rstrip().endswith(";")
        continue
    if skip_stmt:
        if line.rstrip().endswith(";"):
            skip_stmt = False
        continue
    filtered_lines.append(line)

conn = sqlite3.connect(db_path)
conn.executescript("\n".join(filtered_lines))
conn.execute("CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY, applied INTEGER NOT NULL)")
now_ms = int(time.time() * 1000)
for mpath in sorted(glob.glob(os.path.join(mig_dir, "*.sql"))):
    conn.execute("INSERT OR IGNORE INTO _migrations (name, applied) VALUES (?, ?)", (os.path.basename(mpath), now_ms))
conn.commit()

ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
if ok != "ok":
    raise SystemExit(f"SQLite integrity_check failed: {ok}")

for tbl in ("players", "sessions", "runs", "routes", "leagues", "cups"):
    try:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  table {tbl:<12}: {cnt} rows")
    except sqlite3.Error:
        pass
conn.close()
EOF

echo "=== [3/4] Updating secrets across acr-eu, acr-uk, and acr-jp ==="
for entry in "acr-eu:europe-west3-a" "acr-uk:europe-west2-a" "acr-jp:asia-northeast1-a"; do
  gcloud container clusters get-credentials "${entry%%:*}" --zone="${entry##*:}" --project="$PROJECT" >/dev/null
done

CTX_EU="gke_${PROJECT}_europe-west3-a_acr-eu"
CTX_UK="gke_${PROJECT}_europe-west2-a_acr-uk"
CTX_JP="gke_${PROJECT}_asia-northeast1-a_acr-jp"

LIVE_RELAY_KEY="$(printf 'live-relay|%s' "$ADMIN_KEY_VAL" | sha256sum | awk '{print $1}')"

SECRET_ARGS=(
  "--from-literal=ADMIN_KEY=${ADMIN_KEY_VAL}"
  "--from-literal=LIVE_RELAY_KEY=${LIVE_RELAY_KEY}"
)
for opt_var in STEAM_API_KEY DISCORD_WEBHOOK_URL DISCORD_CUPS_WEBHOOK_URL DISCORD_BOT_TOKEN REPORTS_KEY; do
  if [[ -n "${!opt_var:-}" ]]; then
    SECRET_ARGS+=("--from-literal=${opt_var}=${!opt_var}")
  fi
done

kubectl --context="$CTX_EU" -n "$NS" create secret generic acr-daily-secrets \
  "${SECRET_ARGS[@]}" --dry-run=client -o yaml | kubectl --context="$CTX_EU" apply -f - >/dev/null

for ctx in "$CTX_UK" "$CTX_JP"; do
  kubectl --context="$ctx" -n "$NS" create secret generic acr-daily-secrets \
    --from-literal=LIVE_RELAY_KEY="$LIVE_RELAY_KEY" \
    --dry-run=client -o yaml | kubectl --context="$ctx" apply -f - >/dev/null
done

echo "=== [4/4] Staging SQLite DB on acr-eu persistent SSD volume & rolling pods ==="
# Stage as .migrating while old pod is still open; new pod atomically swaps & clears old WAL/SHM before opening SQLite!
kubectl --context="$CTX_EU" -n "$NS" exec -i acr-daily-0 -- sh -c 'cat > /data/acr-daily.sqlite.migrating' < "$SQLITE_OUT"
kubectl --context="$CTX_EU" -n "$NS" rollout restart statefulset/acr-daily
for ctx in "$CTX_EU" "$CTX_UK" "$CTX_JP"; do
  kubectl --context="$ctx" -n "$NS" rollout restart deployment/acr-relay
done
kubectl --context="$CTX_EU" -n "$NS" rollout status statefulset/acr-daily --timeout=180s

echo ""
echo "=== Migration complete! ==="
echo "Next step in Cloudflare DNS:"
echo "  1. Remove acrdaily.com custom domain route from the Cloudflare Worker."
echo "  2. Set DNS record:  A  acrdaily.com  ->  34.49.33.253  (DNS Only / grey cloud)."
