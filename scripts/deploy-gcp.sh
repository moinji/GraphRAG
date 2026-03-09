#!/usr/bin/env bash
# GraphRAG — GCP Cloud Run deploy script
# Prerequisites:
#   1. gcloud CLI installed & authenticated
#   2. GCP project created
#   3. Neo4j AuraDB Free instance created
#   4. Cloud SQL PostgreSQL instance created
#   5. Artifact Registry repository created
#
# Usage: ./scripts/deploy-gcp.sh

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID env var}"
REGION="${GCP_REGION:-asia-northeast3}"
REPO="graphrag"
BACKEND_SERVICE="graphrag-backend"
FRONTEND_SERVICE="graphrag-frontend"

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"
TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")

echo "=== GraphRAG GCP Deploy ==="
echo "Project:  $PROJECT_ID"
echo "Region:   $REGION"
echo "Tag:      $TAG"
echo ""

# ── Step 1: Enable APIs ───────────────────────────────────────────
echo "[1/7] Enabling GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  --project="$PROJECT_ID" --quiet

# ── Step 2: Create Artifact Registry ──────────────────────────────
echo "[2/7] Creating Artifact Registry..."
gcloud artifacts repositories describe "$REPO" \
  --location="$REGION" --project="$PROJECT_ID" 2>/dev/null || \
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --project="$PROJECT_ID"

# ── Step 3: Configure Docker auth ────────────────────────────────
echo "[3/7] Configuring Docker auth..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# ── Step 4: Build & push backend ─────────────────────────────────
echo "[4/7] Building backend..."
docker build -f backend/Dockerfile \
  -t "${REGISTRY}/backend:${TAG}" \
  -t "${REGISTRY}/backend:latest" .
docker push "${REGISTRY}/backend:${TAG}"
docker push "${REGISTRY}/backend:latest"

# ── Step 5: Build & push frontend ────────────────────────────────
echo "[5/7] Building frontend..."
docker build -f frontend/Dockerfile \
  -t "${REGISTRY}/frontend:${TAG}" \
  -t "${REGISTRY}/frontend:latest" .
docker push "${REGISTRY}/frontend:${TAG}"
docker push "${REGISTRY}/frontend:latest"

# ── Step 6: Deploy backend ───────────────────────────────────────
echo "[6/7] Deploying backend to Cloud Run..."
gcloud run deploy "$BACKEND_SERVICE" \
  --image="${REGISTRY}/backend:${TAG}" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=300s \
  --set-env-vars="APP_ENV=production" \
  --project="$PROJECT_ID"

# Get backend URL
BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE" \
  --region="$REGION" --project="$PROJECT_ID" \
  --format='value(status.url)')

echo "Backend URL: $BACKEND_URL"

# ── Step 7: Deploy frontend ──────────────────────────────────────
echo "[7/7] Deploying frontend to Cloud Run..."
gcloud run deploy "$FRONTEND_SERVICE" \
  --image="${REGISTRY}/frontend:${TAG}" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=256Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=2 \
  --set-env-vars="BACKEND_URL=${BACKEND_URL}" \
  --project="$PROJECT_ID"

FRONTEND_URL=$(gcloud run services describe "$FRONTEND_SERVICE" \
  --region="$REGION" --project="$PROJECT_ID" \
  --format='value(status.url)')

# ── Step 8: Update CORS ─────────────────────────────────────────
echo ""
echo "=== Updating backend CORS for frontend URL ==="
gcloud run services update "$BACKEND_SERVICE" \
  --region="$REGION" --project="$PROJECT_ID" \
  --update-env-vars="CORS_ORIGINS=${FRONTEND_URL}"

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo "=== Deploy Complete ==="
echo "Frontend: $FRONTEND_URL"
echo "Backend:  $BACKEND_URL"
echo ""
echo "Next steps:"
echo "  1. Set DB secrets:  gcloud run services update $BACKEND_SERVICE --region=$REGION \\"
echo "       --set-env-vars='NEO4J_URI=neo4j+s://xxx.databases.neo4j.io,NEO4J_PASSWORD=xxx'"
echo "  2. Set LLM keys:   gcloud run services update $BACKEND_SERVICE --region=$REGION \\"
echo "       --set-env-vars='OPENAI_API_KEY=sk-xxx'"
echo "  3. Test health:     curl ${BACKEND_URL}/api/v1/health"
