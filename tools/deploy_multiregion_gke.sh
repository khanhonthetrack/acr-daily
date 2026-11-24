#!/usr/bin/env bash
# Builds and rolls out ACR Daily across the 3 regional GKE clusters with 30-minute zero-drop draining:
#   - acr-eu (europe-west3-a, Primary HTTP/SQLite + EU N^2 Ghost Relay + RPi standby sync)
#   - acr-uk (europe-west2-a, Edge UK HTTP cache/proxy + UK N^2 Ghost Relay)
#   - acr-jp (asia-northeast1-a, Edge JP HTTP cache/proxy + JP N^2 Ghost Relay)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="${GKE_PROJECT:?Set GKE_PROJECT=<gcp-project-id>}"
AR_REGION="${AR_REGION:-europe-west3}"
IMAGE_REPO="${AR_REGION}-docker.pkg.dev/${PROJECT}/acr-daily/acr-daily-server"
TAG="${IMAGE_TAG:-$(date +%s)-$(git rev-parse --short=10 HEAD)}"
NS="acr-daily"

CLUSTERS=(
  "acr-eu:europe-west3-a:deploy/gke/primary-eu.yaml"
  "acr-uk:europe-west2-a:deploy/gke/edge-uk.yaml"
  "acr-jp:asia-northeast1-a:deploy/gke/edge-jp.yaml"
)

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  echo "=== [1/4] Building & pushing ${IMAGE_REPO}:${TAG} ==="
  gcloud auth configure-docker "${AR_REGION}-docker.pkg.dev" --quiet
  docker build -t "${IMAGE_REPO}:${TAG}" -t "${IMAGE_REPO}:latest" .
  docker push "${IMAGE_REPO}:${TAG}"
  docker push "${IMAGE_REPO}:latest"
fi

echo "=== [2/4] Fetching cluster credentials & ensuring least-privilege secrets ==="
for item in "${CLUSTERS[@]}"; do
  IFS=':' read -r cname czone _manifest <<< "$item"
  gcloud container clusters get-credentials "$cname" --zone="$czone" --project="$PROJECT" >/dev/null
done

CTX_EU="gke_${PROJECT}_europe-west3-a_acr-eu"
CTX_UK="gke_${PROJECT}_europe-west2-a_acr-uk"
CTX_JP="gke_${PROJECT}_asia-northeast1-a_acr-jp"

kubectl --context="$CTX_EU" create namespace "$NS" --dry-run=client -o yaml | kubectl --context="$CTX_EU" apply -f - >/dev/null
if ! kubectl --context="$CTX_EU" -n "$NS" get secret acr-daily-secrets >/dev/null 2>&1; then
  ADMIN_KEY="${ACR_DAILY_ADMIN_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"
  LIVE_RELAY_KEY="$(printf 'live-relay|%s' "$ADMIN_KEY" | sha256sum | awk '{print $1}')"
  kubectl --context="$CTX_EU" -n "$NS" create secret generic acr-daily-secrets \
    --from-literal=ADMIN_KEY="$ADMIN_KEY" \
    --from-literal=LIVE_RELAY_KEY="$LIVE_RELAY_KEY" >/dev/null
else
  ADMIN_KEY="$(kubectl --context="$CTX_EU" -n "$NS" get secret acr-daily-secrets -o jsonpath='{.data.ADMIN_KEY}' | base64 -d)"
  LIVE_RELAY_KEY="$(printf 'live-relay|%s' "$ADMIN_KEY" | sha256sum | awk '{print $1}')"
  kubectl --context="$CTX_EU" -n "$NS" patch secret acr-daily-secrets --type merge \
    -p "{\"stringData\":{\"LIVE_RELAY_KEY\":\"${LIVE_RELAY_KEY}\"}}" >/dev/null
fi

# Edge clusters ONLY receive derived LIVE_RELAY_KEY (never ADMIN_KEY!)
for ctx in "$CTX_UK" "$CTX_JP"; do
  kubectl --context="$ctx" create namespace "$NS" --dry-run=client -o yaml | kubectl --context="$ctx" apply -f - >/dev/null
  kubectl --context="$ctx" -n "$NS" create secret generic acr-daily-secrets \
    --from-literal=LIVE_RELAY_KEY="$LIVE_RELAY_KEY" \
    --dry-run=client -o yaml | kubectl --context="$ctx" apply -f - >/dev/null
done

# Fast zero-drop image-only rollout path when topology & mesh ConfigMaps are already live (e.g. from GitHub Actions CI/CD)
if [[ "${IMAGE_ONLY_ROLLOUT:-0}" == "1" ]] && kubectl --context="$CTX_EU" -n "$NS" get deploy acr-relay >/dev/null 2>&1; then
  echo "=== [3/4] Rolling out new image (${IMAGE_REPO}:${TAG}) with 30-min zero-drop draining ==="
  for ctx in "$CTX_EU" "$CTX_UK" "$CTX_JP"; do
    kubectl --context="$ctx" -n "$NS" set image deployment/acr-relay "relay=${IMAGE_REPO}:${TAG}"
  done
  kubectl --context="$CTX_EU" -n "$NS" set image statefulset/acr-daily "server=${IMAGE_REPO}:${TAG}"
  kubectl --context="$CTX_UK" -n "$NS" set image deployment/acr-daily "server=${IMAGE_REPO}:${TAG}"
  kubectl --context="$CTX_JP" -n "$NS" set image deployment/acr-daily "server=${IMAGE_REPO}:${TAG}"

  echo "=== [4/4] Waiting for new Ready pods (draining pods stay alive up to 30m until active drivers finish) ==="
  kubectl --context="$CTX_EU" -n "$NS" rollout status statefulset/acr-daily --timeout=180s
  kubectl --context="$CTX_UK" -n "$NS" rollout status deployment/acr-daily --timeout=180s
  kubectl --context="$CTX_JP" -n "$NS" rollout status deployment/acr-daily --timeout=180s
  for ctx in "$CTX_EU" "$CTX_UK" "$CTX_JP"; do
    kubectl --context="$ctx" -n "$NS" get pods -l 'app in (acr-daily,acr-relay)' -o wide
  done
  exit 0
fi

echo "=== [3/4] Applying Kubernetes manifests across EU, UK, and JP ==="
# Preserve existing wired VPC IPs in ConfigMaps so apply never blanks RELAY_PEERS / PRIMARY_URL mid-flight
save_cm_val() {
  kubectl --context="$1" -n "$NS" get configmap acr-mesh-config -o "jsonpath={.data.$2}" 2>/dev/null || true
}
PREV_EU_PEERS="$(save_cm_val "$CTX_EU" RELAY_PEERS)"
PREV_UK_PEERS="$(save_cm_val "$CTX_UK" RELAY_PEERS)"
PREV_JP_PEERS="$(save_cm_val "$CTX_JP" RELAY_PEERS)"
PREV_UK_PRIM="$(save_cm_val "$CTX_UK" PRIMARY_URL)"
PREV_JP_PRIM="$(save_cm_val "$CTX_JP" PRIMARY_URL)"

for item in "${CLUSTERS[@]}"; do
  IFS=':' read -r cname czone manifest <<< "$item"
  ctx="gke_${PROJECT}_${czone}_${cname}"
  prev_peers="$(save_cm_val "$ctx" RELAY_PEERS)"
  prev_prim="$(save_cm_val "$ctx" PRIMARY_URL)"
  sed -e "s|europe-west3-docker.pkg.dev/[^/]*/acr-daily/acr-daily-server:[^[:space:]]*|${IMAGE_REPO}:${TAG}|g" \
      -e "s|RELAY_PEERS: \"\"|RELAY_PEERS: \"${prev_peers}\"|g" \
      -e "s|PRIMARY_URL: \"http://127.0.0.1:8080\"|PRIMARY_URL: \"${prev_prim:-http://127.0.0.1:8080}\"|g" \
      "$manifest" \
    | kubectl --context="$ctx" apply -f -
  # Remove any obsolete subdomain ManagedCertificates if present
  kubectl --context="$ctx" -n "$NS" delete managedcertificate acr-eu-sub-cert acr-uk-sub-cert acr-jp-sub-cert --ignore-not-found >/dev/null 2>&1 || true
done

wait_svc_ip() {
  local ctx="$1"
  local svc="$2"
  for _i in $(seq 1 45); do
    ip="$(kubectl --context="$ctx" -n "$NS" get svc "$svc" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
    if [[ -n "$ip" ]]; then
      echo "$ip"
      return 0
    fi
    sleep 4
  done
  echo "Timed out waiting for LoadBalancer IP of $svc on $ctx" >&2
  return 1
}

echo "=== [4/4] Wiring cross-region private VPC N^2 Mesh & Primary API ILBs ==="
EU_PRIMARY_ILB="$(wait_svc_ip "$CTX_EU" acr-primary-internal)"
EU_MESH_ILB="$(wait_svc_ip "$CTX_EU" acr-mesh-internal)"
UK_MESH_ILB="$(wait_svc_ip "$CTX_UK" acr-mesh-internal)"
JP_MESH_ILB="$(wait_svc_ip "$CTX_JP" acr-mesh-internal)"
echo "  EU Primary HTTP VPC IP: ${EU_PRIMARY_ILB}"
echo "  EU Relay Mesh VPC IP:   ${EU_MESH_ILB}"
echo "  UK Relay Mesh VPC IP:   ${UK_MESH_ILB}"
echo "  JP Relay Mesh VPC IP:   ${JP_MESH_ILB}"

NEW_EU_PEERS="ws://${UK_MESH_ILB}:8766/live,ws://${JP_MESH_ILB}:8766/live"
NEW_UK_PEERS="ws://${EU_MESH_ILB}:8766/live,ws://${JP_MESH_ILB}:8766/live"
NEW_JP_PEERS="ws://${EU_MESH_ILB}:8766/live,ws://${UK_MESH_ILB}:8766/live"
NEW_PRIM_URL="http://${EU_PRIMARY_ILB}:8080"

kubectl --context="$CTX_EU" -n "$NS" patch configmap acr-mesh-config --type merge \
  -p "{\"data\":{\"RELAY_PEERS\":\"${NEW_EU_PEERS}\"}}"
kubectl --context="$CTX_UK" -n "$NS" patch configmap acr-mesh-config --type merge \
  -p "{\"data\":{\"PRIMARY_URL\":\"${NEW_PRIM_URL}\",\"RELAY_PEERS\":\"${NEW_UK_PEERS}\"}}"
kubectl --context="$CTX_JP" -n "$NS" patch configmap acr-mesh-config --type merge \
  -p "{\"data\":{\"PRIMARY_URL\":\"${NEW_PRIM_URL}\",\"RELAY_PEERS\":\"${NEW_JP_PEERS}\"}}"

if [[ "$PREV_EU_PEERS" != "$NEW_EU_PEERS" ]]; then
  kubectl --context="$CTX_EU" -n "$NS" rollout restart deployment/acr-relay
fi
if [[ "$PREV_UK_PEERS" != "$NEW_UK_PEERS" ]]; then
  kubectl --context="$CTX_UK" -n "$NS" rollout restart deployment/acr-relay
fi
if [[ "$PREV_JP_PEERS" != "$NEW_JP_PEERS" ]]; then
  kubectl --context="$CTX_JP" -n "$NS" rollout restart deployment/acr-relay
fi
if [[ "$PREV_UK_PRIM" != "$NEW_PRIM_URL" ]]; then
  kubectl --context="$CTX_UK" -n "$NS" rollout restart deployment/acr-daily
fi
if [[ "$PREV_JP_PRIM" != "$NEW_PRIM_URL" ]]; then
  kubectl --context="$CTX_JP" -n "$NS" rollout restart deployment/acr-daily
fi

kubectl --context="$CTX_EU" -n "$NS" rollout status statefulset/acr-daily --timeout=180s
kubectl --context="$CTX_UK" -n "$NS" rollout status deployment/acr-daily --timeout=180s
kubectl --context="$CTX_JP" -n "$NS" rollout status deployment/acr-daily --timeout=180s

wait_ext_lb() {
  local ctx="$1"
  for _i in $(seq 1 45); do
    ip="$(kubectl --context="$ctx" -n "$NS" get svc acr-daily-lb -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
    if [[ -n "$ip" ]] && curl -sf --max-time 4 "http://${ip}/healthz" >/dev/null 2>&1; then
      echo "$ip"
      return 0
    fi
    sleep 4
  done
  echo ""
  return 1
}

EU_LB="$(wait_ext_lb "$CTX_EU" || true)"
if [[ -n "$EU_LB" ]]; then
  ROUTE_COUNT="$(curl -sf "http://${EU_LB}/api/routes" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)"
  if [[ "$ROUTE_COUNT" -lt 10 ]]; then
    echo "Seeding full stage pool from https://acrdaily.com into http://${EU_LB}..."
    python3 tools/seed_from_public.py "http://${EU_LB}" "$ADMIN_KEY"
  fi
fi

echo "=== Multi-region zero-drop deployment complete! ==="
for ctx in "$CTX_EU" "$CTX_UK" "$CTX_JP"; do
  echo "--- ${ctx} ---"
  kubectl --context="$ctx" -n "$NS" get pods,svc,ingress,managedcertificate
done
