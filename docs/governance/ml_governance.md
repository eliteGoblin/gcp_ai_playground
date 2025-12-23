# ML Governance Framework for Financial Services

## Overview

This document outlines the governance framework for ML/AI systems handling sensitive financial data (personal loans, PII) in compliance with regulatory requirements.

---

## 1. Model Versioning Strategy

### Semantic Versioning for Models

```
Format: MAJOR.MINOR.PATCH

MAJOR  = Breaking changes (new model architecture, different inputs/outputs)
MINOR  = New features (fine-tuned, new capabilities, added safety)
PATCH  = Bug fixes (prompt adjustments, config tweaks)

Examples:
  v1.0.0  → Initial release
  v1.1.0  → Fine-tuned for loan assessment
  v1.1.1  → Fixed prompt injection vulnerability
  v2.0.0  → Migrated from Gemma to Gemini
```

### Model Registry Structure

```
Model Registry (Vertex AI)
│
├── gemma-3-1b-loan-assessment/
│   ├── v1.0.0/
│   │   ├── model_card.md          # Model documentation
│   │   ├── config.yaml            # Hyperparameters, settings
│   │   ├── evaluation_results.json # Performance metrics
│   │   └── deployment_history.json # When/where deployed
│   │
│   ├── v1.1.0/
│   │   └── ...
│   │
│   └── latest → v1.1.0            # Symbolic link to current
│
└── gemma-3-1b-customer-service/
    └── ...
```

### Version Tracking in Code

```yaml
# model_config.yaml
model:
  name: gemma-3-1b-loan-assessment
  version: v1.1.0
  base_model: google/gemma-3-1b-it
  fine_tuned: true
  training_date: 2024-12-15
  training_data_version: loan_dataset_v3
  owner: ml-team@company.com

deployment:
  environment: prod
  region: us-central1
  min_replicas: 1
  max_replicas: 3

governance:
  approved_by: security-team@company.com
  approval_date: 2024-12-16
  compliance_review: PASSED
  next_review_date: 2025-03-16
```

---

## 2. Model Lifecycle Governance

### Approval Gates

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   DEV       │ →  │   STAGING   │ →  │   UAT       │ →  │   PROD      │
│             │    │             │    │             │    │             │
│ Auto-deploy │    │ Team Lead   │    │ Security +  │    │ Change      │
│             │    │ Approval    │    │ Compliance  │    │ Advisory    │
│             │    │             │    │ Review      │    │ Board       │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### Pre-Production Checklist

```
□ Model Performance
  □ Accuracy meets threshold (e.g., >95%)
  □ Latency within SLA (e.g., p95 < 2s)
  □ No regression from previous version

□ Security
  □ Prompt injection tests passed
  □ PII leakage tests passed
  □ Adversarial input tests passed

□ Compliance
  □ Data residency requirements met
  □ Model explainability documented
  □ Bias assessment completed

□ Operational
  □ Runbooks updated
  □ Monitoring dashboards ready
  □ Rollback procedure tested
```

---

## 3. Data Governance for LLM

### Data Classification

| Level | Examples | LLM Handling |
|-------|----------|--------------|
| **PUBLIC** | Product names, general FAQ | Can be used directly |
| **INTERNAL** | Process docs, policies | Anonymize before use |
| **CONFIDENTIAL** | Loan amounts, income | Tokenize/mask |
| **RESTRICTED** | SSN, credit scores, PII | NEVER send to LLM |

### PII Handling Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   User       │     │  PII Vault   │     │   LLM        │
│   Request    │     │  (Tokenize)  │     │   Endpoint   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │  "Assess loan for  │                    │
       │   John Smith,      │                    │
       │   SSN 123-45-6789" │                    │
       │                    │                    │
       └────────────────────►                    │
                            │                    │
                   Tokenize │                    │
                            │                    │
                            │  "Assess loan for  │
                            │   [CUST_TOKEN_123] │
                            │   [SSN_MASKED]"    │
                            │                    │
                            └────────────────────►
                                                 │
                            ◄────────────────────┘
                            │
                   De-tokenize
                            │
       ◄────────────────────┘
       │
       │  "Based on the customer's
       │   profile, recommend..."
```

### Data Lineage Tracking

```yaml
# data_lineage.yaml
model: gemma-3-1b-loan-assessment-v1.1.0

training_data:
  - source: loan_applications_2023
    version: v3.2
    records: 50000
    pii_handling: tokenized
    retention: 7_years

  - source: customer_feedback
    version: v1.0
    records: 10000
    pii_handling: anonymized
    retention: 3_years

inference_logs:
  destination: bigquery
  dataset: ml_inference_logs
  retention: 7_years
  pii_handling: masked
```

---

## 4. Access Control

### Role-Based Access

```
┌─────────────────────────────────────────────────────────────────┐
│                     ACCESS MATRIX                               │
├─────────────────┬───────────┬───────────┬───────────┬──────────┤
│     Action      │ ML Eng    │ ML Ops    │ Security  │ Auditor  │
├─────────────────┼───────────┼───────────┼───────────┼──────────┤
│ View Models     │    ✓      │    ✓      │    ✓      │    ✓     │
│ Deploy Dev      │    ✓      │    ✓      │    ✗      │    ✗     │
│ Deploy Staging  │    ✗      │    ✓      │    ✗      │    ✗     │
│ Deploy Prod     │    ✗      │    ✓*     │    ✓**    │    ✗     │
│ View Logs       │    ✓      │    ✓      │    ✓      │    ✓     │
│ View PII Logs   │    ✗      │    ✗      │    ✓      │    ✓     │
│ Modify IAM      │    ✗      │    ✗      │    ✓      │    ✗     │
└─────────────────┴───────────┴───────────┴───────────┴──────────┘

* Requires security approval
** Approval only, no direct deploy
```

### Service Account Strategy

```hcl
# Separate service accounts per function

# For CI/CD deployment (used by GitHub Actions)
vertex-deployer@project.iam.gserviceaccount.com
  └── roles/aiplatform.admin
  └── roles/storage.objectViewer

# For runtime predictions (used by applications)
vertex-predictor@project.iam.gserviceaccount.com
  └── roles/aiplatform.user

# For monitoring (used by observability tools)
vertex-monitor@project.iam.gserviceaccount.com
  └── roles/monitoring.viewer
  └── roles/logging.viewer
```

---

## 5. Audit & Compliance

### What Gets Logged

| Event | Logged Data | Retention |
|-------|-------------|-----------|
| Model deployment | Who, when, version, config | 7 years |
| Prediction request | Request ID, timestamp, latency | 7 years |
| Prediction input | Tokenized/masked prompt | 7 years |
| Prediction output | Response (masked if PII) | 7 years |
| Access events | Who accessed what, when | 7 years |
| Config changes | Before/after, who, why | 7 years |

### Audit Log Format

```json
{
  "timestamp": "2024-12-17T20:00:00Z",
  "event_type": "PREDICTION_REQUEST",
  "request_id": "req_abc123",
  "model": {
    "name": "gemma-3-1b-loan-assessment",
    "version": "v1.1.0",
    "endpoint": "mg-endpoint-xxx"
  },
  "caller": {
    "service_account": "loan-service@project.iam.gserviceaccount.com",
    "ip_address": "10.0.1.100",
    "user_agent": "loan-service/2.0"
  },
  "request": {
    "prompt_hash": "sha256:abc...",  // Hash, not actual prompt
    "prompt_length": 150,
    "contains_pii": false  // Pre-validated
  },
  "response": {
    "latency_ms": 450,
    "tokens_generated": 50,
    "finish_reason": "STOP"
  },
  "compliance": {
    "data_residency": "us-central1",
    "pii_check": "PASSED",
    "content_filter": "PASSED"
  }
}
```

### Compliance Reporting

```sql
-- Monthly compliance report query
SELECT
  DATE_TRUNC(timestamp, MONTH) as month,
  COUNT(*) as total_requests,
  COUNTIF(compliance.pii_check = 'FAILED') as pii_violations,
  COUNTIF(response.latency_ms > 2000) as sla_breaches,
  AVG(response.latency_ms) as avg_latency
FROM
  `project.ml_inference_logs.predictions`
WHERE
  timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY
  month
ORDER BY
  month DESC;
```

---

## 6. Incident Response

### Severity Levels

| Level | Definition | Response Time | Example |
|-------|------------|---------------|---------|
| **P1** | Service down, data breach | 15 min | PII leak, model offline |
| **P2** | Degraded service | 1 hour | High latency, partial outage |
| **P3** | Minor issue | 4 hours | Non-critical bug |
| **P4** | Improvement | Next sprint | Feature request |

### Incident Response Procedure

```
1. DETECT
   └── Alert fires / User reports

2. TRIAGE (15 min)
   └── Determine severity
   └── Assign incident commander
   └── Create incident channel

3. MITIGATE (ASAP)
   └── Rollback if needed
   └── Scale resources
   └── Enable fallback

4. COMMUNICATE
   └── Notify stakeholders
   └── Update status page
   └── Regular updates

5. RESOLVE
   └── Root cause analysis
   └── Permanent fix
   └── Deploy fix

6. REVIEW (within 48 hours)
   └── Post-incident review
   └── Update runbooks
   └── Implement preventions
```

---

## 7. Quarterly Review Checklist

```
□ Access Review
  □ All service accounts still needed?
  □ IAM roles still appropriate?
  □ Remove unused permissions

□ Model Review
  □ Performance still meeting SLAs?
  □ Any drift detected?
  □ Retraining needed?

□ Security Review
  □ Any new vulnerabilities?
  □ Penetration test results
  □ Update dependencies

□ Compliance Review
  □ Audit log completeness
  □ Data retention compliance
  □ Regulatory changes

□ Cost Review
  □ Budget vs actual
  □ Optimization opportunities
  □ Forecast next quarter
```
