#!/usr/bin/env bash
# Pauses (scales to 0) or resumes (scales to 1) ACR Daily workloads across acr-eu, acr-uk, and acr-jp while keeping
# all PVCs, static IPs, and secrets intact. Scaling to 0 during a rollback makes any v0.2.2+ multi-region desktop apps
# automatically fail over in 0.25s to https://acrdaily.com (Cloudflare Worker) + Raspberry Pi :10000 relay!
set -euo pipefail

ACTION="${1:-}"
if [[ "$ACTION" != "pause" && "$ACTION" != "resume" ]]; then
  echo "Usage: GKE_PROJECT=<gcp-project-id> bash tools/scale_gke_traffic.sh <pause|resume>" >&2
  exit 1
fi

PROJECT="${GKE_PROJECT:?Set GKE_PROJECT=<gcp-project-id>}"
REPLICAS=1
if [[ "$ACTION" == "pause" ]]; then
  REPLICAS=0
fi

CTX_EU="gke_${PROJECT}_europe-west3-a_acr-eu"
CTX_UK="gke_${PROJECT}_europe-west2-a_acr-uk"
CTX_JP="gke_${PROJECT}_asia-northeast1-a_acr-jp"

gcloud container clusters get-credentials acr-eu --zone=europe-west3-a --project="$PROJECT" >/dev/null
gcloud container clusters get-credentials acr-uk --zone=europe-west2-a --project="$PROJECT" >/dev/null
gcloud container clusters get-credentials acr-jp --zone=asia-northeast1-a --project="$PROJECT" >/dev/null

for ctx in "$CTX_EU" "$CTX_UK" "$CTX_JP"; do
  kubectl --context="$ctx" -n acr-daily scale deployment/acr-rollout-watcher --replicas="$REPLICAS" 2>/dev/null || true
  kubectl --context="$ctx" -n acr-daily scale deployment/acr-relay --replicas="$REPLICAS"
done
kubectl --context="$CTX_EU" -n acr-daily scale statefulset/acr-daily --replicas="$REPLICAS"
kubectl --context="$CTX_UK" -n acr-daily scale deployment/acr-daily --replicas="$REPLICAS"
kubectl --context="$CTX_JP" -n acr-daily scale deployment/acr-daily --replicas="$REPLICAS"

echo "Done: scaled acr-eu, acr-uk, and acr-jp workloads to replicas=${REPLICAS}."
