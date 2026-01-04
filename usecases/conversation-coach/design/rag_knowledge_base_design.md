# RAG Knowledge Base System Design

## 1. System Overview

### 1.1 Purpose

Production-ready Knowledge Base system for RAG-based conversation coaching with:
- **Always-latest policy**: Coach always uses current best practices (no time-travel)
- **Unified ingestion**: All documents flow through single pipeline (GCS → Vector + BQ)
- **Auditable**: Track which version was used, keep history in BQ
- **Dynamic updates**: Documents can change without code deployment

### 1.2 Key Design Principles

| Principle | Decision | Rationale |
|-----------|----------|-----------|
| Retrieval Strategy | **Always latest** | Coaching should reflect current best practices |
| Source of Truth | **GCS bucket** | Single location for all docs, even if stored in code |
| Pipeline | **Unified** | Same process for all doc types |
| Vector Store | **Active chunks only** | Superseded/deprecated docs removed |
| BQ Storage | **Full history** | Raw content + metadata for audit |

### 1.3 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    UNIFIED KB ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   SOURCE OF TRUTH: GCS Bucket                                               │
│   ════════════════════════════                                              │
│   gs://cc-coach-kb/                                                         │
│   ├── policy/POL-*.md                                                       │
│   ├── coaching/COACH-*.md                                                   │
│   └── examples/EX-*.md                                                      │
│                │                                                            │
│                │ Eventarc (object change)                                   │
│                ▼                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    UNIFIED INGESTION PIPELINE                       │   │
│   │                    (Cloud Run Job)                                  │   │
│   │                                                                     │   │
│   │   1. List all docs in GCS                                           │   │
│   │   2. Parse YAML frontmatter + markdown                              │   │
│   │   3. Validate required fields                                       │   │
│   │   4. Compute checksum (detect changes)                              │   │
│   │   5. Chunk by section headings                                      │   │
│   │   6. Generate embeddings                                            │   │
│   │   7. Sync to Vector Store + BQ                                      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                │                              │                             │
│                ▼                              ▼                             │
│   ┌───────────────────────┐     ┌───────────────────────────────────────┐   │
│   │    VECTOR STORE       │     │         BIGQUERY                      │   │
│   │  (Vertex AI Search)   │     │                                       │   │
│   │                       │     │  kb_documents (metadata + raw_content)│   │
│   │  • ACTIVE chunks only │     │  kb_chunks (content + embeddings ref) │   │
│   │  • Embeddings         │     │  kb_retrieval_log (audit trail)       │   │
│   │  • Metadata filters   │     │                                       │   │
│   │                       │     │  • Full history (all versions)        │   │
│   └───────────┬───────────┘     │  • Query-able for audit               │   │
│               │                 └───────────────────────────────────────┘   │
│               │                                                             │
│               ▼                                                             │
│   ┌───────────────────────┐                                                 │
│   │    COACH AGENT        │                                                 │
│   │  (RAG Retrieval)      │                                                 │
│   │                       │                                                 │
│   │  • Query vector store │                                                 │
│   │  • Get relevant chunks│                                                 │
│   │  • Generate coaching  │                                                 │
│   └───────────────────────┘                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.4 Stock & Flow Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KB SYSTEM - STOCK & FLOW MODEL                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   INFLOWS (Sources)                 STOCK (KB State)                        │
│   ─────────────────                 ────────────────                        │
│   • New documents                   • Active documents                      │
│   • Document updates                • Active chunks (embeddings)            │
│   • External refs (ASIC)            • Version history                       │
│   • Example conversations           • Metadata index                        │
│                                                                             │
│           │                               │                                 │
│           ▼                               ▼                                 │
│   ┌───────────────┐              ┌───────────────────┐                      │
│   │  Ingestion    │──────────────│   Vector Store    │                      │
│   │  Pipeline     │              │   + Doc Store     │                      │
│   └───────────────┘              └─────────┬─────────┘                      │
│                                            │                                │
│                                            ▼                                │
│   OUTFLOWS (Consumers)              FEEDBACK LOOP                           │
│   ────────────────────              ─────────────                           │
│   • RAG retrieval                   • Usage analytics                       │
│   • Coach responses                 • Retrieval quality                     │
│   • Audit citations                 • Missing coverage                      │
│   • Compliance reports              • Version effectiveness                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Document Lifecycle Management

### 2.1 Document States

```
┌─────────┐     ┌─────────┐     ┌───────────┐     ┌────────────┐
│  DRAFT  │────►│ ACTIVE  │────►│SUPERSEDED │────►│ DEPRECATED │
└─────────┘     └─────────┘     └───────────┘     └────────────┘
                     │
                     ▼
              ┌─────────────┐
              │  ARCHIVED   │
              └─────────────┘
```

| State | Description | Retrievable |
|-------|-------------|-------------|
| DRAFT | Under review, not yet active | No |
| ACTIVE | Current version, used for new coachings | Yes |
| SUPERSEDED | Replaced by newer version | Yes (historical) |
| DEPRECATED | No longer valid, should not be used | No |
| ARCHIVED | Kept for audit, no longer needed | No |

### 2.2 Version Control Strategy

**Semantic Versioning**: `MAJOR.MINOR.PATCH`
- **MAJOR**: Breaking changes (new compliance requirements)
- **MINOR**: New content (new scenarios added)
- **PATCH**: Fixes (typos, clarifications)

**Effective Dates**:
- `effective_from`: When this version becomes active
- `effective_to`: When this version is superseded (null = currently active)

**Supersession**: `superseded_by` field links to replacement document

### 2.3 Document Metadata Schema

```yaml
---
# ===== IDENTITY =====
doc_id: POL-002
doc_type: policy  # policy | coaching | example | external_ref
title: Prohibited Language Guidelines

# ===== VERSIONING =====
version: 1.2.0
effective_from: 2025-01-01
effective_to: null  # null = currently active
superseded_by: null # doc_id of replacement
changelog:
  - version: 1.2.0
    date: 2025-01-01
    changes: Added wage garnishment prohibition
  - version: 1.1.0
    date: 2024-07-01
    changes: Clarified legal action threats

# ===== SCOPE (for filtering) =====
business_lines: [COLLECTIONS, HARDSHIP]
queues: [ALL]
regions: [AU]
call_directions: [INBOUND, OUTBOUND]

# ===== AUDIT =====
author: compliance-team
approved_by: legal-team
last_reviewed: 2025-01-01

# ===== RAG HINTS =====
priority: high  # high/medium/low (affects retrieval ranking)
keywords: [threats, legal, garnishment, prohibited]
---
```

---

## 3. Document Sources

### 3.1 External References (ASIC/ACCC)

**Primary Regulatory Documents**:

| Document | Source | Published |
|----------|--------|-----------|
| ASIC RG 96 | [PDF Download](https://download.asic.gov.au/media/hw4nf11g/rg96-published-13-april-2021.pdf) | April 2021 |
| ACCC Debt Collection Guideline | [ACCC Page](https://www.accc.gov.au/about-us/publications/guideline-on-debt-collection-for-collectors-and-creditors) | April 2021 |

**Key Compliance Rules from ASIC RG 96**:
- Contact frequency: Max 3x/week, 10x/month
- Prohibited contact days: Public holidays
- Harassment provisions: No undue pressure or coercion
- Disclosure requirements: Debtor rights must be communicated
- Penalties: Up to $1.7M for corporations

**Usage in RAG**:
- Store as `external_ref` doc_type with URL and summary
- Reference for citations, don't embed full text (copyright)
- Coach can cite: "Per ASIC RG 96 Section 2.3..."

### 3.2 Corporate Compliance Documents (To Generate)

```
/documents/policy/
├── POL-001_compliance_overview.md      # Company policy alignment with ASIC
├── POL-002_prohibited_language.md      # Specific phrases agents cannot use
├── POL-003_required_disclosures.md     # Mandatory disclosures per scenario
├── POL-004_hardship_provisions.md      # Hardship program rules
├── POL-005_escalation_procedures.md    # When and how to escalate
└── POL-006_identity_verification.md    # Verification requirements
```

**Content Source**: Extract from current `coach_system_prompt.py` EMBEDDED_POLICY

### 3.3 Agent Playbook Documents (To Generate)

```
/documents/coaching/
├── COACH-001_agent_playbook.md         # Main playbook overview
├── COACH-002_de_escalation_guide.md    # Handling upset customers
├── COACH-003_scenario_responses.md     # Per-scenario scripts
├── COACH-004_empathy_phrases.md        # Approved empathy language
└── COACH-005_collections_techniques.md # Effective collection approaches
```

**Scenarios to Cover** (minimum for POC based on dev data):
1. Hardship request (job loss, medical issues)
2. Payment dispute
3. Angry/escalating customer
4. Identity verification
5. Routine payment arrangement

### 3.4 Example Conversations (From Dev Data)

```
/documents/examples/
├── EX-001_good_hardship_handling.md    # Score > 8
├── EX-002_good_de_escalation.md        # Score > 8
├── EX-003_poor_compliance.md           # Score < 4
└── EX-004_poor_empathy.md              # Score < 4
```

**Source**: Extract from `coach_analysis` table

---

## 4. Ingestion Pipeline Design

### 4.1 Pipeline Architecture

```
Document Source          Change Detection        Processing           Storage
─────────────────────────────────────────────────────────────────────────────

GCS Bucket         ──►   Eventarc           ──►  Cloud Run Job   ──►  Vector Store
(documents/)             (object change)          (process.py)        (embeddings)
     │                                                 │                   │
     │                                                 │                   │
Git Repo           ──►   Cloud Build        ──►       │              ──►  BigQuery
(documents/)             (on merge)                   │                  (metadata)
                                                      │
                                                      ▼
                                               ┌─────────────┐
                                               │  Chunking   │
                                               │  Embedding  │
                                               │  Indexing   │
                                               └─────────────┘
```

### 4.2 Processing Steps

1. **Parse**: Extract YAML frontmatter + markdown content
2. **Validate**: Check required metadata fields, schema compliance
3. **Chunk**: Split by section headings (200-500 tokens per chunk)
4. **Embed**: Generate embeddings using `text-embedding-005`
5. **Index**: Upsert to vector store with metadata filters
6. **Register**: Update BQ document registry tables

### 4.3 Chunking Strategy

**Split by Section Headings**:
```markdown
## Prohibited Language              ← Chunk 1 boundary
### Threats
Agents must never...               ← Content in Chunk 1

### Harassment                      ← Chunk 2 boundary
Repeated contact is...             ← Content in Chunk 2
```

**Chunk Size**: 200-500 tokens (optimal for retrieval)

**Chunk Schema**:
```python
Chunk = {
    # Identity
    "chunk_id": "POL-002-v1.2.0-section-3",
    "doc_id": "POL-002",
    "doc_version": "1.2.0",

    # Content
    "section_path": "Prohibited Language > Threats > Legal Action",
    "content": "Agents must never threaten legal action unless...",
    "token_count": 350,

    # Embedding
    "embedding": [0.123, -0.456, ...],  # 768 dims for text-embedding-005

    # Metadata (copied from document)
    "effective_from": "2025-01-01",
    "effective_to": null,
    "business_lines": ["COLLECTIONS"],
    "priority": "high",

    # Audit
    "indexed_at": "2025-01-03T10:00:00Z",
    "pipeline_version": "1.0.0"
}
```

---

## 5. Document Update Operations

### 5.1 Always-Latest Retrieval

**Key Decision**: Vector store only contains ACTIVE chunks. No time-travel.

```
Vector Store (ACTIVE only)              BQ (Full History)
────────────────────────               ──────────────────

POL-002-v1.2.0-chunk-1                 POL-002-v1.0.0 (superseded)
POL-002-v1.2.0-chunk-2                 POL-002-v1.1.0 (superseded)
POL-002-v1.2.0-chunk-3                 POL-002-v1.2.0 (active) ← current

Only latest version                    All versions for audit
```

**Rationale**: Coaching should always reflect current best practices, not historical policy.

### 5.2 What Happens When Documents Change

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DOCUMENT LIFECYCLE OPERATIONS                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   OPERATION              VECTOR STORE              BQ TABLES                │
│   ─────────              ────────────              ─────────                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ ADD NEW DOCUMENT                                                    │   │
│   │ (POL-007 v1.0 created)                                              │   │
│   │                                                                     │   │
│   │ Vector: INSERT all chunks with embeddings                           │   │
│   │ BQ:     INSERT kb_documents (status='active')                       │   │
│   │         INSERT kb_chunks                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ UPDATE DOCUMENT (new version)                                       │   │
│   │ (POL-002 v1.1 → v1.2)                                               │   │
│   │                                                                     │   │
│   │ Vector: DELETE all v1.1 chunks                                      │   │
│   │         INSERT all v1.2 chunks (replace in place)                   │   │
│   │ BQ:     UPDATE v1.1: status='superseded', superseded_by='v1.2'      │   │
│   │         INSERT v1.2: status='active'                                │   │
│   │         (old chunks kept in kb_chunks for audit)                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ RETIRE DOCUMENT (no replacement)                                    │   │
│   │ (POL-003 deprecated)                                                │   │
│   │                                                                     │   │
│   │ Vector: DELETE all chunks (remove from retrieval)                   │   │
│   │ BQ:     UPDATE: status='deprecated'                                 │   │
│   │         (keep in BQ for audit, not retrievable)                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ ROLLBACK (revert to previous version)                               │   │
│   │ (POL-002 v1.2 → v1.1)                                               │   │
│   │                                                                     │   │
│   │ Vector: DELETE v1.2 chunks                                          │   │
│   │         INSERT v1.1 chunks (re-embed or restore from BQ)            │   │
│   │ BQ:     UPDATE v1.2: status='superseded'                            │   │
│   │         UPDATE v1.1: status='active'                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Sync Strategy Options

**Option A: Full Refresh (Simple, for POC)**
```python
def sync_kb():
    """Delete everything, re-index all active docs."""
    vector_store.delete_all()

    for doc in gcs.list_documents():
        if doc.status == 'active':
            chunks = chunk_document(doc)
            embeddings = embed_chunks(chunks)
            vector_store.insert(chunks, embeddings)
            bq.upsert_document(doc)
            bq.upsert_chunks(chunks)
```
- Pros: Simple, no state management
- Cons: Slow for large KB, re-embeds unchanged docs
- Best for: POC with ~20 docs

**Option B: Incremental Sync (Smart, for Production)**
```python
def sync_kb():
    """Only process changed documents."""
    for doc in gcs.list_documents():
        current_checksum = compute_checksum(doc.content)
        stored_checksum = bq.get_checksum(doc.doc_id)

        if current_checksum != stored_checksum:
            # Document changed - re-process
            vector_store.delete_by_doc_id(doc.doc_id)
            chunks = chunk_document(doc)
            embeddings = embed_chunks(chunks)
            vector_store.insert(chunks, embeddings)
            bq.upsert_document(doc, checksum=current_checksum)
            bq.upsert_chunks(chunks)
```
- Pros: Fast, only re-embeds changed docs
- Cons: Need checksum tracking
- Best for: Production with frequent updates

---

## 6. Change Propagation

### 6.1 Update Flow

```
Document Updated in GCS/Git
           │
           ▼
┌─────────────────────────────┐
│  Eventarc / Cloud Build     │
│  detects change             │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Ingestion Pipeline         │
│  1. Parse new version       │
│  2. Validate metadata       │
│  3. Compare with previous   │
│  4. Chunk & embed changes   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Update Strategy            │
│  - Additive: add new chunks │
│  - Replace: mark old expired│
│  - Delete: mark deprecated  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Coach System               │
│  - Next retrieval gets new  │
│  - No restart needed        │
│  - Hot reload ✓             │
└─────────────────────────────┘
```

### 6.2 Cache Invalidation

| Component | Strategy |
|-----------|----------|
| Vector Store | No cache (always fresh query) |
| Application | Optional cache with short TTL (5 min) |
| Embeddings | Hash-based cache (same content = reuse embedding) |

---

## 7. BQ Tables for KB Management

### 7.1 kb_documents (Document Registry + Raw Content)

```sql
CREATE TABLE cc_coach.kb_documents (
  -- Identity
  doc_id STRING NOT NULL,
  doc_type STRING NOT NULL,  -- policy, coaching, example, external_ref
  title STRING NOT NULL,

  -- Versioning
  version STRING NOT NULL,
  status STRING NOT NULL,  -- draft, active, superseded, deprecated
  superseded_by STRING,

  -- Scope (for filtering)
  business_lines ARRAY<STRING>,
  queues ARRAY<STRING>,
  regions ARRAY<STRING>,

  -- Source
  source_path STRING NOT NULL,  -- GCS path: gs://bucket/policy/POL-001.md
  checksum STRING NOT NULL,  -- SHA256 for change detection

  -- RAW CONTENT (store full doc for audit)
  raw_content STRING,  -- Full markdown content
  frontmatter JSON,    -- Parsed YAML frontmatter as JSON

  -- Processing info
  chunk_count INT64,
  indexed_at TIMESTAMP,

  -- Audit
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),

  -- Primary key
  PRIMARY KEY (doc_id, version) NOT ENFORCED
);
```

**Why store raw_content in BQ?**
- Single query to see full document for audit
- No need to fetch from GCS
- Can reconstruct any version
- Query-able (search within docs)

### 7.2 kb_chunks (Chunk Content + Metadata)

```sql
CREATE TABLE cc_coach.kb_chunks (
  -- Identity
  chunk_id STRING NOT NULL,  -- POL-002-v1.2.0-section-3
  doc_id STRING NOT NULL,
  doc_version STRING NOT NULL,

  -- Content
  section_path STRING,  -- "Prohibited Language > Threats > Legal"
  content STRING NOT NULL,  -- Chunk text
  token_count INT64,

  -- Vector store reference
  embedding_id STRING,  -- ID in Vertex AI Vector Search

  -- Status (derived from document)
  is_active BOOL NOT NULL,  -- true if doc is active (for easy filtering)

  -- Audit
  indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),

  -- Primary key
  PRIMARY KEY (chunk_id) NOT ENFORCED
);
```

### 7.3 kb_retrieval_log (Audit Trail)

```sql
CREATE TABLE cc_coach.kb_retrieval_log (
  retrieval_id STRING NOT NULL,
  conversation_id STRING NOT NULL,
  query_text STRING,
  retrieved_chunks ARRAY<STRUCT<
    chunk_id STRING,
    score FLOAT64,
    doc_id STRING,
    version STRING,
    section_path STRING
  >>,
  retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  coach_model_version STRING,
  prompt_version STRING
);
```

---

## 8. Automation & CI/CD

### 8.1 Git Workflow

```
feature/update-policy-002
        │
        ▼
   Pull Request
        │
   ┌────┴────┐
   │ Review  │  (Compliance team approval required)
   └────┬────┘
        │
        ▼
   Merge to main
        │
        ▼
   Cloud Build Trigger
        │
        ▼
   Ingestion Pipeline
        │
        ▼
   KB Updated (hot reload)
```

### 8.2 cloudbuild.yaml

```yaml
steps:
  # Step 1: Validate all documents
  - name: 'python:3.11'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        pip install pyyaml jsonschema
        python scripts/validate_documents.py documents/

  # Step 2: Sync to GCS (triggers Eventarc ingestion)
  - name: 'gcr.io/cloud-builders/gcloud'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        gsutil -m rsync -r -d documents/ gs://${_KB_BUCKET}/documents/

  # Step 3: Trigger ingestion pipeline
  - name: 'gcr.io/cloud-builders/gcloud'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        gcloud run jobs execute kb-ingestion-job \
          --region=${_REGION} \
          --wait
```

### 8.3 Scheduled Jobs

| Job | Schedule | Purpose |
|-----|----------|---------|
| Validation | Daily 6am | Check active docs for broken links, expired dates |
| Full Re-index | Weekly Sun 2am | Catch any drift, rebuild all embeddings |
| On-demand | Manual | CLI command for immediate re-index |

---

## 9. Monitoring & Observability

### 9.1 Metrics to Track

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| doc_count_by_status | Documents per status | - |
| chunk_count_by_type | Chunks per doc_type | - |
| retrieval_latency_p95 | 95th percentile latency | > 500ms |
| retrieval_relevance_avg | Average similarity score | < 0.7 |
| ingestion_failure_count | Failed ingestion runs | > 0 |

### 9.2 Alerts

- **Document expired without replacement**: Policy gap
- **Ingestion failure**: Pipeline broken
- **Retrieval latency spike**: Performance issue
- **Low relevance scores**: Content coverage gap
- **No retrievals for critical policy**: Missing citations

---

## 10. Implementation Phases

### Phase 1: POC (Current Focus)

| Item | Status |
|------|--------|
| Manual document creation | To do |
| Basic ingestion script | To do |
| Single vector store (Vertex AI) | To do |
| No versioning | - |

**Goal**: Verify RAG improves coaching quality

### Phase 2: MVP

| Item | Description |
|------|-------------|
| Git-based workflow | PR review for doc changes |
| Automated ingestion | Cloud Build trigger |
| Version tracking | effective_from/to dates |
| BQ metadata tables | kb_documents, kb_chunks |

### Phase 3: Production

| Item | Description |
|------|-------------|
| Full CI/CD | Validation, tests, staged rollout |
| Multi-version support | Time-travel retrieval |
| Audit logging | kb_retrieval_log |
| Monitoring & alerting | Cloud Monitoring dashboards |

---

## 11. Document Outlines (To Generate)

### 11.1 POL-001: Compliance Overview

```markdown
# Corporate Compliance Overview

## Purpose
Alignment with ASIC RG 96 and ACCC Debt Collection Guideline.

## Regulatory Framework
- Australian Consumer Law (ACL)
- National Consumer Credit Protection Act 2009
- ASIC Regulatory Guide 96

## Key Principles
1. Fair treatment of debtors
2. Transparent communication
3. Respect for debtor rights
4. Prohibition of harassment

## Reference Documents
- ASIC RG 96: [link]
- ACCC Guideline: [link]
```

### 11.2 POL-002: Prohibited Language

```markdown
# Prohibited Language Guidelines

## Threats of Legal Action
- Never threaten legal action unless debt is in legal proceedings
- Never imply imminent court action without basis

## Wage Garnishment
- Never threaten wage garnishment without court order
- Never imply employer will be contacted

## Harassment
- No repeated calls to pressure payment
- No calls before 7:30am or after 9pm
- No calls on public holidays

## Third Party Disclosure
- Never disclose debt to family members
- Never leave detailed voicemails about debt
```

### 11.3 COACH-001: Agent Playbook

```markdown
# Agent Playbook

## Call Opening
1. Greeting: "Hello, this is [Name] from [Company]"
2. Identity verification: "May I speak with [Customer Name]?"
3. Purpose: "I'm calling regarding your account"

## Handling Scenarios

### Hardship Request
1. Acknowledge: "I understand you're going through a difficult time"
2. Explore: "Can you tell me more about your situation?"
3. Options: "We have a hardship program that may help"
4. Action: "Let me explain the options available"

### Angry Customer
1. Listen: Allow them to express frustration
2. Acknowledge: "I hear your frustration"
3. Empathize: "I would feel the same way"
4. Solve: "Here's what I can do to help"

## Call Closing
1. Summarize: Recap agreed actions
2. Confirm: "Does that work for you?"
3. Next steps: Set clear expectations
4. Close: Professional sign-off
```

---

## 12. Next Steps

1. **Create document directory structure**
2. **Extract policy content from current prompt**
3. **Generate playbook documents**
4. **Extract example conversations from BQ**
5. **Build basic ingestion script for POC**
6. **Test RAG retrieval with coach agent**
