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

        # Row 2: E2E Success Rate
        {
          xPos   = 0
          yPos   = 1
          width  = 3
          height = 4
          widget = {
            title = "E2E Success Rate"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.e2e_success.name}\" resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod    = "86400s"
                    perSeriesAligner   = "ALIGN_COUNT"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
            }
          }
        },

        # Row 2: Total Requests
        {
          xPos   = 3
          yPos   = 1
          width  = 3
          height = 4
          widget = {
            title = "Total Requests (Today)"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.e2e_success.name}\" resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod    = "86400s"
                    perSeriesAligner   = "ALIGN_SUM"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
            }
          }
        },

        # Row 2: E2E Latency P50
        {
          xPos   = 6
          yPos   = 1
          width  = 3
          height = 4
          widget = {
            title = "E2E Latency (P50)"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.e2e_latency.name}\" resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod    = "86400s"
                    perSeriesAligner   = "ALIGN_DELTA"
                    crossSeriesReducer = "REDUCE_PERCENTILE_50"
                  }
                }
              }
            }
          }
        },

        # Row 2: Daily Cost (avg per request from distribution)
        {
          xPos   = 9
          yPos   = 1
          width  = 3
          height = 4
          widget = {
            title = "Avg Cost/Request (USD)"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.request_cost.name}\" resource.type=\"global\""
                  aggregation = {
                    alignmentPeriod    = "86400s"
                    perSeriesAligner   = "ALIGN_MEAN"
                    crossSeriesReducer = "REDUCE_MEAN"
                  }
                }
              }
            }
          }
        },

        # Row 3: E2E Success/Failure Over Time
        {
          xPos   = 0
          yPos   = 5
          width  = 6
          height = 4
          widget = {
            title = "E2E Success vs Failure"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.e2e_success.name}\" resource.type=\"global\""
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
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.e2e_failure.name}\" resource.type=\"global\""
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

        # Row 3: E2E Latency Distribution
        {
          xPos   = 6
          yPos   = 5
          width  = 6
          height = 4
          widget = {
            title = "E2E Latency Distribution"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.e2e_latency.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_PERCENTILE_50"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "P50"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.e2e_latency.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_PERCENTILE_95"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "P95"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.e2e_latency.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_PERCENTILE_99"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "P99"
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

        # Row 7: Token Usage (avg per request from distribution)
        {
          xPos   = 0
          yPos   = 15
          width  = 6
          height = 4
          widget = {
            title = "Avg Tokens per Request"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.input_tokens.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_MEAN"
                        crossSeriesReducer = "REDUCE_MEAN"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Avg Input Tokens"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.output_tokens.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_MEAN"
                        crossSeriesReducer = "REDUCE_MEAN"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Avg Output Tokens"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Avg Tokens/Request"
                scale = "LINEAR"
              }
            }
          }
        },

        # Row 7: Cost Over Time (avg per request from distribution)
        {
          xPos   = 6
          yPos   = 15
          width  = 6
          height = 4
          widget = {
            title = "Avg Cost per Request (USD)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.request_cost.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod    = "3600s"
                        perSeriesAligner   = "ALIGN_MEAN"
                        crossSeriesReducer = "REDUCE_MEAN"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Avg Cost (USD)"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "USD per Request"
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

        # Row 9: Model Latency
        {
          xPos   = 0
          yPos   = 20
          width  = 6
          height = 4
          widget = {
            title = "Model Call Latency"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.model_call_latency.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_PERCENTILE_50"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "P50"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.model_call_latency.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_PERCENTILE_95"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "P95"
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

        # Row 9: Errors
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
                      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.component_failure.name}\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
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
                label = "Errors/min"
                scale = "LINEAR"
              }
            }
          }
        }
      ]
    }
  })
}
