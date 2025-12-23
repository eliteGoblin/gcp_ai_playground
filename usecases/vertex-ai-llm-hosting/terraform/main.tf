# =============================================================================
# Vertex AI LLM Demo - Terraform Configuration
# =============================================================================
# Purpose: Manage Vertex AI infrastructure as code
# Pattern: Demo-scale with production patterns (minimal resources)
# =============================================================================

terraform {
  required_version = ">= 1.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # For production, use remote backend:
  # backend "gcs" {
  #   bucket = "vertexdemo-481519-tfstate"
  #   prefix = "terraform/state"
  # }
}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "vertexdemo-481519"
}

variable "region" {
  description = "GCP Region for Vertex AI"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (demo/staging/prod)"
  type        = string
  default     = "demo"
}

# -----------------------------------------------------------------------------
# Provider
# -----------------------------------------------------------------------------

provider "google" {
  project = var.project_id
  region  = var.region
}

# -----------------------------------------------------------------------------
# APIs - Enable required services
# -----------------------------------------------------------------------------

resource "google_project_service" "apis" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "compute.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# -----------------------------------------------------------------------------
# Service Accounts
# -----------------------------------------------------------------------------

# Service Account for model deployment (CI/CD use)
resource "google_service_account" "deployer" {
  account_id   = "vertex-deployer"
  display_name = "Vertex AI Model Deployer"
  description  = "Used by CI/CD to deploy models"
  project      = var.project_id
}

# Service Account for prediction (runtime use)
resource "google_service_account" "predictor" {
  account_id   = "vertex-predictor"
  display_name = "Vertex AI Predictor"
  description  = "Used by applications to call predictions"
  project      = var.project_id
}

# Existing SA (import this one)
# This was created manually, now managed by Terraform
resource "google_service_account" "vertex_ai_demo" {
  account_id   = "vertex-ai-demo"
  display_name = "Vertex AI Demo Service Account"
  project      = var.project_id
}

# -----------------------------------------------------------------------------
# IAM Bindings - Least Privilege
# -----------------------------------------------------------------------------

# Deployer can manage Vertex AI resources
resource "google_project_iam_member" "deployer_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.admin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Predictor can only call predictions
resource "google_project_iam_member" "predictor_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.predictor.email}"
}

# Existing SA bindings (import these)
resource "google_project_iam_member" "demo_sa_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.vertex_ai_demo.email}"
}

resource "google_project_iam_member" "demo_sa_admin" {
  project = var.project_id
  role    = "roles/aiplatform.admin"
  member  = "serviceAccount:${google_service_account.vertex_ai_demo.email}"
}

# -----------------------------------------------------------------------------
# Vertex AI Endpoint (Import existing)
# -----------------------------------------------------------------------------

# This endpoint was created by gcloud, now managed by Terraform
# Import command: terraform import google_vertex_ai_endpoint.llm_demo projects/vertexdemo-481519/locations/us-central1/endpoints/mg-endpoint-d389c6c2-0220-4648-8365-f45187716345
resource "google_vertex_ai_endpoint" "llm_demo" {
  name         = "mg-endpoint-d389c6c2-0220-4648-8365-f45187716345"
  display_name = "gemma-3-1b-demo"
  description  = "Demo LLM endpoint for Gemma 3 1B"
  location     = var.region
  project      = var.project_id

  labels = {
    environment = var.environment
    managed-by  = "terraform"
    model       = "gemma-3-1b-it"
  }
}

# -----------------------------------------------------------------------------
# Storage - Model Artifacts Bucket
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "model_artifacts" {
  name          = "${var.project_id}-model-artifacts"
  location      = var.region
  project       = var.project_id
  force_destroy = false # Protect model artifacts

  uniform_bucket_level_access = true

  versioning {
    enabled = true # Keep history of model versions
  }

  labels = {
    environment = var.environment
    managed-by  = "terraform"
    purpose     = "model-artifacts"
  }
}

# Deployer can upload models
resource "google_storage_bucket_iam_member" "deployer_storage" {
  bucket = google_storage_bucket.model_artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.deployer.email}"
}

# Predictor can read models (for loading)
resource "google_storage_bucket_iam_member" "predictor_storage" {
  bucket = google_storage_bucket.model_artifacts.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.predictor.email}"
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "project_id" {
  value       = var.project_id
  description = "GCP Project ID"
}

output "endpoint_id" {
  value       = google_vertex_ai_endpoint.llm_demo.name
  description = "Vertex AI Endpoint ID"
}

output "endpoint_dns" {
  value       = "${google_vertex_ai_endpoint.llm_demo.name}.${var.region}-632872760922.prediction.vertexai.goog"
  description = "Dedicated endpoint DNS"
}

output "deployer_sa" {
  value       = google_service_account.deployer.email
  description = "Deployer service account email"
}

output "predictor_sa" {
  value       = google_service_account.predictor.email
  description = "Predictor service account email"
}

output "model_artifacts_bucket" {
  value       = google_storage_bucket.model_artifacts.name
  description = "GCS bucket for model artifacts"
}

output "model_artifacts_uri" {
  value       = "gs://${google_storage_bucket.model_artifacts.name}"
  description = "GCS URI for model artifacts"
}
