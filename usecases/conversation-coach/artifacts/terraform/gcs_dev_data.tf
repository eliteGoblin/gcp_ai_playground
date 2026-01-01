# =============================================================================
# Conversation Coach - Dev Data Storage
# =============================================================================
# Purpose: GCS bucket for dev/test conversation data
# Environment: dev (fake PII, testing pipeline)
# =============================================================================

terraform {
  required_version = ">= 1.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
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
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
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
    "storage.googleapis.com",
    "iam.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# -----------------------------------------------------------------------------
# GCS Bucket - Dev Data (raw conversation artifacts)
# -----------------------------------------------------------------------------
# Structure:
#   gs://<project>-cc-dev/
#     2025-12-28/
#       <UUID>/
#         metadata.json
#         transcription.json
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "cc_dev" {
  name          = "${var.project_id}-cc-dev"
  location      = var.region
  project       = var.project_id
  force_destroy = true  # Dev bucket, safe to destroy

  uniform_bucket_level_access = true

  # Dev data retention: 30 days
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    environment = var.environment
    managed-by  = "terraform"
    purpose     = "conversation-coach-dev-data"
    usecase     = "conversation-coach"
  }
}

# -----------------------------------------------------------------------------
# Service Account - Data Uploader (for scripts/CI)
# -----------------------------------------------------------------------------

resource "google_service_account" "cc_data_uploader" {
  account_id   = "cc-data-uploader"
  display_name = "Conversation Coach Data Uploader"
  description  = "Used by scripts/CI to upload dev test data"
  project      = var.project_id
}

# Data uploader can write to dev bucket
resource "google_storage_bucket_iam_member" "uploader_storage" {
  bucket = google_storage_bucket.cc_dev.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cc_data_uploader.email}"
}

# -----------------------------------------------------------------------------
# Service Account - Pipeline Reader (for ingestion pipeline)
# -----------------------------------------------------------------------------

resource "google_service_account" "cc_pipeline" {
  account_id   = "cc-pipeline"
  display_name = "Conversation Coach Pipeline"
  description  = "Used by ingestion pipeline to read conversation data"
  project      = var.project_id
}

# Pipeline can read from dev bucket
resource "google_storage_bucket_iam_member" "pipeline_storage" {
  bucket = google_storage_bucket.cc_dev.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cc_pipeline.email}"
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "dev_bucket_name" {
  value       = google_storage_bucket.cc_dev.name
  description = "GCS bucket name for dev data"
}

output "dev_bucket_uri" {
  value       = "gs://${google_storage_bucket.cc_dev.name}"
  description = "GCS URI for dev data"
}

output "uploader_sa" {
  value       = google_service_account.cc_data_uploader.email
  description = "Data uploader service account email"
}

output "pipeline_sa" {
  value       = google_service_account.cc_pipeline.email
  description = "Pipeline service account email"
}
