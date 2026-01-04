# =============================================================================
# Conversation Coach - RAG Knowledge Base Infrastructure
# =============================================================================
# Purpose: Infrastructure for RAG pipeline
# Components:
#   - GCS bucket for KB documents (active docs only)
#   - BigQuery tables for metadata and audit
#   - Vertex AI Search (Data Store/App) - manual setup via gcloud, see comments
# =============================================================================

# -----------------------------------------------------------------------------
# Enable Required APIs
# -----------------------------------------------------------------------------

resource "google_project_service" "discoveryengine" {
  project            = var.project_id
  service            = "discoveryengine.googleapis.com"
  disable_on_destroy = false
}

# -----------------------------------------------------------------------------
# GCS Bucket for KB Documents
# -----------------------------------------------------------------------------
# Only active documents are stored here (synced by cc ingest)
# Vertex AI Search auto-indexes this bucket

resource "google_storage_bucket" "kb_documents" {
  name          = "${var.project_id}-cc-kb-docs"
  project       = var.project_id
  location      = var.kb_location
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = false # We handle versioning via immutable artifacts model
  }

  labels = {
    environment = var.environment
    managed_by  = "terraform"
    usecase     = "conversation-coach"
    component   = "rag-knowledge-base"
  }

  depends_on = [google_project_service.apis]
}

# -----------------------------------------------------------------------------
# BigQuery Tables for KB Metadata
# -----------------------------------------------------------------------------

resource "google_bigquery_table" "kb_documents" {
  dataset_id = google_bigquery_dataset.conversation_coach.dataset_id
  table_id   = "kb_documents"
  project    = var.project_id

  description = "Knowledge base document registry - metadata, versions, audit trail"

  schema = jsonencode([
    {
      name        = "uuid"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Deterministic UUID (hash of file_path + version)"
    },
    {
      name        = "doc_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Human-readable ID: POL-002"
    },
    {
      name        = "doc_type"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "policy, coaching, example, external"
    },
    {
      name        = "title"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Document title"
    },
    {
      name        = "version"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Semantic version: 1.0.0"
    },
    {
      name        = "file_path"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Relative path from documents/"
    },
    {
      name        = "status"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "active, superseded, retired, deleted, draft"
    },
    {
      name        = "status_reason"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Reason for status change"
    },
    {
      name        = "superseded_by"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "UUID of replacement doc"
    },
    {
      name        = "status_changed_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When status last changed"
    },
    {
      name        = "business_lines"
      type        = "STRING"
      mode        = "REPEATED"
      description = "Applicable business lines"
    },
    {
      name        = "queues"
      type        = "STRING"
      mode        = "REPEATED"
      description = "Applicable queues"
    },
    {
      name        = "regions"
      type        = "STRING"
      mode        = "REPEATED"
      description = "Applicable regions"
    },
    {
      name        = "raw_content"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Full markdown including frontmatter"
    },
    {
      name        = "checksum"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "SHA-256 for change detection"
    },
    {
      name        = "author"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Document author"
    },
    {
      name        = "approved_by"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Approver"
    },
    {
      name        = "effective_date"
      type        = "DATE"
      mode        = "NULLABLE"
      description = "When document becomes effective"
    },
    {
      name        = "expiry_date"
      type        = "DATE"
      mode        = "NULLABLE"
      description = "When document expires"
    },
    {
      name        = "last_reviewed"
      type        = "DATE"
      mode        = "NULLABLE"
      description = "Last review date"
    },
    {
      name        = "created_at"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "Record creation timestamp"
    },
    {
      name        = "updated_at"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "Record update timestamp"
    }
  ])

  labels = {
    component = "rag-knowledge-base"
  }

  depends_on = [google_bigquery_dataset.conversation_coach]
}

resource "google_bigquery_table" "kb_retrieval_log" {
  dataset_id = google_bigquery_dataset.conversation_coach.dataset_id
  table_id   = "kb_retrieval_log"
  project    = var.project_id

  description = "Audit log for RAG retrievals - tracks which docs were used for each coaching"

  time_partitioning {
    type  = "DAY"
    field = "retrieved_at"
  }

  schema = jsonencode([
    {
      name        = "retrieval_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Unique retrieval identifier"
    },
    {
      name        = "conversation_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Conversation being coached"
    },
    {
      name        = "query_text"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Search query sent to Vertex AI"
    },
    {
      name = "retrieved_docs"
      type = "RECORD"
      mode = "REPEATED"
      fields = [
        { name = "uuid", type = "STRING", mode = "NULLABLE" },
        { name = "doc_id", type = "STRING", mode = "NULLABLE" },
        { name = "version", type = "STRING", mode = "NULLABLE" },
        { name = "section", type = "STRING", mode = "NULLABLE" },
        { name = "snippet", type = "STRING", mode = "NULLABLE" },
        { name = "relevance_score", type = "FLOAT64", mode = "NULLABLE" }
      ]
      description = "Documents retrieved for this query"
    },
    {
      name        = "coach_model_version"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Model used for coaching"
    },
    {
      name        = "prompt_version"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Version of coaching prompt"
    },
    {
      name        = "business_line"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Business context"
    },
    {
      name        = "retrieved_at"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "When retrieval occurred"
    }
  ])

  labels = {
    component = "rag-knowledge-base"
  }

  depends_on = [google_bigquery_dataset.conversation_coach]
}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "kb_location" {
  description = "Location for KB resources (GCS bucket)"
  type        = string
  default     = "australia-southeast1"
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "kb_bucket_name" {
  description = "GCS bucket for KB documents"
  value       = google_storage_bucket.kb_documents.name
}

output "kb_bucket_url" {
  description = "GCS bucket URL"
  value       = google_storage_bucket.kb_documents.url
}

# -----------------------------------------------------------------------------
# Vertex AI Search - Manual Setup Required
# -----------------------------------------------------------------------------
# Terraform support for Vertex AI Search (Discovery Engine) is limited.
# Create Data Store and Search App manually using gcloud:
#
# 1. Create Data Store:
#    gcloud alpha discovery-engine data-stores create cc-kb-datastore \
#      --location=global \
#      --display-name="Conversation Coach KB" \
#      --industry-vertical=GENERIC \
#      --content-config=CONTENT_REQUIRED \
#      --solution-types=SOLUTION_TYPE_SEARCH
#
# 2. Link GCS bucket as data source:
#    gcloud alpha discovery-engine data-stores update cc-kb-datastore \
#      --location=global \
#      --add-gcs-source=gs://${var.project_id}-cc-kb-docs/kb/
#
# 3. Create Search App:
#    gcloud alpha discovery-engine apps create cc-kb-search \
#      --location=global \
#      --display-name="Conversation Coach KB Search" \
#      --data-store-ids=cc-kb-datastore
#
# Then set environment variables:
#   export RAG_DATA_STORE_ID=cc-kb-datastore
#   export RAG_GCS_BUCKET=${var.project_id}-cc-kb-docs
# -----------------------------------------------------------------------------
