#!/bin/bash
# =============================================================================
# Terraform Import Script
# =============================================================================
# Purpose: Import existing GCP resources into Terraform state
# Run this ONCE after terraform init, before terraform plan/apply
# =============================================================================

set -e

PROJECT_ID="vertexdemo-481519"
REGION="us-central1"

echo "=== Terraform Import Script ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# -----------------------------------------------------------------------------
# Step 1: Initialize Terraform
# -----------------------------------------------------------------------------
echo "Step 1: Initializing Terraform..."
terraform init

# -----------------------------------------------------------------------------
# Step 2: Import Service Account
# -----------------------------------------------------------------------------
echo ""
echo "Step 2: Importing existing service account..."
# Format: terraform import google_service_account.NAME projects/PROJECT_ID/serviceAccounts/EMAIL

terraform import google_service_account.vertex_ai_demo \
  "projects/${PROJECT_ID}/serviceAccounts/vertex-ai-demo@${PROJECT_ID}.iam.gserviceaccount.com" \
  || echo "Service account already imported or doesn't exist"

# -----------------------------------------------------------------------------
# Step 3: Import IAM Bindings
# -----------------------------------------------------------------------------
echo ""
echo "Step 3: Importing IAM bindings..."
# Format: terraform import google_project_iam_member.NAME "PROJECT_ID ROLE MEMBER"

terraform import google_project_iam_member.demo_sa_user \
  "${PROJECT_ID} roles/aiplatform.user serviceAccount:vertex-ai-demo@${PROJECT_ID}.iam.gserviceaccount.com" \
  || echo "IAM binding already imported or doesn't exist"

terraform import google_project_iam_member.demo_sa_admin \
  "${PROJECT_ID} roles/aiplatform.admin serviceAccount:vertex-ai-demo@${PROJECT_ID}.iam.gserviceaccount.com" \
  || echo "IAM binding already imported or doesn't exist"

# -----------------------------------------------------------------------------
# Step 4: Import Vertex AI Endpoint
# -----------------------------------------------------------------------------
echo ""
echo "Step 4: Importing Vertex AI endpoint..."
# Format: terraform import google_vertex_ai_endpoint.NAME projects/PROJECT/locations/REGION/endpoints/ENDPOINT_ID

ENDPOINT_ID="mg-endpoint-d389c6c2-0220-4648-8365-f45187716345"

terraform import google_vertex_ai_endpoint.llm_demo \
  "projects/${PROJECT_ID}/locations/${REGION}/endpoints/${ENDPOINT_ID}" \
  || echo "Endpoint already imported or doesn't exist"

# -----------------------------------------------------------------------------
# Step 5: Verify Import
# -----------------------------------------------------------------------------
echo ""
echo "Step 5: Verifying import..."
terraform state list

echo ""
echo "=== Import Complete ==="
echo ""
echo "Next steps:"
echo "  1. Run 'terraform plan' to see if state matches reality"
echo "  2. Fix any diffs in the .tf files"
echo "  3. Run 'terraform apply' to sync"
