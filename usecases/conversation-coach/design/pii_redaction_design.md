# PII Redaction Design Document

## Overview

This document outlines the design for PII (Personally Identifiable Information) redaction in the Conversation Coach pipeline. The system maintains **dual storage**: raw transcripts for compliance/legal purposes and redacted transcripts for coaching analytics.

---

## Table of Contents

1. [Business Requirements](#1-business-requirements)
2. [Regulatory Compliance](#2-regulatory-compliance)
3. [PII Categories](#3-pii-categories)
4. [Architecture](#4-architecture)
5. [Implementation Options](#5-implementation-options)
6. [Access Control](#6-access-control)
7. [Retention & Deletion](#7-retention--deletion)
8. [Cost Analysis](#8-cost-analysis)
9. [Implementation Plan](#9-implementation-plan)

---

## 1. Business Requirements

### Why Keep Raw (Unredacted) Data?

| Use Case | Description | Access Frequency |
|----------|-------------|------------------|
| **Customer Disputes** | Customer claims agent said X, need original transcript | Rare |
| **Legal Discovery** | Litigation requires original evidence | Rare |
| **Compliance Audit** | Regulator requests original records | Occasional |
| **QA Sampling** | Quality team reviews full context | Weekly |
| **Model Training** | Future NLP model training (with consent) | Project-based |

### Why Redact for Coaching?

| Reason | Description |
|--------|-------------|
| **Minimize Risk** | Coaching doesn't need PII - reduce breach surface |
| **Developer Access** | Data scientists can access redacted data freely |
| **Analytics** | Aggregate reports without PII exposure |
| **Third-Party Tools** | Can send to external analytics without PII concerns |

---

## 2. Regulatory Compliance

### Australia

#### Privacy Act 1988 (Cth)

| Principle | Requirement | Impact on Design |
|-----------|-------------|------------------|
| **APP 1** | Open and transparent management | Document what PII is collected and why |
| **APP 3** | Collection of solicited personal information | Only collect what's necessary |
| **APP 6** | Use or disclosure | Only use for purpose collected (coaching = secondary use) |
| **APP 8** | Cross-border disclosure | If data leaves Australia, additional requirements |
| **APP 11** | Security of personal information | Must protect from misuse, loss, unauthorized access |
| **APP 11.2** | Destruction when no longer needed | Must have retention/deletion policy |

#### Notifiable Data Breaches (NDB) Scheme

```
If breach occurs with PII:
├── Assess if "likely to result in serious harm"
├── If yes: Notify affected individuals + OAIC within 30 days
└── Penalties: Up to $2.2M for body corporates
```

#### ASIC RG 96 (Debt Collection)

| Requirement | Relevance |
|-------------|-----------|
| **Section 30** | Cannot disclose debt to third parties |
| **Section 34** | Records must be kept for compliance verification |
| **Section 40** | Privacy of debtor must be respected |

#### Australian Consumer Law (ACL)

- Unconscionable conduct provisions
- Records may be required as evidence
- Retention of original records recommended

---

### United States

#### Fair Debt Collection Practices Act (FDCPA)

| Section | Requirement | Impact |
|---------|-------------|--------|
| **§ 807(11)** | Cannot use false/misleading representation | Keep records to prove compliance |
| **§ 809** | Validation of debts | Must keep records of communications |
| **§ 812** | FTC enforcement | Records may be requested |

#### State Privacy Laws

| State | Law | Key Requirements |
|-------|-----|------------------|
| **California** | CCPA/CPRA | Right to deletion, right to know, opt-out of sale |
| **Virginia** | VCDPA | Similar to CCPA, effective 2023 |
| **Colorado** | CPA | Consumer rights, data minimization |
| **Connecticut** | CTDPA | Right to deletion, data portability |
| **Utah** | UCPA | Consumer rights, 30-day cure period |

#### CCPA/CPRA Requirements (California)

```
Consumer Rights:
├── Right to Know: What PII is collected and why
├── Right to Delete: Must delete upon request (with exceptions)
├── Right to Opt-Out: Of sale/sharing of PII
├── Right to Correct: Inaccurate PII
└── Right to Limit: Use of sensitive PII

Exceptions to Deletion:
├── Complete a transaction
├── Detect security incidents
├── Comply with legal obligation  ← Raw transcript retention
├── Internal uses reasonably aligned with expectations
└── Otherwise use internally in lawful manner
```

#### Gramm-Leach-Bliley Act (GLBA)

- Applies to financial institutions
- Requires safeguards for customer information
- Must have written information security plan

#### HIPAA (If Medical Debt)

- If transcript contains health information
- Requires additional protections
- 6-year retention requirement for PHI

---

### Compliance Comparison Matrix

| Requirement | Australia | US (Federal) | US (California) |
|-------------|-----------|--------------|-----------------|
| **Consent for collection** | Required (APP 3) | Varies | Required |
| **Right to access** | Yes (APP 12) | Limited | Yes (CCPA) |
| **Right to deletion** | Limited (APP 13) | No federal | Yes (CCPA) |
| **Breach notification** | 30 days (NDB) | Varies by state | 72 hours |
| **Cross-border transfer** | Restricted (APP 8) | No federal restriction | Varies |
| **Retention limits** | "No longer needed" | Varies | "Reasonably necessary" |
| **Penalties** | Up to $2.2M | Varies | $7,500/violation |

---

## 3. PII Categories

### Tier 1: High Sensitivity (Must Redact)

| PII Type | Examples | Redaction Token | Detection Method |
|----------|----------|-----------------|------------------|
| **Government IDs** | SSN, TFN, Medicare | `[GOV_ID]` | DLP + Regex |
| **Financial Accounts** | Bank account, credit card | `[FINANCIAL]` | DLP + Regex |
| **Health Information** | Diagnosis, conditions | `[MEDICAL]` | DLP |
| **Biometric Data** | Voice patterns (metadata) | N/A | Not in transcript |

### Tier 2: Medium Sensitivity (Should Redact)

| PII Type | Examples | Redaction Token | Detection Method |
|----------|----------|-----------------|------------------|
| **Full Name** | "Michael Chen" | `[CUSTOMER_NAME]` | DLP |
| **Phone Number** | 0412-xxx-xxx | `[PHONE]` | Regex |
| **Email Address** | user@example.com | `[EMAIL]` | Regex |
| **Physical Address** | 123 Main St | `[ADDRESS]` | DLP |
| **Date of Birth** | 15/03/1985 | `[DOB]` | Regex |

### Tier 3: Low Sensitivity (Consider Redacting)

| PII Type | Examples | Redaction Token | Detection Method |
|----------|----------|-----------------|------------------|
| **Account Reference** | ACC-789456 | `[ACCOUNT_ID]` | Regex |
| **Dollar Amounts** | $5,432.10 | `[AMOUNT]` or keep | Regex |
| **Employer Name** | "Acme Corp" | `[EMPLOYER]` | DLP (optional) |
| **Dates** | Payment dates | Keep | N/A |

### Tier 4: Not PII (Keep)

| Data Type | Examples | Reason to Keep |
|-----------|----------|----------------|
| **Agent Name** | "Marcus" | Needed for coaching attribution |
| **Agent ID** | AGT-001 | Analytics key |
| **Timestamps** | 14:32:05 | Needed for analysis |
| **Business Terms** | "payment plan" | Core content |

---

## 4. Architecture

### Dual Storage Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DUAL STORAGE ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  SOURCE                                                              │   │
│  │                                                                      │   │
│  │  Call Recording ──► Speech-to-Text ──► Raw Transcript               │   │
│  │                                              │                       │   │
│  └──────────────────────────────────────────────┼───────────────────────┘   │
│                                                 │                           │
│                                                 ▼                           │
│                                    ┌───────────────────────┐               │
│                                    │    PII Redaction      │               │
│                                    │    (Cloud DLP API)    │               │
│                                    └───────────┬───────────┘               │
│                                                │                           │
│                         ┌──────────────────────┴──────────────────────┐    │
│                         │                                             │    │
│                         ▼                                             ▼    │
│  ┌─────────────────────────────────────┐   ┌─────────────────────────────┐ │
│  │  RAW STORAGE (Restricted)           │   │  REDACTED STORAGE (Open)    │ │
│  │                                     │   │                             │ │
│  │  gs://cc-raw-restricted/            │   │  gs://cc-data/              │ │
│  │  ├── 2025-12-28/                    │   │  ├── 2025-12-28/            │ │
│  │  │   └── {uuid}/                    │   │  │   └── {uuid}/            │ │
│  │  │       ├── transcription.json     │   │  │       ├── transcription. │ │
│  │  │       └── metadata.json          │   │  │       │   _redacted.json │ │
│  │  │                                  │   │  │       └── metadata.json  │ │
│  │  │                                  │   │  │                          │ │
│  │  │  ACCESS: Legal, Compliance,      │   │  │  ACCESS: All developers, │ │
│  │  │          QA Managers only        │   │  │          Data Scientists │ │
│  │  │                                  │   │  │          Analytics team  │ │
│  │  │  RETENTION: 7 years              │   │  │                          │ │
│  │  │  ENCRYPTION: CMEK                │   │  │  RETENTION: 2 years      │ │
│  │  │  AUDIT: All access logged        │   │  │  ENCRYPTION: Default     │ │
│  │  └─────────────────────────────────┘   │  └─────────────────────────┘ │
│  │                                         │              │               │ │
│  │                                         │              ▼               │ │
│  │                                         │    ┌─────────────────────┐  │ │
│  │                                         │    │  CCAI Insights      │  │ │
│  │                                         │    │  (redacted input)   │  │ │
│  │                                         │    └──────────┬──────────┘  │ │
│  │                                         │               │             │ │
│  │                                         │               ▼             │ │
│  │                                         │    ┌─────────────────────┐  │ │
│  │                                         │    │  BigQuery           │  │ │
│  │                                         │    │  (redacted data)    │  │ │
│  │                                         │    │  • ci_enrichment    │  │ │
│  │                                         │    │  • coach_analysis   │  │ │
│  │                                         │    └─────────────────────┘  │ │
│  │                                         │                             │ │
│  └─────────────────────────────────────────┴─────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Detail

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW SEQUENCE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. INGESTION                                                               │
│     ──────────                                                              │
│     Raw transcript arrives                                                  │
│            │                                                                │
│            ├────────────────────────────────────────┐                      │
│            │                                        │                      │
│            ▼                                        ▼                      │
│     Store to RAW bucket               Call Cloud DLP API                   │
│     (immediate, before redaction)     ├── Detect PII                       │
│            │                          ├── Apply redactions                 │
│            │                          └── Return redacted text             │
│            │                                        │                      │
│            ▼                                        ▼                      │
│     gs://cc-raw-restricted/           gs://cc-data/ (redacted)             │
│     {uuid}/transcription.json         {uuid}/transcription_redacted.json   │
│                                                     │                      │
│                                                     ▼                      │
│                                              CCAI Insights                  │
│                                              (analyzes redacted)            │
│                                                     │                      │
│                                                     ▼                      │
│                                              BigQuery                       │
│                                              (stores redacted)              │
│                                                                             │
│  2. COACHING (uses only redacted)                                          │
│     ─────────────────────────────                                          │
│     BQ ci_enrichment ──► Topic Extract ──► RAG ──► Coach ──► BQ results   │
│     (redacted)                                           (redacted quotes) │
│                                                                             │
│  3. DISPUTE/AUDIT (uses raw)                                               │
│     ────────────────────────                                               │
│     Compliance request ──► Approval workflow ──► Access gs://cc-raw-*     │
│                                                  (logged, audited)         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Implementation Options

### Option A: Google Cloud DLP API (Recommended)

```python
from google.cloud import dlp_v2

class PIIRedactor:
    """PII redaction using Google Cloud DLP API."""

    # Info types for Australia + US
    INFO_TYPES = [
        # Universal
        {"name": "PERSON_NAME"},
        {"name": "PHONE_NUMBER"},
        {"name": "EMAIL_ADDRESS"},
        {"name": "STREET_ADDRESS"},
        {"name": "DATE_OF_BIRTH"},
        {"name": "CREDIT_CARD_NUMBER"},

        # Australia specific
        {"name": "AUSTRALIA_TAX_FILE_NUMBER"},
        {"name": "AUSTRALIA_MEDICARE_NUMBER"},
        {"name": "AUSTRALIA_DRIVERS_LICENSE_NUMBER"},
        {"name": "AUSTRALIA_PASSPORT"},

        # US specific
        {"name": "US_SOCIAL_SECURITY_NUMBER"},
        {"name": "US_DRIVERS_LICENSE_NUMBER"},
        {"name": "US_PASSPORT"},
        {"name": "US_BANK_ROUTING_MICR"},
        {"name": "US_INDIVIDUAL_TAXPAYER_IDENTIFICATION_NUMBER"},
    ]

    def __init__(self, project_id: str):
        self.client = dlp_v2.DlpServiceClient()
        self.project_id = project_id
        self.parent = f"projects/{project_id}/locations/global"

    def redact(self, text: str) -> tuple[str, list[dict]]:
        """
        Redact PII from text.

        Returns:
            Tuple of (redacted_text, findings)
        """
        inspect_config = {
            "info_types": self.INFO_TYPES,
            "min_likelihood": "LIKELY",
        }

        deidentify_config = {
            "info_type_transformations": {
                "transformations": [{
                    "primitive_transformation": {
                        "replace_with_info_type_config": {}
                    }
                }]
            }
        }

        response = self.client.deidentify_content(
            request={
                "parent": self.parent,
                "deidentify_config": deidentify_config,
                "inspect_config": inspect_config,
                "item": {"value": text},
            }
        )

        # Extract findings for audit
        findings = []
        if hasattr(response, 'overview') and response.overview.transformation_summaries:
            for summary in response.overview.transformation_summaries:
                findings.append({
                    "info_type": summary.info_type.name,
                    "count": summary.transformed_count,
                })

        return response.item.value, findings
```

**Pros:**
- 150+ built-in detectors
- Australia and US specific detectors
- Production-ready, Google-maintained
- ML-based detection (catches variations)

**Cons:**
- API cost (~$1-3 per 1000 units)
- Latency (~100-500ms per call)
- Requires API permissions

---

### Option B: Hybrid (DLP + Regex)

```python
import re
from typing import Optional

class HybridRedactor:
    """
    Hybrid approach:
    - Regex for structured patterns (fast, free)
    - DLP for names and context-sensitive PII (accurate)
    """

    # Regex patterns for structured PII
    PATTERNS = {
        # Australia
        "AU_PHONE": (r"\b(?:(?:\+?61|0)4\d{8}|\(\d{2}\)\s*\d{4}\s*\d{4})\b", "[PHONE]"),
        "AU_TFN": (r"\b\d{3}\s?\d{3}\s?\d{3}\b", "[TFN]"),
        "AU_MEDICARE": (r"\b\d{4}\s?\d{5}\s?\d{1}\b", "[MEDICARE]"),

        # US
        "US_PHONE": (r"\b(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b", "[PHONE]"),
        "US_SSN": (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),

        # Universal
        "EMAIL": (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),
        "CREDIT_CARD": (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", "[CREDIT_CARD]"),
        "ACCOUNT_NUM": (r"\b(?:ACC|ACCT|REF|A/C)[-#:\s]?\d{6,12}\b", "[ACCOUNT_ID]"),
        "DOB": (r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "[DOB]"),
    }

    def __init__(self, project_id: Optional[str] = None, use_dlp: bool = True):
        self.use_dlp = use_dlp and project_id is not None
        if self.use_dlp:
            self.dlp_redactor = PIIRedactor(project_id)

    def redact(self, text: str) -> tuple[str, list[dict]]:
        """
        Redact PII using hybrid approach.

        1. First pass: Regex for structured patterns (fast)
        2. Second pass: DLP for names (if enabled)
        """
        findings = []

        # Pass 1: Regex
        for pattern_name, (pattern, replacement) in self.PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                findings.append({"info_type": pattern_name, "count": len(matches)})
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # Pass 2: DLP for names (optional)
        if self.use_dlp:
            text, dlp_findings = self.dlp_redactor.redact(text)
            findings.extend(dlp_findings)

        return text, findings
```

**Pros:**
- Lower cost (regex is free)
- Faster (regex is instant)
- DLP only for hard cases (names)

**Cons:**
- More code to maintain
- Regex may miss edge cases

---

### Option C: CCAI Insights Built-in Redaction

Configure in GCP Console:
```
CCAI Insights > Conversation Profile > Redaction Settings
├── Enable automatic redaction: ✓
├── Redaction mode: Replace with info type
└── Info types to redact:
    ├── PERSON_NAME
    ├── PHONE_NUMBER
    ├── EMAIL_ADDRESS
    ├── CREDIT_CARD_NUMBER
    ├── US_SOCIAL_SECURITY_NUMBER
    └── AUSTRALIA_TAX_FILE_NUMBER
```

**Pros:**
- No code needed
- Included in CI pricing
- Applied at analysis time

**Cons:**
- Only affects CI storage
- Must still redact raw GCS separately
- Less control

---

## 6. Access Control

### IAM Configuration

```yaml
# Raw bucket (restricted)
gs://cc-raw-restricted/:
  roles:
    - role: roles/storage.objectViewer
      members:
        - group:legal@company.com
        - group:compliance@company.com
        - serviceAccount:audit-sa@project.iam.gserviceaccount.com

    - role: roles/storage.objectAdmin
      members:
        - serviceAccount:ingest-sa@project.iam.gserviceaccount.com  # Write only

  audit_logging: DATA_READ, DATA_WRITE

# Redacted bucket (open)
gs://cc-data/:
  roles:
    - role: roles/storage.objectViewer
      members:
        - group:engineering@company.com
        - group:data-science@company.com
        - group:analytics@company.com
        - serviceAccount:ci-sa@project.iam.gserviceaccount.com
        - serviceAccount:coach-sa@project.iam.gserviceaccount.com
```

### Access Request Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  RAW DATA ACCESS REQUEST WORKFLOW                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Requestor submits ticket                                    │
│     ├── Reason: [Dispute / Audit / Legal / QA]                 │
│     ├── Conversation IDs: [list]                               │
│     └── Justification: [text]                                  │
│                                                                 │
│  2. Approval (based on reason)                                  │
│     ├── Dispute: Manager + Legal                               │
│     ├── Audit: Compliance Officer                              │
│     ├── Legal: Legal Counsel                                   │
│     └── QA: QA Manager                                         │
│                                                                 │
│  3. Time-limited access granted                                 │
│     ├── Duration: 24-72 hours                                  │
│     └── Scope: Specific conversation IDs only                  │
│                                                                 │
│  4. Access logged to audit table                                │
│     ├── Who accessed                                           │
│     ├── What conversations                                     │
│     ├── When                                                   │
│     └── Why (linked to ticket)                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Retention & Deletion

### Retention Policy

| Storage | Data Type | Retention | Rationale |
|---------|-----------|-----------|-----------|
| **gs://cc-raw-restricted/** | Raw transcripts | 7 years | Legal/compliance requirements |
| **gs://cc-data/** | Redacted transcripts | 2 years | Coaching analytics |
| **BQ: ci_enrichment** | Redacted analysis | 2 years | Coaching analytics |
| **BQ: coach_analysis** | Coaching results | 2 years | Performance tracking |
| **BQ: deletion_requests** | Audit log | 10 years | Compliance proof |

### Lifecycle Rules (GCS)

```json
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {
          "age": 2555,
          "matchesPrefix": ["gs://cc-raw-restricted/"]
        }
      },
      {
        "action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
        "condition": {
          "age": 90,
          "matchesPrefix": ["gs://cc-raw-restricted/"]
        }
      }
    ]
  }
}
```

### Customer Deletion Workflow

```python
class CustomerDataDeletion:
    """
    Handle customer deletion requests (GDPR/CCPA compliance).
    """

    def process_deletion_request(
        self,
        customer_id: str,
        request_source: str,  # "CCPA", "GDPR", "Customer Request"
        requestor: str,
    ) -> dict:
        """
        Delete all customer data across all storage.

        Note: Raw data may be retained if legal exception applies.
        """
        # 1. Find all conversations for customer
        conversations = self._find_customer_conversations(customer_id)

        # 2. Check for legal holds
        legal_holds = self._check_legal_holds(conversations)

        # 3. Delete from each storage (except legal holds)
        deleted = []
        retained = []

        for conv_id in conversations:
            if conv_id in legal_holds:
                retained.append(conv_id)
                continue

            # Delete from redacted storage
            self._delete_from_gcs(f"gs://cc-data/{conv_id}")
            self._delete_from_bq("ci_enrichment", conv_id)
            self._delete_from_bq("coach_analysis", conv_id)

            # Delete from raw storage (if no legal exception)
            if request_source in ["GDPR", "CCPA"]:
                self._delete_from_gcs(f"gs://cc-raw-restricted/{conv_id}")

            deleted.append(conv_id)

        # 4. Log deletion
        self._log_deletion(
            customer_id=customer_id,
            deleted=deleted,
            retained=retained,
            reason=request_source,
            requestor=requestor,
        )

        return {
            "customer_id": customer_id,
            "deleted_count": len(deleted),
            "retained_count": len(retained),
            "retained_reason": "legal_hold" if retained else None,
        }
```

### Legal Exceptions to Deletion

| Jurisdiction | Exception | Applies To |
|--------------|-----------|------------|
| **CCPA** | Complete a transaction | Active disputes |
| **CCPA** | Detect security incidents | Fraud cases |
| **CCPA** | Comply with legal obligation | Litigation holds |
| **GDPR** | Legal claims | Active disputes |
| **GDPR** | Legal obligation | Regulatory requirements |
| **Australia** | Legal proceedings | Active litigation |

---

## 8. Cost Analysis

### Cloud DLP Pricing

| Volume | Price per Unit | Monthly Cost (1000 convos × 20 turns) |
|--------|---------------|---------------------------------------|
| 0-1GB | $1.00/GB | ~$20 |
| 1-50GB | $0.75/GB | ~$15/GB |
| 50GB+ | $0.60/GB | ~$12/GB |

### Storage Costs

| Storage | Size Estimate | Monthly Cost |
|---------|--------------|--------------|
| Raw GCS (Standard) | 100MB/1000 convos | ~$2.50 |
| Raw GCS (Coldline after 90d) | 100MB | ~$0.40 |
| Redacted GCS | 100MB | ~$2.50 |
| BigQuery | 500MB | ~$10 |

### Total Estimated Cost

| Scale | DLP | Storage | Total/Month |
|-------|-----|---------|-------------|
| 1,000 conversations | $20 | $15 | ~$35 |
| 10,000 conversations | $150 | $50 | ~$200 |
| 100,000 conversations | $1,200 | $300 | ~$1,500 |

---

## 9. Implementation Plan

### Phase 1: Infrastructure (Week 1)

- [ ] Create restricted GCS bucket with IAM
- [ ] Configure lifecycle policies
- [ ] Set up audit logging
- [ ] Create BQ deletion tracking tables

### Phase 2: Redaction Pipeline (Week 2)

- [ ] Implement PIIRedactor class (DLP API)
- [ ] Add hybrid regex patterns
- [ ] Integrate into ingestion pipeline
- [ ] Update CI to receive redacted input

### Phase 3: Access Control (Week 3)

- [ ] Configure IAM roles
- [ ] Create access request workflow
- [ ] Implement audit logging
- [ ] Document access procedures

### Phase 4: Deletion Workflow (Week 4)

- [ ] Implement customer lookup
- [ ] Create deletion CLI command
- [ ] Add legal hold checking
- [ ] Test end-to-end deletion

### Phase 5: Testing & Documentation (Week 5)

- [ ] Test with sample data
- [ ] Verify redaction completeness
- [ ] Document compliance procedures
- [ ] Train team on new workflows

---

## Appendix A: Sample Redacted Output

### Before Redaction

```
Agent: Hi, this is Marcus from FastCash Loans. Am I speaking with Michael Chen?
Customer: Yes, this is Michael. Look, I know why you're calling but I lost my job
last month and my wife has medical bills. I can't pay the $5,432 right now.
Agent: I understand Mr Chen. Let me look up your account. I see account ACC-789456
has a balance of $5,432.10. Can you confirm your date of birth for verification?
Customer: It's March 15, 1985. My phone is 0412-345-678 if you need to call back.
```

### After Redaction

```
Agent: Hi, this is Marcus from FastCash Loans. Am I speaking with [PERSON_NAME]?
Customer: Yes, this is [PERSON_NAME]. Look, I know why you're calling but I lost my job
last month and my wife has medical bills. I can't pay the [AMOUNT] right now.
Agent: I understand [PERSON_NAME]. Let me look up your account. I see account [ACCOUNT_ID]
has a balance of [AMOUNT]. Can you confirm your date of birth for verification?
Customer: It's [DOB]. My phone is [PHONE] if you need to call back.
```

---

## Appendix B: Compliance Checklist

### Australia (Privacy Act)

- [ ] Privacy policy updated to describe coaching use
- [ ] Collection notice includes secondary use
- [ ] Security measures documented (APP 11)
- [ ] Retention policy defined (APP 11.2)
- [ ] Cross-border transfer assessment (if applicable)

### US (CCPA)

- [ ] Privacy notice updated
- [ ] "Do Not Sell" mechanism (if applicable)
- [ ] Deletion request workflow implemented
- [ ] Consumer request response within 45 days
- [ ] Service provider agreements updated

### Both

- [ ] Data inventory completed
- [ ] Access controls implemented
- [ ] Audit logging enabled
- [ ] Incident response plan includes PII breach
- [ ] Staff training on PII handling
