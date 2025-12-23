# AIOps Framework for Production LLM on GCP Vertex AI

## Overview

This document outlines the operational considerations for running LLMs in production on GCP Vertex AI, aligned with enterprise MLOps best practices.

---

## 1. Infrastructure as Code (IaC)

### Why It Matters
- **Reproducibility**: Same infrastructure across dev/staging/prod
- **Audit Trail**: Git history shows who changed what
- **Disaster Recovery**: Recreate entire stack from code
- **Compliance**: Required for SOC2, ISO27001

### What to Terraform
```
├── project.tf           # Project, billing, org policies
├── apis.tf              # Enable required APIs
├── iam.tf               # Service accounts, roles, workload identity
├── networking.tf        # VPC, subnets, Private Service Connect
├── vertex_ai.tf         # Model registry, endpoints, configs
├── monitoring.tf        # Dashboards, alerts, log sinks
├── secrets.tf           # Secret Manager for API keys
└── variables.tf         # Environment-specific configs
```

### Key Resources
- `google_vertex_ai_endpoint` - Prediction endpoints
- `google_vertex_ai_featurestore` - Feature management
- `google_project_iam_member` - Least privilege access
- `google_compute_network` - Private networking

---

## 2. Model Lifecycle Management

### Model Registry
```
Model Registry (Vertex AI)
├── model-v1.0.0 (deprecated)
├── model-v1.1.0 (previous)
├── model-v1.2.0 (current - 90% traffic)
└── model-v1.3.0-rc1 (canary - 10% traffic)
```

### Versioning Strategy
| Aspect | Strategy |
|--------|----------|
| Model artifacts | Semantic versioning (v1.2.3) |
| Prompts | Git-versioned, tagged releases |
| Configs | Environment variables + Secret Manager |
| Data | DVC or GCS with versioned prefixes |

### Deployment Patterns
1. **Blue/Green**: Two endpoints, instant switch
2. **Canary**: Traffic split (90/10), gradual rollout
3. **Shadow**: Mirror traffic to new model, compare outputs

---

## 3. CI/CD Pipeline

### Pipeline Stages
```yaml
# Cloud Build / GitHub Actions
stages:
  - validate:      # Lint, unit tests, security scan
  - build:         # Container image, push to Artifact Registry
  - test:          # Integration tests, model validation
  - deploy-dev:    # Auto-deploy to dev
  - deploy-staging: # Manual gate, deploy to staging
  - deploy-prod:   # Manual gate, canary then full rollout
  - monitor:       # Post-deploy health checks
```

### Model Validation Gates
- [ ] Model size within limits
- [ ] Latency benchmarks pass (p50, p95, p99)
- [ ] Accuracy metrics meet threshold
- [ ] No PII in training data
- [ ] Security scan passed
- [ ] Cost estimation approved

---

## 4. Observability & Monitoring

### Metrics to Track

| Category | Metrics |
|----------|---------|
| **Performance** | Latency (p50/p95/p99), throughput (QPS), error rate |
| **Model Health** | Prediction distribution, confidence scores, drift detection |
| **Infrastructure** | GPU utilization, memory, replica count |
| **Cost** | $/request, daily spend, budget vs actual |
| **Business** | Requests per customer, feature usage |

### Alerting Rules
```yaml
alerts:
  - name: high_latency
    condition: p95_latency > 2s for 5m
    severity: warning

  - name: error_spike
    condition: error_rate > 1% for 2m
    severity: critical

  - name: model_drift
    condition: prediction_distribution_shift > 0.1
    severity: warning

  - name: cost_overrun
    condition: daily_cost > budget * 1.2
    severity: warning
```

### Tools
- **Cloud Monitoring**: Infrastructure metrics, dashboards
- **Cloud Logging**: Request/response logs (sampling)
- **Langfuse/Langsmith**: LLM-specific tracing, prompt analytics
- **BigQuery**: Long-term analytics, cost analysis

---

## 5. Security & Governance

### IAM Best Practices
```hcl
# Least privilege - separate service accounts per function
resource "google_service_account" "model_deployer" {
  account_id   = "model-deployer"
  display_name = "Model Deployment SA"
}

resource "google_service_account" "model_predictor" {
  account_id   = "model-predictor"
  display_name = "Prediction Service SA"
}

# Roles
# model_deployer: roles/aiplatform.admin (deploy only)
# model_predictor: roles/aiplatform.user (predict only)
```

### Network Security
- **VPC Service Controls**: Prevent data exfiltration
- **Private Service Connect**: No public endpoints
- **Cloud Armor**: DDoS protection, WAF rules

### Compliance Checklist
- [ ] Data residency requirements (region constraints)
- [ ] PII handling (masking, tokenization)
- [ ] Audit logging enabled (Cloud Audit Logs)
- [ ] Encryption at rest and in transit
- [ ] Access reviews (quarterly)
- [ ] Incident response plan

### Model Governance
- **Model Cards**: Document model purpose, limitations, biases
- **Lineage Tracking**: Which data trained which model
- **Approval Workflows**: Manual gates for prod deployment

---

## 6. Cost Management

### Cost Optimization Strategies

| Strategy | Savings | Trade-off |
|----------|---------|-----------|
| Auto-scaling (min 0) | High | Cold start latency |
| Smaller models | High | Accuracy |
| Batch predictions | Medium | Not real-time |
| Committed use | 20-50% | Lock-in |
| Spot/Preemptible | 60-90% | Interruptions |

### Budget Controls
```hcl
resource "google_billing_budget" "vertex_ai" {
  billing_account = var.billing_account
  display_name    = "Vertex AI Budget"

  budget_filter {
    services = ["aiplatform.googleapis.com"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = "1000"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 0.9
    spend_basis       = "CURRENT_SPEND"
  }
}
```

---

## Quick Reference: Production Checklist

### Before Go-Live
- [ ] IaC for all resources (Terraform)
- [ ] CI/CD pipeline with gates
- [ ] Monitoring dashboards created
- [ ] Alerts configured and tested
- [ ] Runbooks documented
- [ ] On-call rotation set up
- [ ] Cost budget and alerts
- [ ] Security review completed
- [ ] Load testing passed
- [ ] Rollback procedure tested

### Day 2 Operations
- [ ] Regular model retraining schedule
- [ ] Drift monitoring active
- [ ] Cost review (weekly)
- [ ] Access review (quarterly)
- [ ] Incident post-mortems
- [ ] Capacity planning

---

## Architecture Diagram

```
                                    ┌─────────────────┐
                                    │   Cloud Armor   │
                                    │   (WAF/DDoS)    │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │  Load Balancer  │
                                    │  (HTTPS/gRPC)   │
                                    └────────┬────────┘
                                             │
                         ┌───────────────────┼───────────────────┐
                         │                   │                   │
                ┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐
                │   Endpoint v1   │ │   Endpoint v2   │ │  Endpoint v3    │
                │   (Prod 90%)    │ │  (Canary 10%)   │ │   (Shadow)      │
                └────────┬────────┘ └────────┬────────┘ └────────┬────────┘
                         │                   │                   │
                         └───────────────────┼───────────────────┘
                                             │
                                    ┌────────▼────────┐
                                    │  Model Registry │
                                    │  (Versioned)    │
                                    └────────┬────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
           ┌────────▼────────┐     ┌─────────▼────────┐     ┌─────────▼────────┐
           │ Cloud Monitoring│     │  Cloud Logging   │     │    BigQuery      │
           │   (Metrics)     │     │   (Traces)       │     │  (Analytics)     │
           └─────────────────┘     └──────────────────┘     └──────────────────┘
```
