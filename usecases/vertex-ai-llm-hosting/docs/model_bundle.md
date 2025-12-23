# Model Bundle & Versioning Guide

## Overview

This document explains how model artifacts are packaged, versioned, and deployed to Vertex AI.

---

## 1. What Is a Model Bundle?

A "model" in Vertex AI is actually a **bundle** of multiple artifacts:

```
gs://vertexdemo-481519-model-artifacts/models/loan-assessor/v1.0.0/
│
├── model/                           ← Model weights + config
│   ├── model.safetensors           ← The actual neural network weights
│   ├── config.json                 ← Architecture config (layers, hidden size)
│   ├── generation_config.json      ← Default generation settings
│   └── tokenizer files...          ← Text ↔ token conversion
│
├── custom_code/                     ← Your business logic
│   ├── predictor.py                ← Pre/post processing
│   ├── guardrails.py               ← Safety filters
│   └── requirements.txt            ← Python dependencies
│
├── serving_config.json              ← Deployment settings
└── model_card.md                    ← Documentation
```

---

## 2. Bundle Components Explained

### 2.1 Model Weights (`model/`)

```
What it is:
├── Billions of numbers that encode the model's "knowledge"
├── Result of training on massive text data
├── Can be modified through fine-tuning

File formats:
├── .safetensors  → Modern, safe format (recommended)
├── .bin          → PyTorch format (pytorch_model.bin)
└── .ckpt         → TensorFlow checkpoint

Size:
├── Gemma 1B:   ~2 GB
├── Gemma 7B:   ~14 GB
├── Llama 8B:   ~16 GB
└── Llama 70B:  ~140 GB
```

### 2.2 Tokenizer

```
What it does:
Text → Numbers → Model → Numbers → Text

Example:
"Hello world" → [15496, 995] → Model → [1212, 612] → "Hi there"

Files:
├── tokenizer.json          ← Main tokenizer config
├── tokenizer_config.json   ← Settings (padding, truncation)
├── vocab.txt               ← Token vocabulary (50,000+ tokens)
└── special_tokens_map.json ← [PAD], [EOS], [BOS], etc.
```

### 2.3 Custom Code (`custom_code/`)

```python
# predictor.py - Your business logic

class Predictor:
    def load(self, artifacts_uri):
        """Called once when container starts"""
        # Load model weights into GPU memory

    def preprocess(self, request):
        """BEFORE model inference"""
        # 1. Mask PII (SSN, names)
        # 2. Format prompt
        # 3. Validate input

    def predict(self, processed):
        """The actual LLM call"""
        # model.generate(...)

    def postprocess(self, prediction):
        """AFTER model inference"""
        # 1. Unmask PII
        # 2. Apply guardrails
        # 3. Format response
```

### 2.4 Serving Config

```json
{
  "model_name": "loan-assessor",
  "version": "v1.0.0",
  "container": {
    "image": "us-docker.pkg.dev/vertex-ai/prediction/pytorch-vllm-serve:latest",
    "predict_route": "/predict",
    "health_route": "/health"
  },
  "resources": {
    "machine_type": "g2-standard-12",
    "accelerator_type": "NVIDIA_L4",
    "accelerator_count": 1
  }
}
```

---

## 3. How Vertex AI Loads Your Bundle

```
1. YOU UPLOAD BUNDLE TO GCS
   └── gsutil cp -r bundle/* gs://bucket/models/loan-assessor/v1.0.0/

2. YOU REGISTER IN MODEL REGISTRY
   └── gcloud ai models upload \
         --artifact-uri=gs://bucket/models/loan-assessor/v1.0.0/ \
         --container-image-uri=pytorch-vllm-serve

3. VERTEX AI DEPLOYS
   │
   ├── Provisions VM (g2-standard-12 + L4 GPU)
   │
   ├── Pulls container image (pytorch-vllm-serve)
   │
   ├── Mounts GCS bucket
   │
   ├── Runs your predictor.py:
   │   │
   │   └── predictor.load("gs://bucket/models/loan-assessor/v1.0.0/")
   │       │
   │       ├── Downloads model weights to GPU memory
   │       ├── Loads tokenizer
   │       └── Initializes your custom code
   │
   └── Starts serving on /predict endpoint

4. REQUEST FLOW
   │
   │  POST /predict {"prompt": "Check loan for John SSN 123-45-6789"}
   │
   ├── predictor.preprocess()
   │   └── Mask SSN → "Check loan for John [SSN_0]"
   │
   ├── predictor.predict()
   │   └── LLM generates response
   │
   └── predictor.postprocess()
       └── Unmask, add guardrails → Response to user
```

---

## 4. Versioning Strategy

### Semantic Versioning

```
v MAJOR . MINOR . PATCH
   │       │       │
   │       │       └── Bug fix (prompt tweak, config fix)
   │       └── New feature (guardrails added, fine-tuned)
   └── Breaking change (new base model, API change)

Examples:
├── v1.0.0 → Initial release with base Gemma
├── v1.1.0 → Added PII masking
├── v1.1.1 → Fixed prompt injection bug
└── v2.0.0 → Upgraded to Gemma 2 base model
```

### Version Aliases

```bash
# Register with aliases
gcloud ai models upload \
  --version-aliases="v1.2.0,latest,production"

# Deploy specific version
gcloud ai endpoints deploy-model $ENDPOINT \
  --model="projects/xxx/models/loan-assessor@v1.2.0"

# Deploy latest
gcloud ai endpoints deploy-model $ENDPOINT \
  --model="projects/xxx/models/loan-assessor@latest"
```

---

## 5. CI/CD Pipeline

### Build Workflow (`.github/workflows/build-model.yml`)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MODEL BUILD PIPELINE                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Trigger                                                           │
│   ├── Manual: workflow_dispatch (select model, version)             │
│   └── Auto: push to models/custom_code/**                           │
│                                                                     │
│   Jobs:                                                             │
│                                                                     │
│   1. VALIDATE                                                       │
│      ├── Lint custom code                                           │
│      ├── Type check                                                 │
│      └── Test guardrails                                            │
│                                                                     │
│   2. BUILD BUNDLE                                                   │
│      ├── Create directory structure                                 │
│      ├── Download base model (or use fine-tuned)                    │
│      ├── Copy custom code                                           │
│      ├── Generate model card                                        │
│      └── Upload to GCS                                              │
│                                                                     │
│   3. REGISTER                                                       │
│      ├── Register in Vertex AI Model Registry                       │
│      └── Tag with version aliases                                   │
│                                                                     │
│   4. DEPLOY (optional)                                              │
│      ├── Deploy to endpoint                                         │
│      └── Verify health                                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Running the Pipeline

```bash
# Via GitHub UI:
# 1. Go to Actions → "Build and Register Model"
# 2. Click "Run workflow"
# 3. Fill in:
#    - model_name: loan-assessor
#    - version: v1.0.0
#    - base_model: google/gemma-3-1b-it
#    - deploy_after_build: true/false

# Via GitHub CLI:
gh workflow run build-model.yml \
  -f model_name=loan-assessor \
  -f version=v1.0.0 \
  -f base_model=google/gemma-3-1b-it \
  -f deploy_after_build=false
```

---

## 6. File Structure

```
gcp_ml_playground/
│
├── terraform/
│   └── main.tf                      ← Infrastructure (bucket, endpoint, IAM)
│
├── models/
│   ├── scripts/
│   │   └── package_model.py         ← Local packaging script
│   │
│   └── custom_code/
│       ├── predictor.py             ← Pre/post processing
│       ├── guardrails.py            ← Safety filters
│       └── requirements.txt         ← Dependencies
│
├── .github/workflows/
│   ├── deploy-model.yml             ← Infrastructure deployment
│   └── build-model.yml              ← Model build & register
│
└── documents/
    └── topic/
        └── model_bundle.md          ← This document
```

---

## 7. Quick Reference Commands

```bash
# ===== LOCAL PACKAGING =====
python models/scripts/package_model.py \
  --model-name loan-assessor \
  --version v1.0.0 \
  --base-model google/gemma-3-1b-it \
  --bucket gs://vertexdemo-481519-model-artifacts

# ===== LIST MODELS IN REGISTRY =====
gcloud ai models list --region=us-central1

# ===== DESCRIBE MODEL =====
gcloud ai models describe MODEL_ID --region=us-central1

# ===== LIST MODEL VERSIONS =====
gcloud ai models list-version MODEL_ID --region=us-central1

# ===== DEPLOY MODEL TO ENDPOINT =====
gcloud ai endpoints deploy-model ENDPOINT_ID \
  --region=us-central1 \
  --model=MODEL_ID \
  --display-name="loan-assessor-v1.0.0" \
  --machine-type=g2-standard-12 \
  --accelerator=type=NVIDIA_L4,count=1

# ===== CHECK ARTIFACTS IN GCS =====
gsutil ls -r gs://vertexdemo-481519-model-artifacts/models/
```

---

## 8. What We Have vs What's Possible

| Feature | Our Demo | Full Production |
|---------|----------|-----------------|
| **Model Weights** | Base model (no fine-tune) | Fine-tuned on your data |
| **Custom Code** | Sample predictor | Full PII handling, guardrails |
| **Versioning** | Manual | Automated semantic versioning |
| **CI/CD** | GitHub Actions template | Full pipeline with tests |
| **Deployment** | Single endpoint | Multi-env (dev/staging/prod) |
| **Rollback** | Manual | Automated canary rollback |
