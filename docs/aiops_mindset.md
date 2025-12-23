# AIOps Mindset: Senior AI Operations Engineer Framework

## Who This Is For

A Senior AI Ops Engineer at a financial services company handling:
- Personal loan applications
- PII data (names, SSN, income, credit scores)
- Regulatory requirements (APRA, Privacy Act, SOC2)

---

## 1. The AIOps Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DAILY AIOPS THINKING FRAMEWORK                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  "Is my model RELIABLE, SECURE, COMPLIANT, and COST-EFFECTIVE?"            │
│                                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐  │
│  │ DEPLOY   │ → │ OBSERVE  │ → │ RESPOND  │ → │ IMPROVE  │ → │ GOVERN   │  │
│  │          │   │          │   │          │   │          │   │          │  │
│  │ IaC      │   │ Metrics  │   │ Alerts   │   │ Tune     │   │ Audit    │  │
│  │ CI/CD    │   │ Logs     │   │ Runbooks │   │ Retrain  │   │ Comply   │  │
│  │ Version  │   │ Traces   │   │ Escalate │   │ A/B Test │   │ Review   │  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Daily Operations Checklist

### Morning (Start of Day)
```
□ Check overnight alerts - any P1/P2 incidents?
□ Review model health dashboard - latency, errors, drift
□ Check cost dashboard - any spikes?
□ Review pending deployments - any scheduled releases?
□ Check capacity - GPU utilization, queue depth
```

### During Day
```
□ Monitor active deployments - watch canary metrics
□ Review PRs - Terraform changes, model configs
□ Respond to incidents - follow runbooks
□ Update documentation - post-incident reviews
□ Attend standups - share blockers, status
```

### End of Day
```
□ Ensure no pending alerts
□ Document any manual interventions
□ Update on-call notes
□ Review tomorrow's scheduled changes
```

---

## 3. The 6 Pillars of Production LLM Ops

### Pillar 1: Infrastructure as Code (IaC)

**Why**: Reproducibility, audit trail, disaster recovery

```
NEVER do this:
  $ gcloud ai endpoints create ... (manual)

ALWAYS do this:
  $ terraform apply (from reviewed PR)
```

**Key Practice**: Every resource in Git, every change via PR

### Pillar 2: Model Lifecycle Management

**Versioning Strategy**:
```
models/
├── gemma-3-1b-it/
│   ├── v1.0.0/          # Initial release
│   ├── v1.1.0/          # Fine-tuned for loans
│   ├── v1.2.0/          # Added PII masking
│   └── v1.2.1/          # Bug fix
```

**Key Practice**: Semantic versioning, model cards, lineage tracking

### Pillar 3: CI/CD Pipeline

**Flow**:
```
Code Push → Lint → Test → Security Scan → Deploy Canary → Monitor → Promote
```

**Key Practice**: Automated gates, manual approval for prod

### Pillar 4: Observability

**What to Monitor**:
| Metric | Threshold | Action |
|--------|-----------|--------|
| P95 Latency | > 2s | Page on-call |
| Error Rate | > 1% | Page on-call |
| Model Drift | > 0.1 | Alert team |
| Daily Cost | > budget | Alert finance |

**Key Practice**: Dashboards for every endpoint, alerts for anomalies

### Pillar 5: Security & Compliance

**For Financial/PII Data**:
```
□ Data never leaves approved regions (data residency)
□ PII masked before hitting LLM (tokenization)
□ All access logged (audit trail)
□ Least privilege IAM (service accounts)
□ Encryption at rest and in transit
□ Regular access reviews
```

**Key Practice**: Security by default, compliance as code

### Pillar 6: Cost Management

**Demo Strategy** (what we're doing):
```
├── Single replica (not HA)
├── Smallest viable GPU (L4 vs A100)
├── Auto-scale to 0 when idle (if possible)
├── Budget alerts at $50, $100
└── Undeploy when not needed
```

**Key Practice**: Right-size for purpose, monitor continuously

---

## 4. Thinking Through a Deployment

When deploying a new model, ask yourself:

```
1. WHAT is changing?
   - New model version? Config change? Infra change?

2. WHO approved it?
   - PR reviewed? Security signed off? Compliance checked?

3. HOW will it be deployed?
   - Canary? Blue/green? Direct replacement?

4. WHAT could go wrong?
   - Model errors? Latency spike? Data issues?

5. HOW will we know?
   - Metrics? Alerts? Logs?

6. HOW will we rollback?
   - Previous version ready? Tested rollback procedure?
```

---

## 5. Incident Response Mindset

When something breaks:

```
┌─────────────────────────────────────────────────────────┐
│  INCIDENT RESPONSE FLOW                                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. DETECT    → Alert fires or user reports             │
│       ↓                                                 │
│  2. TRIAGE    → Is it P1/P2/P3? Who's impacted?        │
│       ↓                                                 │
│  3. MITIGATE  → Rollback? Scale up? Failover?          │
│       ↓                                                 │
│  4. FIX       → Root cause, permanent solution          │
│       ↓                                                 │
│  5. REVIEW    → Post-incident review, update runbooks   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Golden Rule**: Mitigate first, investigate later

---

## 6. Compliance Mindset for Financial Services

### Data Classification
```
PUBLIC        → Model architecture docs
INTERNAL      → Performance metrics, costs
CONFIDENTIAL  → Customer prompts, model outputs
RESTRICTED    → PII, loan details, credit scores
```

### Handling PII in LLM Context

```python
# WRONG: Raw PII to model
prompt = f"Assess loan for John Smith, SSN 123-45-6789, income $85,000"

# RIGHT: Tokenized/masked
prompt = f"Assess loan for [CUSTOMER_TOKEN_123], income bracket [INCOME_BAND_3]"
```

### Audit Requirements
- **What**: Every prediction request logged
- **Who**: User/service making request
- **When**: Timestamp with timezone
- **Why**: Business justification
- **Retention**: 7 years (financial regulations)

---

## 7. Skills Matrix (Aligned with JD)

| JD Requirement | How I Demonstrate It |
|----------------|---------------------|
| Cloud ML platforms (GCP, Vertex AI) | Deployed Gemma model to Vertex AI endpoint |
| Model deployment, scaling | Used Model Garden, configured GPU resources |
| CI/CD, IaC, Docker, K8s | Terraform configs, GitHub Actions pipeline |
| Monitoring/observability | Cloud Monitoring alerts, logging setup |
| ML governance, versioning | Semantic versioning, model registry |
| Compliance, regulated environments | PII handling, audit logging, access controls |
| Data quality, streaming | Input validation, request logging |

---

## 8. Day in the Life

### 9:00 AM - Check Systems
```bash
# Quick health check
gcloud ai endpoints list --region=us-central1
gcloud ai operations list --region=us-central1 --filter="done=false"
```

### 10:00 AM - Review PR for Model Update
```
- Check Terraform diff
- Verify security implications
- Approve or request changes
```

### 11:00 AM - Deploy Canary
```bash
# Apply Terraform change
terraform plan -var="traffic_split=10"
terraform apply
```

### 2:00 PM - Monitor Canary
```
- Check latency metrics
- Review error logs
- Compare to baseline
```

### 4:00 PM - Promote or Rollback
```bash
# If healthy, promote
terraform plan -var="traffic_split=100"
terraform apply

# If issues, rollback
terraform plan -var="traffic_split=0"
terraform apply
```

### 5:00 PM - Document & Handoff
```
- Update deployment log
- Note any issues
- Handoff to on-call
```
