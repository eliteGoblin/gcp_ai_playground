# =============================================================================
# Conversation Coach - BigQuery Infrastructure
# =============================================================================
# Purpose: Create BigQuery dataset and tables for the conversation coaching pipeline
# Tables:
#   - conversation_registry: Pipeline state tracking
#   - ci_enrichment: CCAI Insights analysis results
#   - coaching_cards: AI-generated coaching outputs
# =============================================================================

# -----------------------------------------------------------------------------
# Enable BigQuery API
# -----------------------------------------------------------------------------

resource "google_project_service" "bigquery" {
  project            = var.project_id
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

# -----------------------------------------------------------------------------
# BigQuery Dataset
# -----------------------------------------------------------------------------

resource "google_bigquery_dataset" "conversation_coach" {
  dataset_id  = "conversation_coach"
  project     = var.project_id
  location    = "US"
  description = "Conversation Coach pipeline data - registry, CI enrichment, coaching cards"

  labels = {
    environment = var.environment
    managed_by  = "terraform"
    usecase     = "conversation-coach"
  }

  # Default table expiration: none (persistent tables)
  # Can add lifecycle policies per-table if needed

  depends_on = [google_project_service.bigquery]
}

# -----------------------------------------------------------------------------
# Table: conversation_registry
# Purpose: Track pipeline state for each conversation (idempotency, audit)
# -----------------------------------------------------------------------------

resource "google_bigquery_table" "conversation_registry" {
  dataset_id = google_bigquery_dataset.conversation_coach.dataset_id
  table_id   = "conversation_registry"
  project    = var.project_id

  description = "Pipeline state tracking for conversations - enables idempotent processing"

  clustering = ["status"]

  schema = jsonencode([
    {
      name        = "conversation_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Primary key - conversation UUID"
    },
    {
      name        = "transcript_uri_raw"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "GCS URI for raw transcript"
    },
    {
      name        = "metadata_uri_raw"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "GCS URI for raw metadata"
    },
    {
      name        = "audio_uri_raw"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "GCS URI for raw audio (future)"
    },
    {
      name        = "transcript_uri_sanitized"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "GCS URI for sanitized transcript (post-DLP)"
    },
    {
      name        = "metadata_uri_sanitized"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "GCS URI for sanitized metadata"
    },
    {
      name        = "audio_uri_sanitized"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "GCS URI for sanitized audio"
    },
    {
      name        = "has_transcript"
      type        = "BOOLEAN"
      mode        = "NULLABLE"
      description = "Whether transcript file exists"
    },
    {
      name        = "has_metadata"
      type        = "BOOLEAN"
      mode        = "NULLABLE"
      description = "Whether metadata file exists"
    },
    {
      name        = "has_audio"
      type        = "BOOLEAN"
      mode        = "NULLABLE"
      description = "Whether audio file exists"
    },
    {
      name        = "status"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Pipeline status: NEW, SANITIZED, INGESTED, ENRICHED, COACHED, FAILED"
    },
    {
      name        = "redaction_version"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "DLP redaction version applied"
    },
    {
      name        = "pii_types_found"
      type        = "STRING"
      mode        = "REPEATED"
      description = "PII types detected during redaction"
    },
    {
      name        = "ci_conversation_name"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "CCAI Insights conversation resource name"
    },
    {
      name        = "ci_analysis_id"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "CCAI Insights analysis ID"
    },
    {
      name        = "last_error"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Last error message if failed"
    },
    {
      name        = "retry_count"
      type        = "INTEGER"
      mode        = "NULLABLE"
      description = "Number of retry attempts"
    },
    {
      name        = "created_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When the record was created"
    },
    {
      name        = "updated_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When the record was last updated"
    },
    {
      name        = "ingested_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When ingested to CCAI Insights"
    },
    {
      name        = "enriched_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When CI analysis completed"
    },
    {
      name        = "coached_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When coaching card was generated"
    }
  ])

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# -----------------------------------------------------------------------------
# Table: ci_enrichment
# Purpose: Store CCAI Insights analysis results
# -----------------------------------------------------------------------------

resource "google_bigquery_table" "ci_enrichment" {
  dataset_id = google_bigquery_dataset.conversation_coach.dataset_id
  table_id   = "ci_enrichment"
  project    = var.project_id

  description = "CCAI Insights analysis results - sentiment, entities, topics"

  schema = jsonencode([
    {
      name        = "conversation_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Conversation UUID (FK to registry)"
    },
    {
      name        = "ci_conversation_name"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "CCAI Insights conversation resource name"
    },
    {
      name        = "transcript"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Full transcript text"
    },
    {
      name        = "turn_count"
      type        = "INTEGER"
      mode        = "NULLABLE"
      description = "Number of conversation turns"
    },
    {
      name        = "duration_sec"
      type        = "INTEGER"
      mode        = "NULLABLE"
      description = "Conversation duration in seconds"
    },
    {
      name        = "agent_sentiment_score"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Agent sentiment score (-1 to 1)"
    },
    {
      name        = "agent_sentiment_magnitude"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Agent sentiment magnitude"
    },
    {
      name        = "customer_sentiment_score"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Customer sentiment score (-1 to 1)"
    },
    {
      name        = "customer_sentiment_magnitude"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Customer sentiment magnitude"
    },
    {
      name = "entities"
      type = "RECORD"
      mode = "REPEATED"
      fields = [
        { name = "type", type = "STRING", mode = "NULLABLE" },
        { name = "name", type = "STRING", mode = "NULLABLE" },
        { name = "salience", type = "FLOAT", mode = "NULLABLE" },
        { name = "speaker_tag", type = "INTEGER", mode = "NULLABLE" }
      ]
      description = "Extracted entities"
    },
    {
      name        = "topics"
      type        = "STRING"
      mode        = "REPEATED"
      description = "Detected topics/intents"
    },
    {
      name        = "labels"
      type        = "JSON"
      mode        = "NULLABLE"
      description = "Conversation labels (from metadata)"
    },
    {
      name        = "analysis_completed_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When CI analysis completed"
    },
    {
      name        = "exported_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When exported to this table"
    }
  ])

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# -----------------------------------------------------------------------------
# Table: coaching_cards
# Purpose: Store AI-generated coaching outputs per conversation
# -----------------------------------------------------------------------------

resource "google_bigquery_table" "coaching_cards" {
  dataset_id = google_bigquery_dataset.conversation_coach.dataset_id
  table_id   = "coaching_cards"
  project    = var.project_id

  description = "AI-generated coaching cards with compliance checks and recommendations"

  schema = jsonencode([
    {
      name        = "conversation_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Conversation UUID (FK to registry)"
    },
    {
      name        = "generated_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When the coaching card was generated"
    },
    {
      name        = "coach_version"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Version of the coaching agent"
    },
    {
      name        = "summary_bullets"
      type        = "STRING"
      mode        = "REPEATED"
      description = "Short summary bullet points"
    },
    {
      name        = "driver_label"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Primary call driver/topic"
    },
    {
      name        = "driver_score"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Confidence score for driver classification"
    },
    {
      name        = "compliance_checks"
      type        = "JSON"
      mode        = "NULLABLE"
      description = "Compliance check results with evidence and policy refs"
    },
    {
      name        = "risk_flags"
      type        = "STRING"
      mode        = "REPEATED"
      description = "Detected risk flags"
    },
    {
      name        = "next_actions"
      type        = "JSON"
      mode        = "NULLABLE"
      description = "Recommended next actions with payloads"
    },
    {
      name        = "confidence_score"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Overall confidence score for the coaching card"
    },
    {
      name        = "model_id"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "LLM model used for generation"
    },
    {
      name        = "policy_version"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Policy document version used"
    }
  ])

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "bq_dataset_id" {
  value       = google_bigquery_dataset.conversation_coach.dataset_id
  description = "BigQuery dataset ID"
}

output "bq_registry_table" {
  value       = google_bigquery_table.conversation_registry.table_id
  description = "Conversation registry table ID"
}

output "bq_enrichment_table" {
  value       = google_bigquery_table.ci_enrichment.table_id
  description = "CI enrichment table ID"
}

output "bq_coaching_table" {
  value       = google_bigquery_table.coaching_cards.table_id
  description = "Coaching cards table ID"
}
