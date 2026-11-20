#!/usr/bin/env bash
# ==============================================================================
# scripts/deploy_cloud_run.sh
# Builds & deploys `vinyas-ai` (Single-Container FastAPI + React app)
# to Google Cloud Run in `asia-south1` on port 8080 (`--allow-unauthenticated`).
#
# Secret Manager prerequisite (run once with a key file — never echo the key):
#   gcloud secrets create gemini-api-key \
#     --project=vinyas-buildathon-6626 \
#     --replication-policy=automatic
#   gcloud secrets versions add gemini-api-key \
#     --project=vinyas-buildathon-6626 \
#     --data-file=/path/to/gemini_api_key.txt
#   gcloud secrets add-iam-policy-binding gemini-api-key \
#     --project=vinyas-buildathon-6626 \
#     --member="serviceAccount:vinyas-backend-sa@vinyas-buildathon-6626.iam.gserviceaccount.com" \
#     --role="roles/secretmanager.secretAccessor"
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

SERVICE_NAME="${SERVICE_NAME:-vinyas-ai}"
REGION="${GCP_LOCATION:-asia-south1}"
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-${GCP_PROJECT_ID:-vinyas-buildathon-6626}}"
SA_EMAIL="${SA_EMAIL:-vinyas-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com}"
SECRET_NAME="${GEMINI_SECRET_NAME:-gemini-api-key}"

echo "=================================================================="
echo " Vinyas — Google Cloud Run Single-Container Deployment"
echo "=================================================================="
echo " Service Name   : ${SERVICE_NAME}"
echo " GCP Project ID : ${PROJECT_ID}"
echo " Region         : ${REGION}"
echo " Service Acct   : ${SA_EMAIL}"
echo " Gemini Secret  : ${SECRET_NAME}:latest (Secret Manager)"
echo "=================================================================="

# Ensure the runtime service account can read the Gemini API key secret.
gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet >/dev/null

gcloud run deploy "${SERVICE_NAME}" \
  --source="${PROJECT_ROOT}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --platform=managed \
  --ingress=all \
  --allow-unauthenticated \
  --service-account="${SA_EMAIL}" \
  --port=8080 \
  --min-instances=1 \
  --max-instances=4 \
  --concurrency=20 \
  --cpu=2 \
  --memory=2Gi \
  --timeout=120 \
  --set-secrets="GEMINI_API_KEY=${SECRET_NAME}:latest" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GCP_PROJECT_ID=${PROJECT_ID},GCP_LOCATION=${REGION}"

gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --quiet >/dev/null 2>&1 || true

CLOUD_RUN_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)")"

echo ""
echo "=================================================================="
echo " CLOUD RUN DEPLOYMENT COMPLETE"
echo " Live URL        : ${CLOUD_RUN_URL}"
echo " Health Endpoint : ${CLOUD_RUN_URL}/health"
echo "=================================================================="
