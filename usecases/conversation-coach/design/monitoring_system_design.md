# Conversation Coach Monitoring System Design

## Overview

This document outlines the monitoring architecture for the Conversation Coach AI system, designed for production operations on GCP.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONVERSATION COACH MONITORING STACK                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                         APPLICATION LAYER                            │  │
│   │                                                                      │  │
│   │   cc_coach CLI                Cloud Functions (if deployed)         │  │
│   │   ├── analyze_conversation()   ├── coaching_trigger()               │  │
│   │   ├── ingest_documents()       └── rag_sync_trigger()               │  │
│   │   └── rag_search()                                                   │  │
│   │                                                                      │  │
│   │   Instrumented with:                                                │  │
│   │   • OpenTelemetry SDK                                               │  │
│   │   • Cloud Logging client                                            │  │
│   │   • Custom metrics exporter                                         │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                         COLLECTION LAYER                             │  │
│   │                                                                      │  │
│   │   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │  │
│   │   │  Cloud Logging  │  │ Cloud Monitoring│  │  Cloud Trace    │    │  │
│   │   │                 │  │ (Metrics)       │  │                 │    │  │
│   │   │ • Structured    │  │                 │  │ • Request spans │    │  │
│   │   │   JSON logs     │  │ • Latency       │  │ • API call deps │    │  │
│   │   │ • Log levels    │  │ • Throughput    │  │ • Bottlenecks   │    │  │
│   │   │ • Audit trail   │  │ • Error rates   │  │                 │    │  │
│   │   │                 │  │ • Token usage   │  │                 │    │  │
│   │   └────────┬────────┘  └────────┬────────┘  └────────┬────────┘    │  │
│   │            │                    │                    │              │  │
│   └────────────┼────────────────────┼────────────────────┼──────────────┘  │
│                │                    │                    │                  │
│                ▼                    ▼                    ▼                  │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                         STORAGE LAYER                                │  │
│   │                                                                      │  │
│   │   BigQuery (Long-term Analytics)                                    │  │
│   │   ├── coach_metrics         (aggregated coaching metrics)          │  │
│   │   ├── kb_retrieval_log      (RAG audit trail)                      │  │
│   │   ├── coaching_results      (full coaching outputs)                │  │
│   │   └── error_events          (failures for debugging)               │  │
│   │                                                                      │  │
│   │   Cloud Logging Buckets (90-day retention)                          │  │
│   │   └── _Default bucket with log filters                             │  │
│   │                                                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                         ALERTING & VISUALIZATION                     │  │
│   │                                                                      │  │
│   │   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │  │
│   │   │ Cloud Monitoring│  │   Looker Studio │  │    PagerDuty    │    │  │
│   │   │   Dashboards    │  │   (Analytics)   │  │ / OpsGenie      │    │  │
│   │   │                 │  │                 │  │                 │    │  │
│   │   │ • Real-time     │  │ • Historical    │  │ • Alert routing │    │  │
│   │   │   metrics       │  │   trends        │  │ • On-call       │    │  │
│   │   │ • SLO tracking  │  │ • Quality KPIs  │  │ • Escalation    │    │  │
│   │   └─────────────────┘  └─────────────────┘  └─────────────────┘    │  │
│   │                                                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Metrics to Monitor

### 1. Operational Metrics (SRE Focus)

| Metric | Description | Alert Threshold | Source |
|--------|-------------|-----------------|--------|
| `coaching_latency_p50` | Median coaching response time | >10s | Cloud Monitoring |
| `coaching_latency_p95` | 95th percentile latency | >30s | Cloud Monitoring |
| `coaching_error_rate` | Failed coaching requests / total | >5% | Cloud Monitoring |
| `gemini_api_errors` | Vertex AI API failures | >1% | Cloud Logging |
| `rag_retrieval_latency` | RAG search response time | >2s | Cloud Monitoring |
| `rag_fallback_rate` | Using embedded policy (RAG failed) | >10% | Cloud Logging |
| `document_sync_failures` | Failed GCS/BQ syncs | Any | Cloud Monitoring |

### 2. AI Quality Metrics (ML Focus)

| Metric | Description | Alert Threshold | Source |
|--------|-------------|-----------------|--------|
| `coaching_score_mean` | Average overall coaching score | Drift >10% | BigQuery |
| `compliance_score_distribution` | Compliance scores over time | Low scores >20% | BigQuery |
| `coaching_points_per_response` | Avg coaching points generated | <1 or >10 | BigQuery |
| `rag_relevance_scores` | RAG retrieval quality | Mean <0.5 | BigQuery |
| `citation_rate` | % of responses with citations | <50% (when RAG active) | BigQuery |
| `call_type_distribution` | Distribution of detected call types | Drift detection | BigQuery |
| `key_moment_detection_rate` | % conversations with key moment | <80% | BigQuery |

### 3. Cost & Usage Metrics (FinOps Focus)

| Metric | Description | Alert Threshold | Source |
|--------|-------------|-----------------|--------|
| `gemini_input_tokens` | Total input tokens consumed | Budget threshold | Cloud Monitoring |
| `gemini_output_tokens` | Total output tokens generated | Budget threshold | Cloud Monitoring |
| `vertex_search_queries` | RAG search API calls | >10K/day | Cloud Monitoring |
| `bigquery_scanned_bytes` | BQ query costs | >10GB/day | BQ audit logs |
| `estimated_daily_cost` | Projected daily spend | >$100/day | Custom |

### 4. Business Metrics (Stakeholder Focus)

| Metric | Description | Target | Source |
|--------|-------------|--------|--------|
| `conversations_coached_daily` | Volume throughput | Track trend | BigQuery |
| `avg_score_by_business_line` | Score breakdown by unit | Trend analysis | BigQuery |
| `improvement_areas_frequency` | Top coaching themes | Insights | BigQuery |
| `policy_citation_frequency` | Which policies cited most | KB relevance | BigQuery |

---

## Logging Strategy

### Log Levels & Content

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STRUCTURED LOGGING DESIGN                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   LOG LEVELS:                                                               │
│   ═══════════                                                               │
│                                                                             │
│   ERROR (Always logged, always alerted)                                     │
│   ├── Gemini API failures                                                   │
│   ├── JSON parse failures                                                   │
│   ├── BQ write failures                                                     │
│   └── Critical validation errors                                            │
│                                                                             │
│   WARNING (Logged, alert on pattern)                                        │
│   ├── RAG fallback to embedded policy                                       │
│   ├── Low relevance scores (<0.3)                                           │
│   ├── Retry attempts                                                        │
│   └── Slow responses (>p95)                                                 │
│                                                                             │
│   INFO (Standard operations, sampled in prod)                               │
│   ├── Request start/end with metrics                                        │
│   ├── Coaching result summary                                               │
│   ├── RAG retrieval summary                                                 │
│   └── Document sync operations                                              │
│                                                                             │
│   DEBUG (Dev/troubleshooting only, disabled in prod)                        │
│   ├── Full prompts (CC_LOG_FULL_PROMPT=true)                               │
│   ├── Full RAG context                                                      │
│   ├── Raw API responses                                                     │
│   └── Detailed timing breakdowns                                            │
│                                                                             │
│   STRUCTURED LOG FORMAT (JSON):                                             │
│   ══════════════════════════════                                            │
│                                                                             │
│   {                                                                         │
│     "severity": "INFO",                                                     │
│     "message": "Coaching result",                                           │
│     "labels": {                                                             │
│       "service": "conversation-coach",                                      │
│       "component": "coaching_service"                                       │
│     },                                                                      │
│     "jsonPayload": {                                                        │
│       "request_id": "abc12345",                                            │
│       "conversation_id": "conv_789",                                        │
│       "model": "gemini-1.5-flash-002",                                     │
│       "latency_ms": 3420,                                                  │
│       "overall_score": 7.8,                                                 │
│       "compliance_score": 8,                                                │
│       "has_rag_context": true,                                             │
│       "coaching_points_count": 3,                                          │
│       "estimated_input_tokens": 2150,                                      │
│       "estimated_output_tokens": 890                                        │
│     }                                                                       │
│   }                                                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Environment Variables for Logging Control

| Variable | Default | Description |
|----------|---------|-------------|
| `CC_LOG_FULL_PROMPT` | `false` | Log full prompts (DEBUG level) |
| `CC_LOG_LEVEL_PROMPT` | `DEBUG` | Level for prompt logs (`DEBUG`, `INFO`, `OFF`) |
| `CC_LOG_SAMPLING_RATE` | `1.0` | Fraction of INFO logs to keep (prod: 0.1) |
| `CC_TRACE_ENABLED` | `false` | Enable Cloud Trace spans |

---

## Dashboard Design

### 1. Operations Dashboard (Cloud Monitoring)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CONVERSATION COACH - OPERATIONS                              [Last 1 hour] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────┐ │
│  │  Coaching Requests/min  │  │  Error Rate             │  │  P95 Latency│ │
│  │  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄ │  │  ▁▁▁▁▁▁▂▁▁▁▁▁▁▁▁▁▁▁▁▁   │  │   12.4s    │ │
│  │       23.5 req/min      │  │        0.8%             │  │  ▼ 2.1s    │ │
│  └─────────────────────────┘  └─────────────────────────┘  └─────────────┘ │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  Latency Distribution (ms)                                            │ │
│  │                                                                        │ │
│  │    P50: ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  3,420ms  │ │
│  │    P90: ████████████████████████████████████░░░░░░░░░░░░░░  8,230ms  │ │
│  │    P95: ███████████████████████████████████████████░░░░░░░ 12,400ms  │ │
│  │    P99: ██████████████████████████████████████████████████ 18,900ms  │ │
│  │                                                                        │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────┐ │
│  │  RAG Status                     │  │  Gemini API                     │ │
│  │                                  │  │                                 │ │
│  │  ● RAG Active:     78%          │  │  ● Success Rate: 99.2%         │ │
│  │  ● Fallback:       22%          │  │  ● Avg Latency:  2.8s          │ │
│  │  ● Avg Relevance:  0.72         │  │  ● Tokens/req:   3,040         │ │
│  │                                  │  │                                 │ │
│  └─────────────────────────────────┘  └─────────────────────────────────┘ │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  Recent Errors                                              [View All] │ │
│  │                                                                        │ │
│  │  14:32:15  ERROR  [abc123] Gemini API timeout - conversation conv_456 │ │
│  │  14:28:03  ERROR  [def456] JSON parse error - invalid score value     │ │
│  │                                                                        │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. AI Quality Dashboard (Looker Studio)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CONVERSATION COACH - AI QUALITY                          [Last 7 days]     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Overall Score Trend                                                 │   │
│  │      9 ─┬────────────────────────────────────────────────────────── │   │
│  │      8 ─┤ ····▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄····      │   │
│  │      7 ─┤ ▄▄▄▄                                            ▄▄▄▄      │   │
│  │      6 ─┤                                                           │   │
│  │      5 ─┴────────────────────────────────────────────────────────── │   │
│  │         Mon    Tue    Wed    Thu    Fri    Sat    Sun               │   │
│  │                                                                      │   │
│  │  Mean: 7.6  │  Min: 4.2  │  Max: 9.8  │  StdDev: 1.1               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌────────────────────────────┐  ┌────────────────────────────────────┐   │
│  │  Score Distribution        │  │  Dimension Scores                  │   │
│  │                             │  │                                    │   │
│  │   9-10: ████████░░ 32%     │  │  Empathy:        ████████░░ 7.9   │   │
│  │   7-8:  ████████████ 48%   │  │  Compliance:     █████████░ 8.4   │   │
│  │   5-6:  ████░░░░░░ 15%     │  │  Resolution:     ███████░░░ 7.2   │   │
│  │   1-4:  ██░░░░░░░░  5%     │  │  Professionalism:████████░░ 7.8   │   │
│  │                             │  │  De-escalation: ██████████ 9.1   │   │
│  │                             │  │  Efficiency:     ███████░░░ 7.0   │   │
│  └────────────────────────────┘  └────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Top Coaching Themes (This Week)                                     │   │
│  │                                                                      │   │
│  │  1. Empathy during hardship disclosure ████████████████████ 34%     │   │
│  │  2. Compliance disclosure timing      ████████████░░░░░░░░ 22%     │   │
│  │  3. Payment arrangement clarity       ████████░░░░░░░░░░░░ 18%     │   │
│  │  4. Legal language avoidance          ██████░░░░░░░░░░░░░░ 14%     │   │
│  │  5. Call efficiency                   ████░░░░░░░░░░░░░░░░ 12%     │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌────────────────────────────┐  ┌────────────────────────────────────┐   │
│  │  Call Type Breakdown       │  │  Citations by Policy              │   │
│  │                             │  │                                    │   │
│  │  hardship    ████████ 35%  │  │  POL-002 (Prohibited) ████████ 28%│   │
│  │  payment     ██████░░ 25%  │  │  POL-001 (Compliance) ██████░░ 22%│   │
│  │  complaint   █████░░░ 18%  │  │  POL-004 (Hardship)   █████░░░ 18%│   │
│  │  inquiry     ████░░░░ 15%  │  │  COACH-001 (Playbook) ████░░░░ 15%│   │
│  │  dispute     ██░░░░░░  7%  │  │  Other                ███░░░░░ 17%│   │
│  │                             │  │                                    │   │
│  └────────────────────────────┘  └────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Alerting Strategy

### Alert Tiers

| Tier | Severity | Response Time | Channel | Examples |
|------|----------|---------------|---------|----------|
| P1 - Critical | High | <15 min | PagerDuty + Slack | Service down, >50% error rate |
| P2 - High | Medium | <1 hour | Slack + Email | >10% error rate, latency SLO breach |
| P3 - Medium | Low | <4 hours | Email | Unusual patterns, drift detected |
| P4 - Info | Info | Next business day | Dashboard | Trend notifications |

### Alert Definitions

```yaml
# Cloud Monitoring Alert Policies (YAML format for reference)

# P1: Service Down
- displayName: "Coach - Service Critical Failure"
  conditions:
    - conditionThreshold:
        filter: 'resource.type="cloud_function" AND metric.type="custom.googleapis.com/coach/error_rate"'
        threshold_value: 0.5  # 50%
        duration: 300s  # 5 min
  alertPolicy:
    notificationChannels: [pagerduty, slack-critical]

# P2: High Error Rate
- displayName: "Coach - Elevated Error Rate"
  conditions:
    - conditionThreshold:
        filter: 'metric.type="custom.googleapis.com/coach/error_rate"'
        threshold_value: 0.1  # 10%
        duration: 600s  # 10 min
  alertPolicy:
    notificationChannels: [slack-alerts, email-oncall]

# P2: Latency SLO Breach
- displayName: "Coach - P95 Latency SLO Breach"
  conditions:
    - conditionThreshold:
        filter: 'metric.type="custom.googleapis.com/coach/latency_p95"'
        threshold_value: 30000  # 30 seconds
        duration: 600s
  alertPolicy:
    notificationChannels: [slack-alerts]

# P3: RAG Fallback High
- displayName: "Coach - High RAG Fallback Rate"
  conditions:
    - conditionThreshold:
        filter: 'metric.type="custom.googleapis.com/coach/rag_fallback_rate"'
        threshold_value: 0.3  # 30%
        duration: 1800s  # 30 min
  alertPolicy:
    notificationChannels: [slack-alerts]

# P3: AI Quality Drift
- displayName: "Coach - Score Distribution Drift"
  conditions:
    - conditionAbsent:
        filter: 'metric.type="custom.googleapis.com/coach/avg_score" AND metric.labels.window="1h"'
        aggregations:
          - alignmentPeriod: 3600s
            perSeriesAligner: ALIGN_MEAN
        # Custom drift detection via scheduled query
  alertPolicy:
    notificationChannels: [email-ml-team]
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1-2)

1. **Structured Logging** ✅
   - Add JSON structured logging to all services
   - Implement request correlation IDs
   - Configure log levels and sampling

2. **Cloud Logging Setup**
   - Create log sinks for different log types
   - Configure log retention (90 days default)
   - Set up log-based metrics

3. **Basic Metrics Export**
   - Latency histograms
   - Error counters
   - Request volume

### Phase 2: Dashboards (Week 3)

1. **Operations Dashboard**
   - Cloud Monitoring dashboard with key SRE metrics
   - Error rate and latency charts
   - Service health status

2. **Log Explorer Saved Queries**
   - Common debugging queries
   - Error pattern searches
   - Performance investigation

### Phase 3: Alerting (Week 4)

1. **Alert Policies**
   - P1/P2 critical alerts
   - P3 quality alerts
   - Budget alerts

2. **Notification Channels**
   - Slack integration
   - Email distribution lists
   - Optional: PagerDuty for 24/7

### Phase 4: Analytics (Week 5-6)

1. **BigQuery Analytics Tables**
   - Aggregated metrics tables
   - Scheduled queries for rollups
   - Data retention policies

2. **Looker Studio Dashboards**
   - AI Quality dashboard
   - Business metrics
   - Trend analysis

---

## Cost Considerations

### Monitoring Costs (Estimated)

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| Cloud Logging | 1GB/day ingestion | ~$15/month |
| Cloud Monitoring | 10 custom metrics | ~$10/month |
| Cloud Trace | 100K spans | ~$2/month |
| BigQuery (analytics) | 100GB storage, 1TB queries | ~$25/month |
| **Total** | | **~$50/month** |

### Cost Optimization

1. **Log Sampling**: Sample INFO logs at 10% in production
2. **Metric Aggregation**: Pre-aggregate in app, reduce metric cardinality
3. **Retention Policies**: 30-day logs, 90-day BQ analytics
4. **Query Optimization**: Partition BQ tables by date

---

## Security Considerations

### Data Sensitivity

| Data Type | Handling | Log Level |
|-----------|----------|-----------|
| Conversation transcripts | Never log in full | Excluded |
| Customer PII | Redacted | Excluded |
| Coaching scores | Logged | INFO |
| Model responses | Logged (summary only) | INFO |
| Full prompts | Optional, DEBUG only | DEBUG |
| API keys/credentials | Never logged | Excluded |

### Access Control

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MONITORING ACCESS CONTROL                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Role                      Permissions                                     │
│   ════                      ═══════════                                     │
│                                                                             │
│   monitoring-viewer         • View dashboards                               │
│                             • View metrics                                  │
│                             • View aggregated logs                          │
│                                                                             │
│   monitoring-editor         • All viewer permissions                        │
│                             • Create/edit dashboards                        │
│                             • Create/edit alerts                            │
│                                                                             │
│   monitoring-admin          • All editor permissions                        │
│                             • View detailed logs (incl DEBUG)               │
│                             • Access BQ raw data                            │
│                             • Modify log sinks                              │
│                                                                             │
│   ml-engineer               • All viewer permissions                        │
│                             • Access AI quality metrics                     │
│                             • Access BQ analytics tables                    │
│                             • Run custom queries                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## SLO Definitions

### Service Level Objectives

| SLO | Target | Measurement Window |
|-----|--------|-------------------|
| Availability | 99.5% | Rolling 30 days |
| Latency P95 | <30s | Rolling 7 days |
| Error Rate | <2% | Rolling 7 days |
| RAG Coverage | >80% | Rolling 7 days |

### SLO Burn Rate Alerts

```
Fast Burn:  2% budget consumed in 1 hour  → P1 Alert
Slow Burn:  5% budget consumed in 6 hours → P2 Alert
```

---

## Runbook References

### Common Issues

| Symptom | Check | Action |
|---------|-------|--------|
| High latency | Gemini API status | Check Vertex AI status page |
| High error rate | Recent deployments | Rollback if needed |
| RAG failures | Vertex Search status | Check data store health |
| Score drift | Prompt/model changes | Review recent changes |

### Debug Commands

```bash
# View recent errors
gcloud logging read 'severity=ERROR AND resource.labels.service="conversation-coach"' --limit=50

# Check latency distribution
gcloud monitoring time-series describe custom.googleapis.com/coach/latency_ms

# Query BQ for score trends
bq query 'SELECT DATE(created_at) as date, AVG(overall_score) as avg_score FROM coaching_results WHERE created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) GROUP BY 1 ORDER BY 1'
```

---

## Appendix: Reviewer Q&A

### Q: What metrics do you monitor for an AI system like this?

**A:** Three categories:
1. **Operational**: Latency, errors, throughput - standard SRE metrics
2. **AI Quality**: Score distributions, drift detection, citation rates - ML-specific
3. **Business**: Volume trends, improvement themes, policy usage - stakeholder value

### Q: How do you detect model degradation?

**A:**
1. **Statistical drift detection**: Compare score distributions over time windows
2. **Citation rate monitoring**: If RAG-enabled but low citations, model may be ignoring context
3. **Coaching point analysis**: Track themes to detect if model output is becoming repetitive
4. **A/B comparison**: When updating prompts/models, compare quality metrics

### Q: How do you handle PII in logs?

**A:**
1. **Never log transcripts** in production
2. **Structured logging** with explicit field allowlists
3. **Sampling** reduces exposure
4. **Access controls** limit who sees DEBUG logs
5. **Retention policies** auto-delete sensitive data

### Q: What's your incident response for AI failures?

**A:**
1. **Detection**: Automated alerts within 5 minutes
2. **Triage**: Request correlation IDs enable quick root cause
3. **Mitigation**: RAG fallback to embedded policy ensures graceful degradation
4. **Recovery**: Model/prompt rollback capability via version tracking
