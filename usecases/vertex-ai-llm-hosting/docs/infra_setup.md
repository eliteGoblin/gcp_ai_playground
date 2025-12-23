# Infrastructure Setup for Vertex AI LLM Demo

## Overview

This document summarizes the infrastructure setup for deploying an LLM on GCP Vertex AI. Focus: **model hosting and provisioning** with demo-scale resources but production patterns.

---

## 1. What Was Provisioned

### Model Hosting Summary

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MODEL HOSTING ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Model Garden          Model Registry           Endpoint               │
│   ┌──────────┐         ┌──────────────┐        ┌──────────────┐        │
│   │ Gemma 3  │ ──────► │ google-gemma │ ─────► │ gemma-3-1b   │        │
│   │ 1B IT    │  deploy │ 3-gemma-3-1b │  serve │ -demo        │        │
│   │ (Google) │         │ -it-176...   │        │              │        │
│   └──────────┘         └──────────────┘        └──────┬───────┘        │
│                                                       │                 │
│                                                       ▼                 │
│                                              ┌──────────────┐           │
│                                              │  Dedicated   │           │
│                                              │  DNS Endpoint│           │
│                                              │  (HTTPS)     │           │
│                                              └──────────────┘           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Resources Created

| Resource | ID/Name | Details |
|----------|---------|---------|
| **Project** | `vertexdemo-481519` | GCP project |
| **Model** | `google-gemma3-gemma-3-1b-it-1766002321` | Gemma 3 1B instruction-tuned |
| **Endpoint** | `mg-endpoint-d389c6c2-0220-4648-8365-f45187716345` | Prediction serving |
| **Endpoint DNS** | `mg-endpoint-d389c6c2-0220-4648-8365-f45187716345.us-central1-632872760922.prediction.vertexai.goog` | Dedicated endpoint URL |
| **Service Account** | `vertex-ai-demo@vertexdemo-481519.iam.gserviceaccount.com` | Runtime identity |

---

## 2. Model Provisioning (Core Steps)

### Step 1: Enable APIs
```bash
gcloud services enable \
  aiplatform.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com \
  --project=vertexdemo-481519
```

### Step 2: Check Available Models
```bash
# List models in Model Garden
gcloud ai model-garden models list --project=vertexdemo-481519 | grep gemma

# Check machine requirements for specific model
gcloud ai model-garden models list-deployment-config \
  --model="google/gemma3@gemma-3-1b-it" \
  --project=vertexdemo-481519
```

Output:
```
MACHINE_TYPE    ACCELERATOR_TYPE  ACCELERATOR_COUNT
g2-standard-12  NVIDIA_L4         1                  ← Smallest option
a2-ultragpu-1g  NVIDIA_A100_80GB  1
a3-highgpu-1g   NVIDIA_H100_80GB  1
```

### Step 3: Deploy Model to Endpoint
```bash
gcloud ai model-garden models deploy \
  --model="google/gemma3@gemma-3-1b-it" \
  --endpoint-display-name="gemma-3-1b-demo" \
  --region=us-central1 \
  --project=vertexdemo-481519 \
  --machine-type=g2-standard-12 \
  --accelerator-type=NVIDIA_L4 \
  --accelerator-count=1 \
  --accept-eula
```

This command:
1. Pulls model from Model Garden
2. Registers it in Model Registry
3. Creates endpoint
4. Deploys model to endpoint with GPU

### Step 4: Verify Deployment
```bash
# Check model in registry
gcloud ai models list --region=us-central1 --project=vertexdemo-481519

# Check endpoint
gcloud ai endpoints list --region=us-central1 --project=vertexdemo-481519

# Detailed endpoint info
gcloud ai endpoints describe mg-endpoint-d389c6c2-0220-4648-8365-f45187716345 \
  --region=us-central1 --project=vertexdemo-481519
```

### Step 5: Test Prediction
```bash
# Get auth token
ACCESS_TOKEN=$(gcloud auth print-access-token)

# Call endpoint (Gemma uses specific prompt format)
curl -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  "https://mg-endpoint-d389c6c2-0220-4648-8365-f45187716345.us-central1-632872760922.prediction.vertexai.goog/v1/projects/vertexdemo-481519/locations/us-central1/endpoints/mg-endpoint-d389c6c2-0220-4648-8365-f45187716345:rawPredict" \
  -d '{
    "prompt": "<start_of_turn>user\nHello! Who are you?<end_of_turn>\n<start_of_turn>model\n",
    "max_tokens": 50
  }'
```

Response:
```json
{"predictions":["...Output:\nYes, I am Gemma! I'm a large language model created by the Gemma team at Google DeepMind..."]}
```

---

## 3. Compute Infrastructure

### Machine Specs (Demo)

| Component | Value |
|-----------|-------|
| Machine Type | `g2-standard-12` |
| vCPUs | 12 |
| Memory | 48 GB |
| GPU | NVIDIA L4 x 1 |
| GPU Memory | 24 GB |
| Container | `pytorch-vllm-serve` |
| Replicas | 1 (min=1, max=1) |

### Cost

```
Demo Setup:
├── g2-standard-12 + L4 GPU: ~$0.70/hour
├── Running 24/7: ~$500/month
└── Per request: negligible

To stop billing:
gcloud ai endpoints undeploy-model \
  mg-endpoint-d389c6c2-0220-4648-8365-f45187716345 \
  --deployed-model-id=473826839408672768 \
  --region=us-central1
```

---

## 4. Terraform Import (IaC)

After manual setup, imported existing resources into Terraform:

```bash
cd /home/parallels/devel/gcp_ml_playground/terraform

# Initialize
terraform init

# Import service account
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)

terraform import google_service_account.vertex_ai_demo \
  "projects/vertexdemo-481519/serviceAccounts/vertex-ai-demo@vertexdemo-481519.iam.gserviceaccount.com"

# Import endpoint
terraform import google_vertex_ai_endpoint.llm_demo \
  "projects/vertexdemo-481519/locations/us-central1/endpoints/mg-endpoint-d389c6c2-0220-4648-8365-f45187716345"

# Verify state
terraform state list
# google_service_account.vertex_ai_demo
# google_vertex_ai_endpoint.llm_demo

# Plan to see drift
terraform plan
```

Now resources are managed by Terraform - changes go through IaC.

---

## 5. Key Files

| File | Purpose |
|------|---------|
| `terraform/main.tf` | IaC for all resources |
| `terraform/import.sh` | Script to import existing resources |
| `.github/workflows/deploy-model.yml` | CI/CD pipeline |
| `documents/governance/ml_governance.md` | Versioning & compliance |

---

## 6. Quick Reference Commands

```bash
# ===== HEALTH CHECK =====
gcloud ai endpoints list --region=us-central1
gcloud ai models list --region=us-central1

# ===== VIEW ENDPOINT DETAILS =====
gcloud ai endpoints describe mg-endpoint-d389c6c2-0220-4648-8365-f45187716345 \
  --region=us-central1

# ===== TEST PREDICTION =====
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://mg-endpoint-d389c6c2-0220-4648-8365-f45187716345.us-central1-632872760922.prediction.vertexai.goog/v1/projects/vertexdemo-481519/locations/us-central1/endpoints/mg-endpoint-d389c6c2-0220-4648-8365-f45187716345:rawPredict" \
  -d '{"prompt": "<start_of_turn>user\nHello<end_of_turn>\n<start_of_turn>model\n", "max_tokens": 30}'

# ===== STOP BILLING (UNDEPLOY) =====
gcloud ai endpoints undeploy-model \
  mg-endpoint-d389c6c2-0220-4648-8365-f45187716345 \
  --deployed-model-id=473826839408672768 \
  --region=us-central1

# ===== TERRAFORM =====
cd terraform
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)
terraform plan
terraform apply
```

---

## 7. What Happens Under the Hood

When you run `gcloud ai model-garden models deploy`:

```
1. MODEL GARDEN
   └── Google hosts pre-trained models (Gemma, Llama, etc.)
   └── You select: google/gemma3@gemma-3-1b-it

2. MODEL REGISTRY
   └── Creates entry: google-gemma3-gemma-3-1b-it-1766002321
   └── Stores model metadata, version info

3. ENDPOINT CREATION
   └── Creates: mg-endpoint-d389c6c2-0220-4648-8365-f45187716345
   └── Provisions dedicated DNS for your project

4. COMPUTE PROVISIONING
   └── Allocates g2-standard-12 VM
   └── Attaches NVIDIA L4 GPU
   └── Pulls vLLM container image

5. MODEL LOADING
   └── Downloads model weights to GPU memory
   └── Starts vLLM inference server
   └── Health checks pass → endpoint ready

6. TRAFFIC ROUTING
   └── Dedicated DNS resolves to your endpoint
   └── Auth via Bearer token (gcloud auth print-access-token)
   └── Requests routed to vLLM container
```

---

## 8. Differences: Demo vs Production

| Aspect | Demo (What We Did) | Production (What You'd Add) |
|--------|-------------------|---------------------------|
| Replicas | 1 | 2+ across zones |
| Scaling | Fixed | Auto-scale 0-N |
| Network | Public DNS | VPC-SC + Private |
| Auth | User token | Workload Identity |
| IaC | Terraform imported | Terraform from scratch |
| CI/CD | Template ready | Connected to repo |
| Monitoring | Basic | Full dashboards |
