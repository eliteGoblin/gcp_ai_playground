# Conversation Coach: AI System Monitoring Design

## Philosophy

**Don't monitor "the model" — monitor the AI SYSTEM in your production context.**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CORE PRINCIPLE                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   "You don't test an engine alone; you test the whole car on your roads."  │
│                                                                             │
│   • Engine = Model (Gemini)           → Google monitors this               │
│   • Car = AI System (our app)         → WE monitor this                    │
│   • Roads = Our users, data, context  → WE monitor this                    │
│                                                                             │
│   The AI System = Prompt + RAG + Guardrails + Data + Users + Model         │
│                                                                             │
│   Most failures happen OUTSIDE the model:                                   │
│   • Bad input data         (~60% of issues)                                │
│   • Poor RAG retrieval     (~20% of issues)                                │
│   • Prompt problems        (~15% of issues)                                │
│   • Model issues           (~5% of issues) ← Google handles these          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Table of Contents

1. [MVP Scope](#1-mvp-scope)
2. [AI System Layers](#2-ai-system-layers)
3. [MVP Metrics](#3-mvp-metrics)
4. [MVP Implementation](#4-mvp-implementation)
5. [Distributed Tracing (OpenTelemetry + ADK)](#5-distributed-tracing-opentelemetry--adk)
6. [Non-MVP (Deferred)](#6-non-mvp-deferred)

---

## 1. MVP Scope

### What's In vs Out

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MVP SCOPE DEFINITION                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ✅ MVP (Implement Now)                ❌ NON-MVP (Defer)                  │
│   ══════════════════════                ════════════════════                │
│                                                                             │
│   • Structured logging                  • Drift detection                  │
│   • End-to-end success rate             • Golden dataset testing           │
│   • Error alerting (P1/P2)              • LLM observability tools          │
│   • Basic latency tracking              • Prompt management UI             │
│   • Cost visibility (daily)             • Evaluation frameworks            │
│   • Component health checks             • Advanced FinOps                  │
│                                         • Business outcome dashboards      │
│                                         • Multi-agent tracing              │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   MVP GOAL:                                                                 │
│   "Know when the system is broken and where to look"                       │
│                                                                             │
│   NOT MVP GOAL:                                                             │
│   "Optimize every component" or "Catch subtle quality degradation"         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### MVP Success Criteria

| Criteria | Metric | Target |
|----------|--------|--------|
| **Detection** | Time to detect P1 issue | < 5 minutes |
| **Diagnosis** | Time to identify failing component | < 15 minutes |
| **Coverage** | % of requests with trace | 100% |
| **Cost** | Know daily spend | ± 10% accuracy |

---

## 2. AI System Layers

### Complete System View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              CONVERSATION COACH: AI SYSTEM LAYERS                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Layer 6: BUSINESS OUTCOME                              ❌ NON-MVP         │
│   ═══════════════════════════════════════════════════════════════════════  │
│   │ Agent improvement over time, compliance reduction, ROI                │  │
│   └───────────────────────────────────────────────────────────────────────│  │
│                                     ▲                                       │
│   Layer 5: OUTPUT QUALITY                                ⚠️ BASIC MVP      │
│   ═══════════════════════════════════════════════════════════════════════  │
│   │ Score distribution variance, parse success rate                       │  │
│   └───────────────────────────────────────────────────────────────────────│  │
│                                     ▲                                       │
│   Layer 4: APPLICATION (RED)                             ✅ MVP            │
│   ═══════════════════════════════════════════════════════════════════════  │
│   │ E2E success rate, error rate, latency                                 │  │
│   └───────────────────────────────────────────────────────────────────────│  │
│                                     ▲                                       │
│   Layer 3: COMPONENT HEALTH                              ✅ MVP            │
│   ═══════════════════════════════════════════════════════════════════════  │
│   │ Data → RAG → Prompt → Model Call → Output Parse → Storage             │  │
│   └───────────────────────────────────────────────────────────────────────│  │
│                                     ▲                                       │
│   Layer 2: DATA PIPELINE                                 ⚠️ BASIC MVP      │
│   ═══════════════════════════════════════════════════════════════════════  │
│   │ Input validation, CI enrichment health                                │  │
│   └───────────────────────────────────────────────────────────────────────│  │
│                                     ▲                                       │
│   Layer 1: INFRASTRUCTURE                                ✅ MVP (Auto)     │
│   ═══════════════════════════════════════════════════════════════════════  │
│   │ GCP auto-collects: CPU, memory, API quotas                            │  │
│   └───────────────────────────────────────────────────────────────────────│  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Health (Layer 3) - MVP Focus

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              COMPONENT HEALTH: WHERE FAILURES ACTUALLY HAPPEN                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Request Flow:                                                             │
│                                                                             │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐            │
│   │   DATA   │───▶│   RAG    │───▶│  MODEL   │───▶│  OUTPUT  │            │
│   │  FETCH   │    │ RETRIEVE │    │   CALL   │    │  PARSE   │            │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘            │
│        │               │               │               │                   │
│        ▼               ▼               ▼               ▼                   │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐            │
│   │ Monitor: │    │ Monitor: │    │ Monitor: │    │ Monitor: │            │
│   │ • Found? │    │ • Docs   │    │ • Latency│    │ • Valid  │            │
│   │ • Valid? │    │   found? │    │ • Errors │    │   JSON?  │            │
│   │ • Fresh? │    │ • Score? │    │ • Tokens │    │ • Schema?│            │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘            │
│                                                                             │
│   EACH COMPONENT LOGS:                                                      │
│   • success: bool                                                          │
│   • duration_ms: int                                                       │
│   • error_type: string (if failed)                                         │
│   • component_specific_metrics: dict                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. MVP Metrics

### Primary Metric: End-to-End Success Rate

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              PRIMARY METRIC: E2E SUCCESS RATE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   DEFINITION:                                                               │
│   ────────────                                                              │
│   E2E Success = Request received AND coaching stored in BQ successfully    │
│                                                                             │
│   success_rate = successful_coachings / total_requests                     │
│                                                                             │
│   TARGET: > 95%                                                             │
│   ALERT:  < 90% for 10 minutes → P2                                        │
│           < 50% for 5 minutes  → P1                                        │
│                                                                             │
│   WHY THIS METRIC:                                                          │
│   ─────────────────                                                         │
│   • Captures ALL failure modes (data, RAG, model, parsing, storage)        │
│   • User-centric (did they get their coaching?)                            │
│   • Simple to understand and explain                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### MVP Metrics Table

| Layer | Metric | MVP? | Alert | Source |
|-------|--------|------|-------|--------|
| **Application** | `e2e_success_rate` | ✅ | <90% | Custom |
| **Application** | `e2e_error_rate` | ✅ | >10% | Custom |
| **Application** | `e2e_latency_p95` | ✅ | >30s | Custom |
| **Component** | `data_fetch_success` | ✅ | <95% | Logging |
| **Component** | `rag_retrieval_success` | ✅ | <90% | Logging |
| **Component** | `model_call_success` | ✅ | <95% | Logging |
| **Component** | `output_parse_success` | ✅ | <95% | Logging |
| **Cost** | `daily_cost_estimate` | ✅ | >$50 | Calculated |
| **Quality** | `output_schema_valid` | ⚠️ Basic | <90% | Logging |
| **Quality** | `score_variance` | ⚠️ Basic | <0.5 | BQ Query |
| **Business** | `coaching_per_day` | ❌ Non-MVP | - | BQ |
| **Business** | `score_by_team` | ❌ Non-MVP | - | BQ |

### Component-Level Health Checks

```python
# What each component logs (MVP)

# 1. Data Fetch
{
    "component": "data_fetch",
    "success": true,
    "duration_ms": 450,
    "ci_data_found": true,
    "registry_found": true,
    "conversation_id": "xxx"
}

# 2. RAG Retrieval
{
    "component": "rag_retrieval",
    "success": true,
    "duration_ms": 1200,
    "topics_extracted": ["hardship", "compliance"],
    "docs_retrieved": 3,
    "top_relevance_score": 0.82,
    "fallback_used": false
}

# 3. Model Call
{
    "component": "model_call",
    "success": true,
    "duration_ms": 5400,
    "model": "gemini-1.5-flash-002",
    "input_tokens": 2150,
    "output_tokens": 890,
    "error": null
}

# 4. Output Parse
{
    "component": "output_parse",
    "success": true,
    "duration_ms": 50,
    "json_valid": true,
    "schema_valid": true,
    "scores_in_range": true
}
```

---

## 4. MVP Implementation

### Implementation Checklist

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              MVP IMPLEMENTATION CHECKLIST                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   WEEK 1: Structured Logging                                               │
│   ══════════════════════════                                               │
│   □ Add request_id to all logs (correlation)                               │
│   □ Log component success/failure at each step                             │
│   □ Log duration_ms for each component                                     │
│   □ JSON structured format for Cloud Logging                               │
│                                                                             │
│   WEEK 2: Metrics & Alerts                                                 │
│   ════════════════════════                                                 │
│   □ Create log-based metric: e2e_success_rate                              │
│   □ Create log-based metric: e2e_error_rate                                │
│   □ Create P1 alert: error_rate > 50%                                      │
│   □ Create P2 alert: error_rate > 10%                                      │
│   □ Create P2 alert: latency_p95 > 30s                                     │
│                                                                             │
│   WEEK 3: Cost & Dashboard                                                 │
│   ════════════════════════                                                 │
│   □ Enable billing export to BQ                                            │
│   □ Add token counting to model call logs                                  │
│   □ Create basic Cloud Monitoring dashboard                                │
│   □ Add cost alert: daily > $50                                            │
│                                                                             │
│   DONE CRITERIA:                                                            │
│   ───────────────                                                           │
│   • Can answer: "Is the system working?" in < 1 minute                     │
│   • Can answer: "What component failed?" in < 5 minutes                    │
│   • Get alerted automatically on P1/P2 issues                              │
│   • Know yesterday's cost                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Code: Structured Logging (MVP)

```python
# cc_coach/monitoring/logging.py

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Optional
from contextlib import contextmanager
import time

# Request context for correlation
request_id_ctx: ContextVar[str] = ContextVar('request_id', default='')

class ComponentLogger:
    """Structured logging for AI system components."""

    def __init__(self, service: str = "conversation-coach"):
        self.service = service
        self.logger = logging.getLogger(service)

    @contextmanager
    def component(self, name: str, **context):
        """Log component execution with timing."""
        start = time.time()
        result = {"success": False, "error": None}

        try:
            yield result
            result["success"] = True
        except Exception as e:
            result["error"] = str(e)
            result["error_type"] = type(e).__name__
            raise
        finally:
            duration_ms = int((time.time() - start) * 1000)
            self._log_component(name, duration_ms, result, context)

    def _log_component(self, component: str, duration_ms: int,
                       result: dict, context: dict):
        entry = {
            "severity": "ERROR" if result.get("error") else "INFO",
            "message": f"Component: {component}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "labels": {
                "service": self.service,
                "component": component,
            },
            "logging.googleapis.com/trace": request_id_ctx.get(),
            "jsonPayload": {
                "component": component,
                "success": result["success"],
                "duration_ms": duration_ms,
                "error": result.get("error"),
                "error_type": result.get("error_type"),
                **context
            }
        }
        self.logger.log(
            logging.ERROR if result.get("error") else logging.INFO,
            json.dumps(entry)
        )

    def log_e2e_result(self, conversation_id: str, success: bool,
                       total_duration_ms: int, error: Optional[str] = None):
        """Log end-to-end coaching result."""
        entry = {
            "severity": "ERROR" if not success else "INFO",
            "message": "E2E coaching result",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "labels": {
                "service": self.service,
                "component": "e2e",
            },
            "logging.googleapis.com/trace": request_id_ctx.get(),
            "jsonPayload": {
                "component": "e2e",
                "conversation_id": conversation_id,
                "success": success,
                "duration_ms": total_duration_ms,
                "error": error
            }
        }
        self.logger.log(
            logging.ERROR if not success else logging.INFO,
            json.dumps(entry)
        )

def new_request_context() -> str:
    """Start new request with correlation ID."""
    request_id = str(uuid.uuid4())
    request_id_ctx.set(request_id)
    return request_id
```

### Code: Instrumented Coaching Service (MVP)

```python
# cc_coach/services/coaching.py (instrumented version)

from cc_coach.monitoring.logging import ComponentLogger, new_request_context
import time

class CoachingOrchestrator:
    def __init__(self, ...):
        self.logger = ComponentLogger()
        # ... existing init

    def generate_coaching(self, conversation_id: str) -> CoachingOutput:
        """Generate coaching with component-level monitoring."""

        request_id = new_request_context()
        start_time = time.time()

        try:
            # Component 1: Data Fetch
            with self.logger.component("data_fetch",
                                       conversation_id=conversation_id) as result:
                ci_data = self._fetch_ci_enrichment(conversation_id)
                registry_data = self._fetch_registry(conversation_id)
                result["ci_found"] = ci_data is not None
                result["registry_found"] = registry_data is not None

                if not ci_data:
                    raise ValueError(f"No CI data for {conversation_id}")

            # Component 2: Input Processing
            with self.logger.component("input_processing") as result:
                input_data = self._build_coaching_input(
                    conversation_id, ci_data, registry_data
                )
                result["turn_count"] = len(input_data.turns)

            # Component 3: RAG Retrieval
            with self.logger.component("rag_retrieval") as result:
                rag_context, retrieved_docs = self._get_rag_context(
                    conversation_id, ci_data, input_data.turns, registry_data
                )
                result["docs_retrieved"] = len(retrieved_docs)
                result["fallback_used"] = not rag_context and self.allow_fallback
                result["topics"] = self.last_extracted_topics if hasattr(self, 'last_extracted_topics') else []

            # Component 4: Model Call
            with self.logger.component("model_call",
                                       model=self.coach.model) as result:
                output = self.coach.analyze_conversation(
                    input_data,
                    rag_context=rag_context,
                    allow_fallback=self.allow_fallback,
                )
                result["input_tokens"] = getattr(output, 'input_tokens', 0)
                result["output_tokens"] = getattr(output, 'output_tokens', 0)

            # Component 5: Output Processing
            with self.logger.component("output_processing") as result:
                if retrieved_docs:
                    output.citations = [doc.to_citation() for doc in retrieved_docs]
                    output.rag_context_used = True
                result["schema_valid"] = True  # Would have raised if invalid
                result["scores_in_range"] = 1 <= output.overall_score <= 10

            # Component 6: Storage
            with self.logger.component("storage") as result:
                self._store_coaching_result(
                    conversation_id, output, registry_data, ci_data, retrieved_docs
                )
                self._update_registry_status(conversation_id, "COACHED")
                result["stored"] = True

            # Log E2E success
            total_duration = int((time.time() - start_time) * 1000)
            self.logger.log_e2e_result(
                conversation_id,
                success=True,
                total_duration_ms=total_duration
            )

            return output

        except Exception as e:
            # Log E2E failure
            total_duration = int((time.time() - start_time) * 1000)
            self.logger.log_e2e_result(
                conversation_id,
                success=False,
                total_duration_ms=total_duration,
                error=str(e)
            )
            raise
```

### Cloud Monitoring: Log-Based Metrics (MVP)

```yaml
# Create via gcloud or Terraform

# Metric 1: E2E Success Rate
- name: "projects/PROJECT/metricDescriptors/custom.googleapis.com/coach/e2e_success"
  filter: |
    resource.type="cloud_run_revision"
    jsonPayload.component="e2e"
  labelExtractors:
    success: EXTRACT(jsonPayload.success)
  metricKind: DELTA
  valueType: INT64

# Metric 2: Component Errors
- name: "projects/PROJECT/metricDescriptors/custom.googleapis.com/coach/component_errors"
  filter: |
    resource.type="cloud_run_revision"
    severity="ERROR"
    jsonPayload.component!=""
  labelExtractors:
    component: EXTRACT(jsonPayload.component)
    error_type: EXTRACT(jsonPayload.error_type)
  metricKind: DELTA
  valueType: INT64

# Metric 3: Latency by Component
- name: "projects/PROJECT/metricDescriptors/custom.googleapis.com/coach/component_latency"
  filter: |
    resource.type="cloud_run_revision"
    jsonPayload.duration_ms>0
  labelExtractors:
    component: EXTRACT(jsonPayload.component)
  valueExtractor: EXTRACT(jsonPayload.duration_ms)
  metricKind: GAUGE
  valueType: INT64
```

### Alert Policies (MVP)

```yaml
# P1: System Down
- displayName: "Coach - P1 - System Down"
  conditions:
    - displayName: "E2E error rate > 50%"
      conditionThreshold:
        filter: 'metric.type="custom.googleapis.com/coach/e2e_success"'
        comparison: COMPARISON_LT
        thresholdValue: 0.5
        duration: 300s  # 5 minutes
        aggregations:
          - alignmentPeriod: 60s
            perSeriesAligner: ALIGN_RATE
  alertStrategy:
    notificationChannels: ["slack-critical", "pagerduty"]

# P2: Degraded
- displayName: "Coach - P2 - Degraded Performance"
  conditions:
    - displayName: "E2E error rate > 10%"
      conditionThreshold:
        filter: 'metric.type="custom.googleapis.com/coach/e2e_success"'
        comparison: COMPARISON_LT
        thresholdValue: 0.9
        duration: 600s  # 10 minutes
  alertStrategy:
    notificationChannels: ["slack-alerts"]

# P2: Latency
- displayName: "Coach - P2 - High Latency"
  conditions:
    - displayName: "P95 latency > 30s"
      conditionThreshold:
        filter: 'metric.type="custom.googleapis.com/coach/component_latency" AND metric.labels.component="e2e"'
        comparison: COMPARISON_GT
        thresholdValue: 30000
        duration: 600s
  alertStrategy:
    notificationChannels: ["slack-alerts"]

# P4: Cost
- displayName: "Coach - P4 - Cost Warning"
  conditions:
    - displayName: "Daily cost > $50"
      # Use billing export to BQ + scheduled query
  alertStrategy:
    notificationChannels: ["email"]
```

### Dashboard Layout (MVP)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CONVERSATION COACH - SYSTEM HEALTH                         [Last 1 hour]   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────┐  ┌─────────────────────────┐                  │
│  │  E2E SUCCESS RATE       │  │  REQUESTS / MIN         │                  │
│  │  ██████████████████░░   │  │  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄  │                  │
│  │       94.2%             │  │       12.3 req/min      │                  │
│  └─────────────────────────┘  └─────────────────────────┘                  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  COMPONENT HEALTH                                                      │ │
│  │                                                                        │ │
│  │  data_fetch      ████████████████████████████████████████░ 98%        │ │
│  │  rag_retrieval   █████████████████████████████████████░░░░ 92%        │ │
│  │  model_call      ████████████████████████████████████████░ 97%        │ │
│  │  output_parse    ████████████████████████████████████████░ 99%        │ │
│  │  storage         ████████████████████████████████████████░ 99%        │ │
│  │                                                                        │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  LATENCY BY COMPONENT (P95)                                           │ │
│  │                                                                        │ │
│  │  data_fetch      ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    450ms  │ │
│  │  rag_retrieval   █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  1,200ms  │ │
│  │  model_call      █████████████████████████████████░░░░░░░░  5,400ms  │ │
│  │  output_parse    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     50ms  │ │
│  │  storage         █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░    300ms  │ │
│  │  ────────────────────────────────────────────────────────            │ │
│  │  TOTAL E2E       █████████████████████████████████████████  7,400ms  │ │
│  │                                                                        │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────┐ │
│  │  RECENT ERRORS                  │  │  TODAY'S COST                   │ │
│  │                                  │  │                                 │ │
│  │  14:32 model_call: timeout      │  │  Gemini:     $2.40              │ │
│  │  14:28 rag: no docs found       │  │  Vertex:     $0.80              │ │
│  │  14:15 data: CI not found       │  │  BigQuery:   $0.15              │ │
│  │                                  │  │  ─────────────────              │ │
│  │                      [View All] │  │  Total:      $3.35              │ │
│  └─────────────────────────────────┘  └─────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Distributed Tracing (OpenTelemetry + ADK)

### Overview

Real distributed tracing using OpenTelemetry, leveraging ADK's built-in instrumentation plus custom spans for business logic.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              DISTRIBUTED TRACING ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   DESIGN DECISION: DIRECT EXPORT (No Collector)                            │
│   ═════════════════════════════════════════════                            │
│                                                                             │
│   ┌─────────────────┐                      ┌─────────────────┐             │
│   │  Your App       │                      │  Cloud Trace    │             │
│   │  ┌───────────┐  │   OTLP/HTTP          │                 │             │
│   │  │ ADK Auto  │──┼──────────────────────▶│  Trace Storage  │             │
│   │  │ Spans     │  │                      │  & Visualization│             │
│   │  ├───────────┤  │   Direct Export      │                 │             │
│   │  │ Custom    │──┼──────────────────────▶│  (No Collector  │             │
│   │  │ Spans     │  │   (Fire & Forget)    │   Required!)    │             │
│   │  └───────────┘  │                      │                 │             │
│   └─────────────────┘                      └─────────────────┘             │
│                                                                             │
│   WHY NO COLLECTOR:                                                        │
│   • Single backend (Cloud Trace only)                                      │
│   • ADK uses BatchSpanProcessor (buffers internally)                       │
│   • Less infrastructure to manage                                          │
│   • Works identically: Local → Cloud Run → ADK Engine                      │
│                                                                             │
│   WHEN TO ADD COLLECTOR:                                                   │
│   • Multiple backends (Jaeger + Cloud Trace + Datadog)                     │
│   • Complex sampling rules                                                 │
│   • Very high volume (>10K traces/sec)                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Trace Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              TRACE STRUCTURE: ACTUAL IMPLEMENTATION                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   WATERFALL VISUALIZATION (Real trace from Cloud Trace):                   │
│                                                                             │
│   e2e_coaching       │████████████████████████████████████████│  35,711ms  │
│   ├─data_fetch       │███·····································│   3,546ms  │
│   ├─input_processing │···█····································│      92ms  │
│   ├─rag_retrieval    │····█···································│      88ms  │
│   ├─model_call       │····███████████████████████████████·····│  28,438ms  │ ← 80%
│   ├─output_processing│····································█···│     101ms  │
│   └─storage          │····································███·│   3,374ms  │
│                                                                             │
│   SPAN ATTRIBUTES (Real data from verified traces):                        │
│   ───────────────────────────────────────────────────────────────────────  │
│   e2e_coaching:       conversation_id, request_id, success, duration_ms    │
│   data_fetch:         ci_found=true, registry_found=true                   │
│   input_processing:   turn_count=27                                        │
│   rag_retrieval:      rag_enabled=false, fallback_used=true, docs=0       │
│   model_call:         model=gemini-2.5-flash, cost_usd=0.0008,             │
│                       gen_ai.usage.input_tokens=3274, output_tokens=1914   │
│   output_processing:  overall_score=8.6, coaching_points_count=1           │
│   storage:            stored=true                                          │
│                                                                             │
│   CONTEXT PROPAGATION:                                                      │
│   All spans share the same trace_id via Python ContextVar                  │
│   start_as_current_span() automatically sets parent_span_id                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Required IAM Roles

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              IAM ROLES FOR CLOUD TRACE                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ROLE                        PURPOSE                                       │
│   ────                        ───────                                       │
│   roles/cloudtrace.agent      Write traces (required for export)           │
│   roles/cloudtrace.user       Read traces (for verification/querying)      │
│                                                                             │
│   GRANT COMMANDS:                                                           │
│   ───────────────                                                           │
│   gcloud projects add-iam-policy-binding PROJECT_ID \                      │
│     --member="serviceAccount:SA_EMAIL" \                                   │
│     --role="roles/cloudtrace.agent"                                        │
│                                                                             │
│   gcloud projects add-iam-policy-binding PROJECT_ID \                      │
│     --member="serviceAccount:SA_EMAIL" \                                   │
│     --role="roles/cloudtrace.user"                                         │
│                                                                             │
│   CLOUD RUN: Default service account usually has these roles               │
│   LOCAL DEV: Service account key needs roles granted explicitly            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation

#### Step 1: Setup OTEL with Cloud Trace Export

```python
# cc_coach/monitoring/tracing.py

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
import os

def setup_tracing(
    service_name: str = "conversation-coach",
    enable_cloud_trace: bool = True,
) -> trace.Tracer:
    """Setup OpenTelemetry tracing with Cloud Trace export.

    Works in all environments:
    - Local: Uses service account credentials (GOOGLE_APPLICATION_CREDENTIALS)
    - Cloud Run: Uses default credentials automatically
    - ADK Engine: Uses platform credentials
    """

    # Create resource with service info
    resource = Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("SERVICE_VERSION", "dev"),
    })

    # Setup provider
    provider = TracerProvider(resource=resource)

    if enable_cloud_trace:
        # Use native Cloud Trace exporter (works with service account key)
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
        if not project_id:
            # Try to get from credentials file
            creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_file:
                import json
                with open(creds_file) as f:
                    creds = json.load(f)
                    project_id = creds.get("project_id")

        exporter = CloudTraceSpanExporter(project_id=project_id)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


# Global tracer instance
_tracer: trace.Tracer = None

def get_tracer() -> trace.Tracer:
    """Get or create the global tracer."""
    global _tracer
    if _tracer is None:
        _tracer = setup_tracing()
    return _tracer

def shutdown_tracing():
    """Shutdown tracing and flush any pending spans."""
    # Call this on exit to ensure traces are exported
    if _provider is not None:
        _provider.shutdown()
```

#### Step 2: Instrument Business Logic

```python
# cc_coach/services/coaching.py (with tracing)

from opentelemetry import trace
from cc_coach.monitoring.tracing import get_tracer

class CoachingOrchestrator:

    def __init__(self, ...):
        self.tracer = get_tracer()
        # ... existing init

    def generate_coaching(self, conversation_id: str) -> CoachingOutput:
        """Generate coaching with distributed tracing."""

        # Root span for entire operation
        with self.tracer.start_as_current_span("e2e_coaching") as root_span:
            root_span.set_attribute("conversation_id", conversation_id)

            try:
                # Custom span: Data Fetch
                with self.tracer.start_as_current_span("data_fetch") as span:
                    span.set_attribute("conversation_id", conversation_id)
                    ci_data = self._fetch_ci_enrichment(conversation_id)
                    registry_data = self._fetch_registry(conversation_id)
                    span.set_attribute("ci_found", ci_data is not None)

                # Custom span: Input Processing
                with self.tracer.start_as_current_span("input_processing"):
                    input_data = self._build_coaching_input(...)

                # Custom span: RAG Retrieval
                with self.tracer.start_as_current_span("rag_retrieval") as span:
                    rag_context, docs = self._get_rag_context(...)
                    span.set_attribute("docs_retrieved", len(docs))

                # ADK auto-creates spans here (call_llm, etc.)
                # They become children of current span automatically!
                output = self.coach.analyze_conversation(input_data, ...)

                # Custom span: Output Processing
                with self.tracer.start_as_current_span("output_processing"):
                    # ... validate output
                    pass

                # Custom span: Storage
                with self.tracer.start_as_current_span("storage") as span:
                    self._store_coaching_result(...)
                    span.set_attribute("stored", True)

                root_span.set_attribute("success", True)
                return output

            except Exception as e:
                root_span.set_attribute("success", False)
                root_span.set_attribute("error", str(e))
                root_span.record_exception(e)
                raise
```

#### Step 3: Environment Configuration

```bash
# Local development
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/service-account-key.json
export OTEL_SERVICE_NAME=conversation-coach
export CC_ENABLE_TRACING=true

# Cloud Run (automatic - uses default service account)
# No additional config needed

# ADK Engine (use --trace_to_cloud flag)
adk deploy agent_engine --trace_to_cloud
```

### Deployment Configurations

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              TRACING BY DEPLOYMENT ENVIRONMENT                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   LOCAL DEVELOPMENT                                                        │
│   ═════════════════                                                        │
│   ┌─────────────────┐    OTLP/HTTP     ┌─────────────────┐                │
│   │  cc-coach CLI   │─────────────────▶│  Cloud Trace    │                │
│   │                 │                   │  (GCP)          │                │
│   │  Service Acct   │                   │                 │                │
│   │  Credentials    │                   └─────────────────┘                │
│   └─────────────────┘                                                      │
│                                                                             │
│   Config: GOOGLE_APPLICATION_CREDENTIALS + CC_ENABLE_TRACING=true          │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   CLOUD RUN                                                                │
│   ═════════                                                                │
│   ┌─────────────────┐    OTLP/HTTP     ┌─────────────────┐                │
│   │  Cloud Run      │─────────────────▶│  Cloud Trace    │                │
│   │  Service        │                   │  (GCP)          │                │
│   │                 │                   │                 │                │
│   │  Default SA     │                   │  Auto-linked    │                │
│   │  (automatic)    │                   │  to project     │                │
│   └─────────────────┘                   └─────────────────┘                │
│                                                                             │
│   Config: Just deploy - credentials automatic                              │
│   Bonus: Cloud Run adds X-Cloud-Trace-Context header automatically         │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   ADK ENGINE (Vertex AI Agent Builder)                                     │
│   ════════════════════════════════════                                     │
│   ┌─────────────────┐    Built-in      ┌─────────────────┐                │
│   │  ADK Agent      │─────────────────▶│  Cloud Trace    │                │
│   │  Engine         │                   │  (GCP)          │                │
│   │                 │                   │                 │                │
│   │  --trace_to_    │                   │  Full agent     │                │
│   │  cloud flag     │                   │  telemetry      │                │
│   └─────────────────┘                   └─────────────────┘                │
│                                                                             │
│   Config: adk deploy agent_engine --trace_to_cloud                         │
│   Alternative: enable_tracing=True in AdkApp()                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Viewing Traces

```bash
# Option 1: GCP Console
https://console.cloud.google.com/traces/list?project=PROJECT_ID

# Option 2: gcloud CLI
gcloud trace traces list --project=PROJECT_ID

# Option 3: Query specific trace
gcloud trace traces describe TRACE_ID --project=PROJECT_ID
```

### OTEL Semantic Conventions for GenAI

ADK follows OpenTelemetry GenAI semantic conventions:

| Attribute | Description | Example |
|-----------|-------------|---------|
| `gen_ai.system` | AI system identifier | `gcp.vertex.agent` |
| `gen_ai.request.model` | Model used | `gemini-2.0-flash` |
| `gen_ai.usage.input_tokens` | Input tokens | `2150` |
| `gen_ai.usage.output_tokens` | Output tokens | `890` |
| `gen_ai.response.finish_reasons` | Why generation stopped | `["stop"]` |
| `gen_ai.operation.name` | Operation type | `invoke_agent`, `call_llm` |
| `gen_ai.conversation.id` | Session/conversation ID | `session-123` |

### Tracing + Logging Correlation

```python
# Correlate traces with logs using trace_id

import logging
from opentelemetry import trace

def log_with_trace(message: str, **kwargs):
    """Log with trace context for correlation."""
    span = trace.get_current_span()
    ctx = span.get_span_context()

    # Add trace context to log
    extra = {
        "trace_id": format(ctx.trace_id, '032x'),
        "span_id": format(ctx.span_id, '016x'),
        **kwargs
    }

    logging.info(message, extra=extra)
```

Cloud Logging query to find logs for a trace:
```
trace="projects/PROJECT_ID/traces/TRACE_ID"
```

### Cost Considerations

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              CLOUD TRACE PRICING                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   FREE TIER (per month):                                                   │
│   • First 2.5 million spans ingested: FREE                                 │
│   • First 50 million spans scanned: FREE                                   │
│                                                                             │
│   BEYOND FREE TIER:                                                        │
│   • $0.20 per million spans ingested                                       │
│   • $0.02 per million spans scanned                                        │
│                                                                             │
│   ESTIMATION FOR CONVERSATION COACH:                                       │
│   ─────────────────────────────────                                        │
│   • ~7 spans per coaching request                                          │
│   • 100 requests/day = 700 spans/day = 21,000 spans/month                 │
│   • Well within free tier                                                  │
│                                                                             │
│   SAMPLING (if needed for high volume):                                    │
│   ─────────────────────────────────────                                    │
│   from opentelemetry.sdk.trace.sampling import TraceIdRatioBased           │
│   sampler = TraceIdRatioBased(0.1)  # Sample 10% of traces                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Summary: Tracing Implementation

| Question | Answer |
|----------|--------|
| **Need OTEL SDK?** | No - ADK includes it |
| **Need Collector?** | No - direct export to Cloud Trace |
| **Need GCP infra?** | No - Cloud Trace already enabled |
| **App changes?** | ~50 lines for custom spans |
| **Works in prod?** | Yes - same code for local/Cloud Run/ADK Engine |

---

## 6. Non-MVP (Deferred)

### Items NOT Implementing

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              NON-MVP: EXPLICITLY NOT IMPLEMENTING                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   DRIFT DETECTION                                          Status: DEFER   │
│   ═══════════════                                                           │
│   What: Statistical detection of model output distribution changes          │
│   Why defer:                                                               │
│   • Pinned model version mitigates biggest risk                            │
│   • Low volume - not enough data for statistical significance              │
│   • Basic variance check (stddev < 0.5) covers 80% of issues               │
│   When to reconsider: Volume > 100/day, unpinning model                    │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   LLM OBSERVABILITY TOOLS (Langfuse/Opik)                  Status: DEFER   │
│   ═══════════════════════════════════════                                   │
│   What: Specialized prompt management, LLM tracing, evals                  │
│   Why defer:                                                               │
│   • Single LLM call per request - low complexity                           │
│   • Prompt changes infrequent                                              │
│   • GCP native sufficient for MVP monitoring                               │
│   When to reconsider: Complex multi-agent, frequent prompt iteration       │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   GOLDEN DATASET TESTING                                   Status: DEFER   │
│   ══════════════════════                                                    │
│   What: Fixed test set for regression detection                            │
│   Why defer: Requires test data curation, eval framework                   │
│   When to reconsider: After prompt/model changes cause issues              │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   BUSINESS OUTCOME DASHBOARDS                              Status: DEFER   │
│   ═══════════════════════════                                               │
│   What: Agent improvement trends, ROI tracking                             │
│   Why defer: Need production usage first, stakeholder requirements         │
│   When to reconsider: Production rollout, executive reporting needs        │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   ADVANCED FINOPS                                          Status: DEFER   │
│   ═══════════════                                                           │
│   What: Forecasting, rightsizing, optimization recommendations             │
│   Why defer: Basic cost visibility sufficient for MVP scale                │
│   When to reconsider: Monthly spend > $1000                                │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   DISTRIBUTED TRACING VISUALIZATION                        Status: ✅ DONE │
│   ═════════════════════════════════                                         │
│   Implemented: OpenTelemetry + ADK auto-spans + Cloud Trace                │
│   See: Section 5 - Distributed Tracing                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Future Architecture (When Non-MVP Needed)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              FUTURE STATE: WHEN TO ADD WHAT                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   TRIGGER                          ADD                                      │
│   ───────                          ───                                      │
│                                                                             │
│   Volume > 100/day                 → Drift detection                       │
│   Complex multi-agent flows        → Langfuse/Opik                         │
│   Frequent prompt changes          → Prompt management tool                │
│   Debugging takes > 30 min         → Enhanced tracing                      │
│   Monthly spend > $1000            → Advanced FinOps                       │
│   Executive reporting needs        → Business dashboards                   │
│   Model/prompt change issues       → Golden dataset testing                │
│   Self-hosted LLM                  → GPU monitoring layer                  │
│                                                                             │
│   ARCHITECTURE EVOLUTION:                                                   │
│   ───────────────────────                                                   │
│                                                                             │
│   MVP          →    Scale           →    Enterprise                        │
│   ───              ─────                 ──────────                         │
│   GCP Native       + OpenTelemetry      + Self-hosted                      │
│   Logging          + LLM tool           + Langfuse/Opik                    │
│   Basic alerts     + Drift detection    + Golden datasets                  │
│   Cost visibility  + Advanced FinOps    + Business dashboards              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              MONITORING DESIGN SUMMARY                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   PHILOSOPHY:                                                               │
│   Monitor the AI SYSTEM, not just the model                                │
│   (The car on your roads, not the engine alone)                            │
│                                                                             │
│   IMPLEMENTED:                                                              │
│   ✅ Structured component logging (local + Cloud Logging)                  │
│   ✅ E2E success rate as primary metric                                    │
│   ✅ Log-based metrics (10 metrics in Cloud Monitoring)                    │
│   ✅ Basic cost visibility                                                 │
│   ✅ Component health dashboard                                            │
│   ✅ Distributed tracing (OpenTelemetry + ADK + Cloud Trace)               │
│                                                                             │
│   TRACING ARCHITECTURE:                                                    │
│   • Direct export to Cloud Trace (no collector needed)                     │
│   • ADK auto-instruments: invoke_agent, call_llm, execute_tool             │
│   • Custom spans for business logic (data_fetch, rag, storage)             │
│   • Same code works: Local → Cloud Run → ADK Engine                        │
│                                                                             │
│   NON-MVP (Explicitly deferred):                                           │
│   ❌ Drift detection                                                       │
│   ❌ LLM observability tools (Langfuse/Opik)                               │
│   ❌ Golden dataset testing                                                │
│   ❌ Business outcome dashboards                                           │
│   ❌ Advanced FinOps                                                       │
│                                                                             │
│   SUCCESS CRITERIA:                                                         │
│   • Know when system is broken (< 5 min detection)                         │
│   • Know which component failed (< 15 min diagnosis)                       │
│   • Trace any request E2E with latency breakdown                           │
│   • Know yesterday's cost                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## References

- [Google SRE Book - Monitoring](https://sre.google/sre-book/monitoring-distributed-systems/)
- [RED Method - Tom Wilkie](https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/)
- [AI Engineering Book - Chapter 4: Evaluating AI Systems](https://www.oreilly.com/library/view/ai-engineering/9781098166298/)
- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
