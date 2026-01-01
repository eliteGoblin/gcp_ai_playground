# =============================================================================
# Conversation Coach - CCAI Insights Infrastructure
# =============================================================================
# Purpose: Enable and configure CCAI Insights API for conversation analysis
# =============================================================================

# -----------------------------------------------------------------------------
# Enable CCAI Insights API
# -----------------------------------------------------------------------------

resource "google_project_service" "ccai_insights" {
  project            = var.project_id
  service            = "contactcenterinsights.googleapis.com"
  disable_on_destroy = false
}

# -----------------------------------------------------------------------------
# Service Account for CCAI Insights operations
# -----------------------------------------------------------------------------

resource "google_service_account" "ccai_insights" {
  account_id   = "cc-insights-sa"
  display_name = "Conversation Coach - CCAI Insights"
  description  = "Service account for CCAI Insights operations"
  project      = var.project_id
}

# Grant CCAI Insights admin role
resource "google_project_iam_member" "ccai_insights_admin" {
  project = var.project_id
  role    = "roles/contactcenterinsights.admin"
  member  = "serviceAccount:${google_service_account.ccai_insights.email}"
}

# Grant BigQuery data editor for exports
resource "google_project_iam_member" "ccai_insights_bq" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.ccai_insights.email}"
}

# Grant GCS read access for conversation data
resource "google_storage_bucket_iam_member" "ccai_insights_gcs" {
  bucket = google_storage_bucket.cc_dev.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.ccai_insights.email}"
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "ccai_insights_sa" {
  value       = google_service_account.ccai_insights.email
  description = "CCAI Insights service account email"
}
