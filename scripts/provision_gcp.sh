#!/usr/bin/env bash
# ==============================================================================
# scripts/provision_gcp.sh
# Minimal idempotent GCP provisioning for Vinyas on Cloud Run (asia-south1).
# Enables only the APIs actually used by the deployed demo and configures the
# runtime service account + Secret Manager access.
# ==============================================================================
set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-${GCP_PROJECT_ID:-vinyas-buildathon-6626}}"
REGION="${GCP_LOCATION:-asia-south1}"
SA_NAME="${SA_NAME:-vinyas-backend-sa}"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET_NAME="${GEMINI_SECRET_NAME:-gemini-api-key}"

echo "=================================================================="
echo " Vinyas — Minimal GCP Provisioning"
echo " Project : ${PROJECT_ID}"
echo " Region  : ${REGION}"
echo " SA      : ${SA_EMAIL}"
echo "=================================================================="

gcloud config set project "${PROJECT_ID}"
gcloud config set run/region "${REGION}"

echo "[1/3] Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  generativelanguage.googleapis.com \
  --project="${PROJECT_ID}"

echo "[2/3] Ensuring Cloud Run runtime service account exists..."
if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Vinyas Cloud Run Runtime SA" \
    --project="${PROJECT_ID}"
fi

echo "[3/3] Ensuring Secret Manager secret '${SECRET_NAME}' exists..."
if ! gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud secrets create "${SECRET_NAME}" \
    --replication-policy="automatic" \
    --project="${PROJECT_ID}"
  echo "  -> Created empty secret '${SECRET_NAME}'."
  echo "  -> Add your rotated Gemini API key from a file (never echo the key):"
  echo "     gcloud secrets versions add ${SECRET_NAME} --project=${PROJECT_ID} --data-file=/path/to/key.txt"
fi

gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet >/dev/null

echo "Provisioning complete. Next: bash scripts/deploy_cloud_run.sh"
