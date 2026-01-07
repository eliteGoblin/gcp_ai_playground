# Terraform configuration for Conversation Coach Monitoring
# This creates Cloud Logging sinks, log-based metrics, and Cloud Monitoring dashboards

terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Note: APIs should already be enabled in the project
# The service account needs roles/logging.configWriter and roles/monitoring.admin
# to create log-based metrics and dashboards
#
# To grant permissions, run as project owner:
#   gcloud projects add-iam-policy-binding vertexdemo-481519 \
#     --member="serviceAccount:vertex-ai-demo@vertexdemo-481519.iam.gserviceaccount.com" \
#     --role="roles/logging.configWriter"
#   gcloud projects add-iam-policy-binding vertexdemo-481519 \
#     --member="serviceAccount:vertex-ai-demo@vertexdemo-481519.iam.gserviceaccount.com" \
#     --role="roles/monitoring.admin"

# Outputs
output "dashboard_url" {
  value       = "https://console.cloud.google.com/monitoring/dashboards/builder/${google_monitoring_dashboard.conversation_coach.id}?project=${var.project_id}"
  description = "URL to the Cloud Monitoring dashboard"
}

output "log_explorer_url" {
  value       = "https://console.cloud.google.com/logs/query;query=resource.labels.service_name%3D%22${var.service_name}%22?project=${var.project_id}"
  description = "URL to view logs in Log Explorer"
}
