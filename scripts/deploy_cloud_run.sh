#!/usr/bin/env bash
# ==============================================================================
# scripts/deploy_cloud_run.sh
# Builds & Deploys `opssense-ai` (Single-Container FastAPI + React Control Room)
# to Google Cloud Run in `asia-south1` on port 8080 (`--allow-unauthenticated`).
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env"
  set +a
fi

SERVICE_NAME="${SERVICE_NAME:-opssense-ai}"
REGION="${GCP_LOCATION:-asia-south1}"
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-${GCP_PROJECT_ID:-vinyas-buildathon-6626}}"
GEMINI_API_KEY="${GEMINI_API_KEY:-}"
GCS_BUCKET="${GCS_BUCKET:-${GCS_QA_VAULT_BUCKET:-gs://${PROJECT_ID}-qa-vault}}"
ALLOYDB_DSN="${ALLOYDB_DSN:-}"
SA_EMAIL="${SA_EMAIL:-vinyas-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com}"

echo "=================================================================="
echo " OpsSense AI — Google Cloud Run Single-Container Deployment"
echo "=================================================================="
echo " Service Name   : ${SERVICE_NAME}"
echo " GCP Project ID : ${PROJECT_ID}"
echo " Region         : ${REGION}"
echo " GCS Bucket     : ${GCS_BUCKET}"
echo "=================================================================="

gcloud run deploy "${SERVICE_NAME}" \
  --source="${PROJECT_ROOT}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --service-account="${SA_EMAIL}" \
  --port=8080 \
  --min-instances=1 \
  --max-instances=4 \
  --cpu=2 \
  --memory=2Gi \
  --timeout=300 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GCP_PROJECT_ID=${PROJECT_ID},GCP_LOCATION=${REGION},GEMINI_API_KEY=${GEMINI_API_KEY},GCS_BUCKET=${GCS_BUCKET},ALLOYDB_DSN=${ALLOYDB_DSN},DEMO_FALLBACK_ENABLED=true"

CLOUD_RUN_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)")"

echo ""
echo "=================================================================="
echo " CLOUD RUN DEPLOYMENT COMPLETE"
echo " Live Control Room : ${CLOUD_RUN_URL}"
echo " Health Endpoint   : ${CLOUD_RUN_URL}/health"
echo "=================================================================="

if [[ -f "${PROJECT_ROOT}/.env" ]] && [[ -n "${CLOUD_RUN_URL}" ]]; then
  if grep -q "^CLOUD_RUN_BACKEND_URL=" "${PROJECT_ROOT}/.env"; then
    sed -i.bak "s|^CLOUD_RUN_BACKEND_URL=.*|CLOUD_RUN_BACKEND_URL=\"${CLOUD_RUN_URL}\"|" "${PROJECT_ROOT}/.env"
    rm -f "${PROJECT_ROOT}/.env.bak"
  else
    echo "CLOUD_RUN_BACKEND_URL=\"${CLOUD_RUN_URL}\"" >> "${PROJECT_ROOT}/.env"
  fi
fi
