# Variables for Conversation Coach Monitoring Infrastructure

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

variable "service_name" {
  description = "Service name for labeling resources"
  type        = string
  default     = "conversation-coach"
}

variable "log_bucket_name" {
  description = "Name for the log bucket"
  type        = string
  default     = "conversation-coach-logs"
}

variable "log_retention_days" {
  description = "Log retention in days"
  type        = number
  default     = 30
}
