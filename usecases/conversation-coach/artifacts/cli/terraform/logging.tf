# Cloud Logging resources for Conversation Coach

# Log-based metrics for monitoring

# 1. E2E Success Rate Metric
resource "google_logging_metric" "e2e_success" {
  name        = "conversation-coach/e2e_success"
  description = "Count of successful E2E coaching requests"
  filter      = <<-EOT
    logName="projects/${var.project_id}/logs/conversation-coach"
    jsonPayload.component="e2e"
    jsonPayload.success=true
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "conversation_id"
      value_type  = "STRING"
      description = "Conversation ID"
    }
  }

  label_extractors = {
    "conversation_id" = "EXTRACT(jsonPayload.conversation_id)"
  }
}

# 2. E2E Failure Rate Metric
resource "google_logging_metric" "e2e_failure" {
  name        = "conversation-coach/e2e_failure"
  description = "Count of failed E2E coaching requests"
  filter      = <<-EOT
    logName="projects/${var.project_id}/logs/conversation-coach"
    jsonPayload.component="e2e"
    jsonPayload.success=false
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "error_type"
      value_type  = "STRING"
      description = "Error type"
    }
  }

  label_extractors = {
    "error_type" = "EXTRACT(jsonPayload.error_type)"
  }
}

# 3. E2E Latency Distribution Metric
resource "google_logging_metric" "e2e_latency" {
  name        = "conversation-coach/e2e_latency"
  description = "E2E coaching request latency distribution"
  filter      = <<-EOT
    logName="projects/${var.project_id}/logs/conversation-coach"
    jsonPayload.component="e2e"
    jsonPayload.duration_ms>0
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"
  }

  value_extractor = "EXTRACT(jsonPayload.duration_ms)"

  bucket_options {
    explicit_buckets {
      bounds = [1000, 5000, 10000, 15000, 20000, 30000, 45000, 60000, 90000, 120000]
    }
  }
}

# 4. Model Call Latency Distribution
resource "google_logging_metric" "model_call_latency" {
  name        = "conversation-coach/model_call_latency"
  description = "Gemini model call latency distribution"
  filter      = <<-EOT
    logName="projects/${var.project_id}/logs/conversation-coach"
    jsonPayload.component="model_call"
    jsonPayload.duration_ms>0
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"
  }

  value_extractor = "EXTRACT(jsonPayload.duration_ms)"

  bucket_options {
    explicit_buckets {
      bounds = [1000, 5000, 10000, 15000, 20000, 30000, 45000, 60000]
    }
  }
}

# 5. Token Usage Metric (Input) - Distribution for sum aggregation
resource "google_logging_metric" "input_tokens" {
  name        = "conversation-coach/input_tokens"
  description = "Input tokens distribution per request"
  filter      = <<-EOT
    logName="projects/${var.project_id}/logs/conversation-coach"
    jsonPayload.component="model_call"
    jsonPayload.input_tokens>0
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "1"
  }

  value_extractor = "EXTRACT(jsonPayload.input_tokens)"

  bucket_options {
    explicit_buckets {
      bounds = [500, 1000, 2000, 3000, 5000, 10000, 20000]
    }
  }
}

# 6. Token Usage Metric (Output) - Distribution for sum aggregation
resource "google_logging_metric" "output_tokens" {
  name        = "conversation-coach/output_tokens"
  description = "Output tokens distribution per request"
  filter      = <<-EOT
    logName="projects/${var.project_id}/logs/conversation-coach"
    jsonPayload.component="model_call"
    jsonPayload.output_tokens>0
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "1"
  }

  value_extractor = "EXTRACT(jsonPayload.output_tokens)"

  bucket_options {
    explicit_buckets {
      bounds = [200, 500, 1000, 2000, 3000, 5000, 10000]
    }
  }
}

# 7. Cost Tracking Metric - Distribution for sum aggregation
resource "google_logging_metric" "request_cost" {
  name        = "conversation-coach/request_cost"
  description = "Cost per coaching request distribution in USD"
  filter      = <<-EOT
    logName="projects/${var.project_id}/logs/conversation-coach"
    jsonPayload.component="e2e"
    jsonPayload.total_cost_usd>0
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "USD"
  }

  value_extractor = "EXTRACT(jsonPayload.total_cost_usd)"

  bucket_options {
    explicit_buckets {
      bounds = [0.0001, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.05]
    }
  }
}

# 8. Component Success Counter
resource "google_logging_metric" "component_success" {
  name        = "conversation-coach/component_success"
  description = "Component-level success count"
  filter      = <<-EOT
    logName="projects/${var.project_id}/logs/conversation-coach"
    jsonPayload.component!="e2e"
    jsonPayload.success=true
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "component"
      value_type  = "STRING"
      description = "Component name"
    }
  }

  label_extractors = {
    "component" = "EXTRACT(jsonPayload.component)"
  }
}

# 9. Component Failure Counter
resource "google_logging_metric" "component_failure" {
  name        = "conversation-coach/component_failure"
  description = "Component-level failure count"
  filter      = <<-EOT
    logName="projects/${var.project_id}/logs/conversation-coach"
    jsonPayload.component!="e2e"
    jsonPayload.success=false
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "component"
      value_type  = "STRING"
      description = "Component name"
    }

    labels {
      key         = "error_type"
      value_type  = "STRING"
      description = "Error type"
    }
  }

  label_extractors = {
    "component"  = "EXTRACT(jsonPayload.component)"
    "error_type" = "EXTRACT(jsonPayload.error_type)"
  }
}

# 10. Component Latency Distribution
resource "google_logging_metric" "component_latency" {
  name        = "conversation-coach/component_latency"
  description = "Component-level latency distribution"
  filter      = <<-EOT
    logName="projects/${var.project_id}/logs/conversation-coach"
    jsonPayload.component!="e2e"
    jsonPayload.duration_ms>0
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"

    labels {
      key         = "component"
      value_type  = "STRING"
      description = "Component name"
    }
  }

  label_extractors = {
    "component" = "EXTRACT(jsonPayload.component)"
  }

  value_extractor = "EXTRACT(jsonPayload.duration_ms)"

  bucket_options {
    explicit_buckets {
      bounds = [100, 500, 1000, 2000, 5000, 10000, 20000, 30000]
    }
  }
}
