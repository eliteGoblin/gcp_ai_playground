# Cloud Monitoring Dashboard for Conversation Coach

resource "google_monitoring_dashboard" "conversation_coach" {
  dashboard_json = jsonencode({
    displayName = "Conversation Coach - AI Coaching Pipeline"

    labels = {
      service = var.service_name
    }

    mosaicLayout = {
      columns = 12

      tiles = [
        # Row 1: Key Metrics Header
        {
          xPos   = 0
          yPos   = 0
          width  = 12
          height = 1
          widget = {
            title = ""
            text = {
              content = "# Conversation Coach - Real-Time Monitoring\n**Service**: ${var.service_name} | **Region**: ${var.region}"
              format  = "MARKDOWN"
            }
          }
        },

        # Row 2: Total Requests (OTEL counter with ALIGN_DELTA)
        {
          xPos   = 0
          yPos   = 1
          width  = 3
          height = 4
          widget = {
            title = "Total Requests"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"workload.googleapis.com/cc_coach_requests_total\" resource.type=\"generic_node\""
                  aggregation = {
                    alignmentPeriod    = "604800s"
                    perSeriesAligner   = "ALIGN_DELTA"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
            }
          }
        },

        # Row 2: Success Count (OTEL counter with ALIGN_DELTA)
        {
          xPos   = 3
          yPos   = 1
          width  = 3
          height = 4
          widget = {
            title = "Successful Requests"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"workload.googleapis.com/cc_coach_requests_total\" metric.label.success=\"true\" resource.type=\"generic_node\""
                  aggregation = {
                    alignmentPeriod    = "604800s"
                    perSeriesAligner   = "ALIGN_DELTA"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
            }
          }
        },

        # Row 2: E2E Latency Avg (OTEL - using ALIGN_DELTA for histogram count)
        {
          xPos   = 6
          yPos   = 1
          width  = 3
          height = 4
          widget = {
            title = "Requests Processed"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"workload.googleapis.com/cc_coach_request_duration_ms\" resource.type=\"generic_node\""
                  aggregation = {
                    alignmentPeriod    = "3600s"
                    perSeriesAligner   = "ALIGN_DELTA"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
            }
          }
        },

        # Row 2: Total Cost (OTEL Real-time - micro USD)
        {
          xPos   = 9
          yPos   = 1
          width  = 3
          height = 4
          widget = {
            title = "Total Cost (micro-USD)"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"workload.googleapis.com/cc_coach_cost_micro_usd\" resource.type=\"generic_node\""
                  aggregation = {
                    alignmentPeriod    = "86400s"
                    perSeriesAligner   = "ALIGN_DELTA"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
            }
          }
        },

        # Row 3: Request Rate by Success (OTEL Real-time)
        {
          xPos   = 0
          yPos   = 5
          width  = 6
          height = 4
          widget = {
            title = "Request Rate by Success (Real-time)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_requests_total\" metric.label.success=\"true\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Success"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_requests_total\" metric.label.success=\"false\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Failure"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Requests/min"
                scale = "LINEAR"
              }
            }
          }
        },

        # Row 3: E2E Request Count Over Time (OTEL histogram count)
        {
          xPos   = 6
          yPos   = 5
          width  = 6
          height = 4
          widget = {
            title = "Request Count Over Time"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_request_duration_ms\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Requests"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Request Count"
                scale = "LINEAR"
              }
            }
          }
        },

        # Row 4: Component Health
        {
          xPos   = 0
          yPos   = 9
          width  = 12
          height = 1
          widget = {
            title = ""
            text = {
              content = "## Component Health"
              format  = "MARKDOWN"
            }
          }
        },

        # Row 5: Component Success/Failure
        {
          xPos   = 0
          yPos   = 10
          width  = 6
          height = 4
          widget = {
            title = "Component Success by Type"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.component_success.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["metric.label.component"]
                      }
                    }
                  }
                  plotType   = "STACKED_BAR"
                  legendTemplate = "$${metric.label.component}"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Calls/min"
                scale = "LINEAR"
              }
            }
          }
        },

        # Row 5: Component Latency
        {
          xPos   = 6
          yPos   = 10
          width  = 6
          height = 4
          widget = {
            title = "Component Latency (P50)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.component_latency.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_50"
                        crossSeriesReducer = "REDUCE_MEAN"
                        groupByFields      = ["metric.label.component"]
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "$${metric.label.component}"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Latency (ms)"
                scale = "LINEAR"
              }
            }
          }
        },

        # Row 6: Cost & Token Metrics
        {
          xPos   = 0
          yPos   = 14
          width  = 12
          height = 1
          widget = {
            title = ""
            text = {
              content = "## Cost & Token Usage"
              format  = "MARKDOWN"
            }
          }
        },

        # Row 7: Token Usage Over Time (OTEL Real-time)
        {
          xPos   = 0
          yPos   = 15
          width  = 6
          height = 4
          widget = {
            title = "Token Usage (Real-time)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_tokens_total\" metric.label.type=\"input\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Input Tokens"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_tokens_total\" metric.label.type=\"output\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Output Tokens"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Tokens"
                scale = "LINEAR"
              }
            }
          }
        },

        # Row 7: Cost Over Time (OTEL Real-time)
        {
          xPos   = 6
          yPos   = 15
          width  = 6
          height = 4
          widget = {
            title = "Cost Accumulation (micro-USD, Real-time)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_cost_micro_usd\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "3600s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType   = "STACKED_BAR"
                  legendTemplate = "Cost (micro-USD)"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Cost (micro-USD)"
                scale = "LINEAR"
              }
            }
          }
        },

        # Row 8: Model Performance
        {
          xPos   = 0
          yPos   = 19
          width  = 12
          height = 1
          widget = {
            title = ""
            text = {
              content = "## Model Performance (Gemini)"
              format  = "MARKDOWN"
            }
          }
        },

        # Row 9: Model Call Count (OTEL histogram count)
        {
          xPos   = 0
          yPos   = 20
          width  = 6
          height = 4
          widget = {
            title = "Model Calls Over Time"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_model_latency_ms\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Model Calls"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Call Count"
                scale = "LINEAR"
              }
            }
          }
        },

        # Row 9: Errors (OTEL counter)
        {
          xPos   = 6
          yPos   = 20
          width  = 6
          height = 4
          widget = {
            title = "Errors by Type"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_errors_total\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["metric.label.error_type"]
                      }
                    }
                  }
                  plotType   = "STACKED_BAR"
                  legendTemplate = "$${metric.label.error_type}"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Errors"
                scale = "LINEAR"
              }
            }
          }
        },

        # Row 10: RAG Performance
        {
          xPos   = 0
          yPos   = 24
          width  = 12
          height = 1
          widget = {
            title = ""
            text = {
              content = "## RAG Performance"
              format  = "MARKDOWN"
            }
          }
        },

        # Row 11: RAG Requests
        {
          xPos   = 0
          yPos   = 25
          width  = 6
          height = 4
          widget = {
            title = "RAG Requests (Real-time)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_rag_requests_total\" metric.label.fallback_used=\"false\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "RAG Used"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_rag_requests_total\" metric.label.fallback_used=\"true\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Fallback Used"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Requests"
                scale = "LINEAR"
              }
            }
          }
        },

        # Row 11: Documents Retrieved
        {
          xPos   = 6
          yPos   = 25
          width  = 6
          height = 4
          widget = {
            title = "Documents Retrieved Distribution"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"workload.googleapis.com/cc_coach_rag_requests_total\" resource.type=\"generic_node\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["metric.label.docs_retrieved"]
                      }
                    }
                  }
                  plotType   = "STACKED_BAR"
                  legendTemplate = "$${metric.label.docs_retrieved} docs"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Requests"
                scale = "LINEAR"
              }
            }
          }
        }
      ]
    }
  })
}
