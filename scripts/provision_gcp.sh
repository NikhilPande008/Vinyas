#!/usr/bin/env bash
# ==============================================================================
# scripts/provision_gcp.sh
# Idempotent Google Cloud & Gemini API Provisioning Script for Vinyas
# (Startup Buildathon India 2026)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

REGION="${GCP_LOCATION:-asia-south1}"
BILLING_ID="${BILLING_ID:-016D0E-BEBF45-1C4C49}"
DISPLAY_NAME="Vinyas Buildathon India"
SA_NAME="vinyas-backend-sa"
KEYRING_NAME="vinyas-qa-keyring"
CRYPTOKEY_NAME="vinyas-cert-signer"
BQ_DATASET="nadatwin_telemetry"
API_KEY_DISPLAY_NAME="vinyas-gemini-runtime-key"
SECRETS_DIR="${PROJECT_ROOT}/secrets"
SA_KEY_PATH="${SECRETS_DIR}/vinyas-sa-key.json"
ENV_FILE="${PROJECT_ROOT}/.env"

echo "=================================================================="
echo " Vinyas — GCP Cloud Security & Infrastructure Provisioner (2026)"
echo "=================================================================="

# ------------------------------------------------------------------------------
# STEP 1: PRE-FLIGHT AUTH & BILLING VERIFICATION
# ------------------------------------------------------------------------------
echo "[Step 1/5] Verifying active gcloud authentication & billing account..."
ACTIVE_ACCOUNT="$(gcloud auth list --filter="status:ACTIVE" --format="value(account)" 2>/dev/null || true)"
if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
  echo "ERROR: No active gcloud account detected."
  echo "Please run: gcloud auth login && gcloud auth application-default login"
  exit 1
fi
echo "  -> Authenticated as: ${ACTIVE_ACCOUNT}"
echo "  -> Target Billing Account: ${BILLING_ID}"

# ------------------------------------------------------------------------------
# STEP 2: CREATE & CONFIGURE GCP PROJECT + ENABLE APIS
# ------------------------------------------------------------------------------
echo "[Step 2/5] Resolving or creating Google Cloud Project..."
if [[ -z "${PROJECT_ID:-}" ]]; then
  CURRENT_CFG_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
  if [[ "${CURRENT_CFG_PROJECT}" == vinyas-buildathon-* ]]; then
    PROJECT_ID="${CURRENT_CFG_PROJECT}"
    echo "  -> Using active configured Vinyas Buildathon project: ${PROJECT_ID}"
  else
    EXISTING_PROJECT="$(gcloud projects list --filter="projectId:vinyas-buildathon-*" --format="value(projectId)" --limit=1 2>/dev/null || true)"
    if [[ -n "${EXISTING_PROJECT}" ]]; then
      PROJECT_ID="${EXISTING_PROJECT}"
      echo "  -> Found existing Vinyas Buildathon project: ${PROJECT_ID}"
    else
      RAND_SUFFIX="$(printf "%04d" $((RANDOM % 10000)))"
      PROJECT_ID="vinyas-buildathon-${RAND_SUFFIX}"
      echo "  -> Creating new GCP project: ${PROJECT_ID} (${DISPLAY_NAME})..."
      gcloud projects create "${PROJECT_ID}" --name="${DISPLAY_NAME}"
    fi
  fi
else
  if ! gcloud projects describe "${PROJECT_ID}" >/dev/null 2>&1; then
    echo "  -> Creating specified GCP project: ${PROJECT_ID} (${DISPLAY_NAME})..."
    gcloud projects create "${PROJECT_ID}" --name="${DISPLAY_NAME}"
  else
    echo "  -> Using existing GCP project: ${PROJECT_ID}"
  fi
fi

gcloud config set project "${PROJECT_ID}"
gcloud config set run/region "${REGION}"

echo "  -> Linking Billing Account (${BILLING_ID}) to ${PROJECT_ID}..."
gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ID}"

APIS=(
  "generativelanguage.googleapis.com"
  "aiplatform.googleapis.com"
  "apikeys.googleapis.com"
  "run.googleapis.com"
  "cloudbuild.googleapis.com"
  "artifactregistry.googleapis.com"
  "bigquery.googleapis.com"
  "storage.googleapis.com"
  "cloudkms.googleapis.com"
  "secretmanager.googleapis.com"
  "iam.googleapis.com"
  "cloudresourcemanager.googleapis.com"
)

echo "  -> Enabling required Google Cloud & Gemini APIs..."
gcloud services enable "${APIS[@]}" --project="${PROJECT_ID}"

# ------------------------------------------------------------------------------
# STEP 3: PROVISION IAM SERVICE ACCOUNT, CLOUD KMS KEY & DATA RESOURCES
# ------------------------------------------------------------------------------
echo "[Step 3/5] Provisioning Least-Privilege IAM Service Account, Cloud KMS & Data Vault..."
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  -> Creating Service Account: ${SA_EMAIL}"
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Vinyas Backend Runtime Service Account" \
    --project="${PROJECT_ID}"
  sleep 3
else
  echo "  -> Service Account already exists: ${SA_EMAIL}"
fi

ROLES=(
  "roles/aiplatform.user"
  "roles/bigquery.dataEditor"
  "roles/bigquery.jobUser"
  "roles/storage.objectAdmin"
  "roles/cloudkms.signerVerifier"
)

if [[ ! -f "${SA_KEY_PATH}" ]] || [[ "${FORCE_IAM_BINDING:-0}" == "1" ]]; then
  for ROLE in "${ROLES[@]}"; do
    echo "  -> Binding IAM role ${ROLE} to ${SA_EMAIL}..."
    for ATTEMPT in 1 2 3; do
      if gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="${ROLE}" \
        --condition=None \
        --quiet >/dev/null 2>&1; then
        break
      fi
      echo "     (Rate limit hit on cloudresourcemanager; retrying in $((ATTEMPT * 5))s...)"
      sleep $((ATTEMPT * 5))
    done
  done
else
  echo "  -> IAM roles already bound for ${SA_EMAIL} (set FORCE_IAM_BINDING=1 to re-apply)"
fi

mkdir -p "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"
if [[ ! -f "${SA_KEY_PATH}" ]]; then
  echo "  -> Downloading local development Service Account key to ./secrets/vinyas-sa-key.json..."
  gcloud iam service-accounts keys create "${SA_KEY_PATH}" \
    --iam-account="${SA_EMAIL}" \
    --project="${PROJECT_ID}"
  chmod 600 "${SA_KEY_PATH}"
else
  echo "  -> Local SA key already exists at ./secrets/vinyas-sa-key.json (skipping new key creation)"
fi

# Cloud KMS KeyRing & ECDSA P-256 Asymmetric Signing Key
echo "  -> Provisioning Cloud KMS KeyRing (${KEYRING_NAME}) & ECDSA P-256 Key (${CRYPTOKEY_NAME}) in ${REGION}..."
if ! gcloud kms keyrings describe "${KEYRING_NAME}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud kms keyrings create "${KEYRING_NAME}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}"
else
  echo "  -> KeyRing ${KEYRING_NAME} already exists in ${REGION}"
fi

if ! gcloud kms keys describe "${CRYPTOKEY_NAME}" --keyring="${KEYRING_NAME}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud kms keys create "${CRYPTOKEY_NAME}" \
    --keyring="${KEYRING_NAME}" \
    --location="${REGION}" \
    --purpose="asymmetric-signing" \
    --default-algorithm="ec-sign-p256-sha256" \
    --project="${PROJECT_ID}"
else
  echo "  -> Asymmetric Signing Key ${CRYPTOKEY_NAME} already exists"
fi

KMS_KEY_RESOURCE="projects/${PROJECT_ID}/locations/${REGION}/keyRings/${KEYRING_NAME}/cryptoKeys/${CRYPTOKEY_NAME}/cryptoKeyVersions/1"
echo "  -> Cloud KMS Key Version Resource: ${KMS_KEY_RESOURCE}"

# BigQuery Dataset & Tables
echo "  -> Creating BigQuery dataset ${BQ_DATASET} in ${REGION} & initializing tables..."
bq --location="${REGION}" --project_id="${PROJECT_ID}" mk --dataset --force "${PROJECT_ID}:${BQ_DATASET}" >/dev/null 2>&1 || true
GCP_PROJECT_ID="${PROJECT_ID}" GCP_LOCATION="${REGION}" python3 "${PROJECT_ROOT}/scripts/init_bigquery.py"

# Cloud Storage Immutable QA Vault Bucket
VAULT_BUCKET="gs://${PROJECT_ID}-qa-vault"
echo "  -> Provisioning versioned Cloud Storage QA Vault bucket: ${VAULT_BUCKET} in ${REGION}..."
if ! gsutil ls -b "${VAULT_BUCKET}" >/dev/null 2>&1; then
  gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "${VAULT_BUCKET}"
else
  echo "  -> Bucket ${VAULT_BUCKET} already exists"
fi
gsutil versioning set on "${VAULT_BUCKET}"

# ------------------------------------------------------------------------------
# STEP 4: CREATE & RESTRICT THE GEMINI API KEY PROGRAMMATICALLY
# ------------------------------------------------------------------------------
echo "[Step 4/5] Provisioning & restricting Gemini API Key (${API_KEY_DISPLAY_NAME})..."
EXISTING_KEY_NAME="$(gcloud services api-keys list \
  --project="${PROJECT_ID}" \
  --filter="displayName='${API_KEY_DISPLAY_NAME}'" \
  --format="value(name)" \
  --limit=1 2>/dev/null || true)"

if [[ -z "${EXISTING_KEY_NAME}" ]]; then
  echo "  -> Creating restricted API Key for generativelanguage.googleapis.com..."
  CREATE_JSON="$(gcloud services api-keys create \
    --project="${PROJECT_ID}" \
    --display-name="${API_KEY_DISPLAY_NAME}" \
    --api-target=service=generativelanguage.googleapis.com \
    --format="json")"

  EXISTING_KEY_NAME="$(gcloud services api-keys list \
    --project="${PROJECT_ID}" \
    --filter="displayName='${API_KEY_DISPLAY_NAME}'" \
    --format="value(name)" \
    --limit=1)"
else
  echo "  -> Reusing existing restricted API Key resource: ${EXISTING_KEY_NAME}"
fi

GEMINI_KEY_STRING="$(gcloud services api-keys get-key-string "${EXISTING_KEY_NAME}" \
  --project="${PROJECT_ID}" \
  --format="value(keyString)")"

if [[ -z "${GEMINI_KEY_STRING}" ]]; then
  echo "ERROR: Failed to retrieve Gemini API key string."
  exit 1
fi
MASKED_KEY="${GEMINI_KEY_STRING:0:10}...${GEMINI_KEY_STRING: -4}"
echo "  -> Restricted Gemini API Key active: ${MASKED_KEY}"

# ------------------------------------------------------------------------------
# STEP 5: WRITE SECURE .env CONFIGURATION & VERIFY GITIGNORE
# ------------------------------------------------------------------------------
echo "[Step 5/5] Writing production credentials to .env..."
cat > "${ENV_FILE}" <<EOF
# Vinyas Environment Configuration (.env)
# Team Vinyas (Nikhil Pande & Ravi Mule) — Startup Buildathon India 2026
# Auto-provisioned via scripts/provision_gcp.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Google AI & Cloud Credentials
GEMINI_API_KEY="${GEMINI_KEY_STRING}"
GCP_PROJECT_ID="${PROJECT_ID}"
GCP_LOCATION="${REGION}"
GOOGLE_APPLICATION_CREDENTIALS="./secrets/vinyas-sa-key.json"
GCS_QA_VAULT_BUCKET="${VAULT_BUCKET}"

# Demo Circuit Breaker & Hardware Source Selection
DEMO_SAFE_MODE=true
CIRCUIT_BREAKER_TIMEOUT_SEC=3.2
HARDWARE_SOURCE="USB_STEREO_ADC"
AUDIO_DEVICE_INDEX=
CAMERA_DEVICE_INDEX=0
RELAY_SERIAL_PORT=
RELAY_OPERATING_MODE="DAY1_ANDON_ONLY"

# Current Google GenAI Model Identifiers
GEMINI_OMNI_MODEL_ID="gemini-2.5-flash"
EDGE_GEMMA_MODEL_ID="gemma-3n-E4B-it"
VERNACULAR_GEMMA_MODEL_ID="gemma-3-4b-it"
GEMINI_IMAGE_MODEL_ID="gemini-3-pro-image-preview"
GEMINI_LIVE_MODEL_ID="gemini-2.0-flash-live-001"
OLLAMA_BASE_URL="http://localhost:11434"

# Edge Hardware Stereo 48 kHz ADC Calibration Constants
SAMPLE_RATE_HZ=48000
WINDOW_DURATION_MS=250
VIBRATION_G_PER_FS=10.0
CT_AMPS_PER_FS=15.0
COHERENCE_CHATTER_THRESHOLD=0.72
MIN_CT_RIPPLE_AMPS=0.12
MAX_AE_RMS_G=4.5

# Cloud KMS (EC_SIGN_P256_SHA256) & Provenance
HMAC_SIGNING_SECRET="vinyas-ai-v21-chakan-iatf16949-hmac-key-2026"
CLOUD_KMS_KEY_RESOURCE="${KMS_KEY_RESOURCE}"

# Vertex AI Vector Search & BigQuery
VECTOR_SEARCH_INDEX_ENDPOINT="projects/${PROJECT_ID}/locations/${REGION}/indexEndpoints/chakan-alloy-1408d"
VECTOR_SEARCH_DEPLOYED_INDEX_ID="vinyas_ai_alloy_signatures_v21"
BIGQUERY_DATASET="${BQ_DATASET}"
BIGQUERY_TABLE="shift_incidents_ledger"

# Backend API URL for Streamlit Frontend
BACKEND_API_URL="http://localhost:8000"
EOF

chmod 600 "${ENV_FILE}"

echo ""
echo "=================================================================="
echo " PROVISIONING COMPLETE"
echo "=================================================================="
echo " Project ID       : ${PROJECT_ID}"
echo " Region           : ${REGION}"
echo " Billing Account  : ${BILLING_ID}"
echo " Service Account  : ${SA_EMAIL}"
echo " Local SA Key     : ./secrets/vinyas-sa-key.json"
echo " Cloud KMS Key    : ${KMS_KEY_RESOURCE}"
echo " BigQuery Dataset : ${PROJECT_ID}:${BQ_DATASET}"
echo " GCS QA Vault     : ${VAULT_BUCKET} (Versioning: ON)"
echo " Gemini API Key   : ${MASKED_KEY} (Restricted: generativelanguage.googleapis.com)"
echo "=================================================================="
