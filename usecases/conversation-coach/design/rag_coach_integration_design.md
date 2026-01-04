# RAG + Coach Integration Design

## Status: Draft - For Review

## Overview

This document describes how to integrate the RAG (Retrieval-Augmented Generation) pipeline with the Coaching service, and the GCP infrastructure required to support it.

---

## Table of Contents

1. [What is "GCP Setup"?](#what-is-gcp-setup)
2. [Current State](#current-state)
3. [Infrastructure Requirements (Terraform)](#infrastructure-requirements-terraform)
4. [RAG + Coach Integration](#rag--coach-integration)
5. [Implementation Plan](#implementation-plan)
6. [File Changes Summary](#file-changes-summary)

---

## What is "GCP Setup"?

"GCP Setup" refers to the cloud infrastructure that must be provisioned before the RAG pipeline can function. This includes:

| Component | Purpose | Current State |
|-----------|---------|---------------|
| **GCS Bucket** | Store active KB documents for Vertex AI indexing | Not created for KB |
| **Vertex AI Search Data Store** | Auto-index documents, provide semantic search | Not created |
| **Vertex AI Search App** | Search endpoint for querying | Not created |
| **BQ Tables** | `kb_documents`, `kb_retrieval_log` for metadata/audit | SQL ready, not applied |

### Why These Are Needed

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     RAG INFRASTRUCTURE REQUIREMENTS                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   LOCAL                           GCP INFRASTRUCTURE                        │
│   ─────                           ──────────────────                        │
│                                                                             │
│   documents/                                                                │
│   ├── policy/                     ┌─────────────────────┐                  │
│   ├── coaching/   ───cc ingest───►│  GCS Bucket         │                  │
│   └── examples/                   │  gs://xxx-kb-docs/  │                  │
│                                   └────────┬────────────┘                  │
│                                            │                                │
│                                            ▼                                │
│                                   ┌─────────────────────┐                  │
│                                   │  Vertex AI Search   │                  │
│                                   │  Data Store         │◄── Auto-indexes  │
│                                   └────────┬────────────┘                  │
│                                            │                                │
│                                            ▼                                │
│   cc-coach rag search ───────────►┌─────────────────────┐                  │
│   "hardship rules"                │  Vertex AI Search   │                  │
│                                   │  App (query API)    │                  │
│                                   └─────────────────────┘                  │
│                                                                             │
│   Metadata/Audit:                                                           │
│                                   ┌─────────────────────┐                  │
│   cc ingest ─────────────────────►│  BigQuery           │                  │
│   (also logs retrievals)          │  kb_documents       │                  │
│                                   │  kb_retrieval_log   │                  │
│                                   └─────────────────────┘                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Current State

### Already Implemented (Code)

| Component | Location | Status |
|-----------|----------|--------|
| RAG Config | `cc_coach/rag/config.py` | ✅ Done |
| RAG Parser | `cc_coach/rag/parser.py` | ✅ Done |
| RAG Metadata | `cc_coach/rag/metadata.py` | ✅ Done |
| RAG Ingest | `cc_coach/rag/ingest.py` | ✅ Done |
| RAG Retriever | `cc_coach/rag/retriever.py` | ✅ Done |
| CLI Commands | `cc_coach/cli.py` (rag subcommand) | ✅ Done |
| Unit Tests | `tests/test_rag.py` | ✅ Done (39 tests) |
| BQ Schema SQL | `sql/create_kb_tables.sql` | ✅ Done |

### Not Yet Implemented

| Component | Location | Status |
|-----------|----------|--------|
| Terraform for RAG infra | `artifacts/terraform/rag_knowledge_base.tf` | ❌ Not done |
| Coach + RAG integration | `cc_coach/services/coaching.py` | ❌ Not done |
| Updated coaching prompts | `cc_coach/prompts/` | ❌ Not done |

### Existing Terraform

```
artifacts/terraform/
├── gcs_dev_data.tf      # Dev bucket for conversation data
├── bigquery.tf          # BQ dataset + existing tables
├── ccai_insights.tf     # CCAI Insights config
└── (need) rag_knowledge_base.tf  # NEW: KB infrastructure
```

---

## Infrastructure Requirements (Terraform)

All infrastructure should be managed via Terraform in `artifacts/terraform/`.

### New Terraform File: `rag_knowledge_base.tf`

```hcl
# =============================================================================
# Conversation Coach - RAG Knowledge Base Infrastructure
# =============================================================================
# Purpose: Infrastructure for RAG pipeline
# Components:
#   - GCS bucket for KB documents (active docs only)
#   - Vertex AI Search Data Store (auto-indexes GCS)
#   - Vertex AI Search App (query endpoint)
#   - BigQuery tables for metadata and audit
# =============================================================================

# -----------------------------------------------------------------------------
# Enable Required APIs
# -----------------------------------------------------------------------------

resource "google_project_service" "discoveryengine" {
  project            = var.project_id
  service            = "discoveryengine.googleapis.com"
  disable_on_destroy = false
}

# -----------------------------------------------------------------------------
# GCS Bucket for KB Documents
# -----------------------------------------------------------------------------
# Only active documents are stored here (synced by cc ingest)
# Vertex AI Search auto-indexes this bucket

resource "google_storage_bucket" "kb_documents" {
  name          = "${var.project_id}-cc-kb-docs"
  project       = var.project_id
  location      = var.kb_location  # e.g., "australia-southeast1"
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = false  # We handle versioning via immutable artifacts
  }

  labels = {
    environment = var.environment
    managed_by  = "terraform"
    usecase     = "conversation-coach"
    component   = "rag-knowledge-base"
  }
}

# -----------------------------------------------------------------------------
# Vertex AI Search Data Store
# -----------------------------------------------------------------------------
# Note: As of 2025, Terraform support for Vertex AI Search is limited.
# Data Store may need to be created via gcloud or console, then imported.
#
# gcloud alpha discovery-engine data-stores create cc-kb-datastore \
#   --location=global \
#   --display-name="Conversation Coach KB" \
#   --industry-vertical=GENERIC \
#   --content-config=CONTENT_REQUIRED \
#   --solution-types=SOLUTION_TYPE_SEARCH

# Placeholder for when Terraform support improves:
# resource "google_discovery_engine_data_store" "kb" {
#   location         = "global"
#   data_store_id    = "cc-kb-datastore"
#   display_name     = "Conversation Coach KB"
#   industry_vertical = "GENERIC"
#   content_config   = "CONTENT_REQUIRED"
#   solution_types   = ["SOLUTION_TYPE_SEARCH"]
# }

# -----------------------------------------------------------------------------
# BigQuery Tables for KB Metadata
# -----------------------------------------------------------------------------

resource "google_bigquery_table" "kb_documents" {
  dataset_id = google_bigquery_dataset.conversation_coach.dataset_id
  table_id   = "kb_documents"
  project    = var.project_id

  description = "Knowledge base document registry - metadata, versions, audit trail"

  schema = jsonencode([
    { name = "uuid", type = "STRING", mode = "REQUIRED", description = "Deterministic UUID (hash of file_path + version)" },
    { name = "doc_id", type = "STRING", mode = "REQUIRED", description = "Human-readable ID: POL-002" },
    { name = "doc_type", type = "STRING", mode = "REQUIRED", description = "policy, coaching, example, external" },
    { name = "title", type = "STRING", mode = "REQUIRED" },
    { name = "version", type = "STRING", mode = "REQUIRED", description = "Semantic version: 1.0.0" },
    { name = "file_path", type = "STRING", mode = "REQUIRED", description = "Relative path from documents/" },
    { name = "status", type = "STRING", mode = "REQUIRED", description = "active, superseded, retired, deleted, draft" },
    { name = "status_reason", type = "STRING", mode = "NULLABLE" },
    { name = "superseded_by", type = "STRING", mode = "NULLABLE", description = "UUID of replacement doc" },
    { name = "status_changed_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "business_lines", type = "STRING", mode = "REPEATED" },
    { name = "queues", type = "STRING", mode = "REPEATED" },
    { name = "regions", type = "STRING", mode = "REPEATED" },
    { name = "raw_content", type = "STRING", mode = "REQUIRED", description = "Full markdown including frontmatter" },
    { name = "checksum", type = "STRING", mode = "REQUIRED", description = "SHA-256 for change detection" },
    { name = "author", type = "STRING", mode = "NULLABLE" },
    { name = "approved_by", type = "STRING", mode = "NULLABLE" },
    { name = "effective_date", type = "DATE", mode = "NULLABLE" },
    { name = "expiry_date", type = "DATE", mode = "NULLABLE" },
    { name = "last_reviewed", type = "DATE", mode = "NULLABLE" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "updated_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])

  labels = {
    component = "rag-knowledge-base"
  }
}

resource "google_bigquery_table" "kb_retrieval_log" {
  dataset_id = google_bigquery_dataset.conversation_coach.dataset_id
  table_id   = "kb_retrieval_log"
  project    = var.project_id

  description = "Audit log for RAG retrievals - tracks which docs were used for each coaching"

  time_partitioning {
    type  = "DAY"
    field = "retrieved_at"
  }

  schema = jsonencode([
    { name = "retrieval_id", type = "STRING", mode = "REQUIRED" },
    { name = "conversation_id", type = "STRING", mode = "REQUIRED" },
    { name = "query_text", type = "STRING", mode = "NULLABLE" },
    {
      name = "retrieved_docs",
      type = "RECORD",
      mode = "REPEATED",
      fields = [
        { name = "uuid", type = "STRING" },
        { name = "doc_id", type = "STRING" },
        { name = "version", type = "STRING" },
        { name = "section", type = "STRING" },
        { name = "snippet", type = "STRING" },
        { name = "relevance_score", type = "FLOAT64" },
      ]
    },
    { name = "coach_model_version", type = "STRING", mode = "NULLABLE" },
    { name = "prompt_version", type = "STRING", mode = "NULLABLE" },
    { name = "business_line", type = "STRING", mode = "NULLABLE" },
    { name = "retrieved_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])

  labels = {
    component = "rag-knowledge-base"
  }
}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "kb_location" {
  description = "Location for KB resources (GCS bucket)"
  type        = string
  default     = "australia-southeast1"
}
```

### Terraform Execution Plan

```bash
# 1. Navigate to terraform directory
cd usecases/conversation-coach/artifacts/terraform

# 2. Initialize (if new providers)
terraform init

# 3. Plan changes
terraform plan -out=tfplan

# 4. Apply
terraform apply tfplan
```

### Manual Setup Required (Vertex AI Search)

Vertex AI Search Data Store/App creation is not fully supported in Terraform as of early 2025. Use gcloud or console:

```bash
# Create Data Store
gcloud alpha discovery-engine data-stores create cc-kb-datastore \
  --location=global \
  --display-name="Conversation Coach KB" \
  --industry-vertical=GENERIC \
  --content-config=CONTENT_REQUIRED \
  --solution-types=SOLUTION_TYPE_SEARCH

# Link GCS bucket (after bucket is created by Terraform)
gcloud alpha discovery-engine data-stores update cc-kb-datastore \
  --location=global \
  --add-gcs-source=gs://${PROJECT_ID}-cc-kb-docs/kb/

# Create Search App
gcloud alpha discovery-engine apps create cc-kb-search \
  --location=global \
  --display-name="Conversation Coach KB Search" \
  --data-store-ids=cc-kb-datastore
```

---

## RAG + Coach Integration

### Current Coaching Flow (Without RAG)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CURRENT COACHING FLOW                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. cc-coach coach generate <conversation_id>                              │
│                                                                             │
│   2. Fetch from BQ:                                                         │
│      - ci_enrichment (sentiment, entities, phrase matches)                  │
│      - conversation_registry (metadata)                                     │
│                                                                             │
│   3. Build CoachingInput:                                                   │
│      - Transcript                                                           │
│      - CI analysis results                                                  │
│      - Metadata (agent, queue, etc.)                                        │
│                                                                             │
│   4. Generate with Gemini:                                                  │
│      System prompt + CoachingInput → CoachingOutput                         │
│                                                                             │
│   5. Save to BQ: coach_analysis table                                       │
│                                                                             │
│   LIMITATION: No access to policy/coaching documents                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Enhanced Coaching Flow (With RAG)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     ENHANCED COACHING FLOW (WITH RAG)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. cc-coach coach generate <conversation_id>                              │
│                                                                             │
│   2. Fetch from BQ:                                                         │
│      - ci_enrichment (sentiment, entities, phrase matches)                  │
│      - conversation_registry (metadata)                                     │
│                                                                             │
│   3. Extract topics from conversation:                                      │
│      ┌─────────────────────────────────────────────────────────────────┐   │
│      │  TOPIC EXTRACTION:                                               │   │
│      │  - From CI entities: "hardship", "payment plan"                  │   │
│      │  - From CI phrase matches: "threat_language", "prohibited_terms" │   │
│      │  - From transcript keywords: "legal action", "can't pay"         │   │
│      │  - From metadata: business_line → "COLLECTIONS"                  │   │
│      └─────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   4. Query RAG for relevant documents:     ◄─── NEW STEP                   │
│      ┌─────────────────────────────────────────────────────────────────┐   │
│      │  RAGRetriever.get_context_for_coaching(                          │   │
│      │      topics=["hardship rules", "prohibited language"],           │   │
│      │      conversation_id=...,                                        │   │
│      │      business_line="COLLECTIONS"                                 │   │
│      │  )                                                                │   │
│      │                                                                   │   │
│      │  Returns:                                                         │   │
│      │  - context: Formatted document snippets with citations           │   │
│      │  - docs: List of RetrievedDocument for audit                     │   │
│      └─────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   5. Build CoachingInput with RAG context:                                  │
│      - Transcript                                                           │
│      - CI analysis results                                                  │
│      - Metadata                                                             │
│      - RAG context (policy/coaching snippets)  ◄─── NEW                    │
│                                                                             │
│   6. Generate with Gemini:                                                  │
│      System prompt + CoachingInput + RAG Context → CoachingOutput           │
│                                                                             │
│   7. Save to BQ:                                                            │
│      - coach_analysis table                                                 │
│      - Include citations in output  ◄─── NEW                               │
│                                                                             │
│   BENEFIT: Coaching grounded in actual policy documents                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Code Changes Required

#### 1. Topic Extraction (New Module)

```python
# cc_coach/rag/topic_extractor.py

class TopicExtractor:
    """Extract topics from conversation for RAG retrieval."""

    def extract_topics(
        self,
        ci_enrichment: dict,
        transcript: list[dict],
        metadata: dict,
    ) -> list[str]:
        """
        Extract search topics from conversation data.

        Sources:
        - CI entities (high salience)
        - CI phrase matcher hits
        - Transcript keywords (TF-IDF or LLM extraction)
        - Business line context

        Returns:
            List of topic strings for RAG queries
        """
        topics = []

        # From CI entities
        entities = ci_enrichment.get("entities", {})
        for entity_id, entity in entities.items():
            if entity.get("salience", 0) > 0.5:
                topics.append(entity.get("displayName", ""))

        # From phrase matches
        phrase_matches = ci_enrichment.get("phrase_matches", [])
        for match in phrase_matches:
            # Map phrase matcher ID to topic
            matcher_id = match.get("phrase_matcher_id", "")
            if "threat" in matcher_id.lower():
                topics.append("prohibited language threats")
            elif "hardship" in matcher_id.lower():
                topics.append("hardship provisions")
            # ... more mappings

        # From business line
        business_line = metadata.get("business_line", "")
        if business_line:
            topics.append(f"{business_line.lower()} compliance rules")

        return list(set(topics))  # Deduplicate
```

#### 2. Update Coaching Service

```python
# cc_coach/services/coaching.py - modifications

from cc_coach.rag import RAGConfig, RAGRetriever
from cc_coach.rag.topic_extractor import TopicExtractor

class CoachingOrchestrator:
    def __init__(self, model: str = None, use_rag: bool = True):
        self.use_rag = use_rag
        if use_rag:
            self.rag_config = RAGConfig.from_env()
            self.rag_retriever = RAGRetriever(self.rag_config)
            self.topic_extractor = TopicExtractor()

    def generate_coaching(self, conversation_id: str) -> CoachingOutput:
        # ... existing fetch code ...

        # NEW: Extract topics and retrieve context
        rag_context = ""
        retrieved_docs = []

        if self.use_rag:
            topics = self.topic_extractor.extract_topics(
                ci_data, transcript, registry_data
            )

            if topics:
                rag_context, retrieved_docs = self.rag_retriever.get_context_for_coaching(
                    conversation_topics=topics,
                    conversation_id=conversation_id,
                    business_line=registry_data.get("business_line"),
                )

        # Build input with RAG context
        input_data = self._build_coaching_input(
            conversation_id, ci_data, registry_data,
            rag_context=rag_context  # NEW parameter
        )

        # ... existing generation code ...

        # Include citations in output
        output.citations = [doc.to_citation() for doc in retrieved_docs]

        return output
```

#### 3. Update Coaching Prompts

```python
# cc_coach/prompts/coach_system_prompt.py - additions

RAG_CONTEXT_SECTION = """
## Relevant Policy & Coaching Documents

The following excerpts are from our official policy and coaching documents.
Use these to ground your coaching feedback in specific, verifiable guidelines.

{rag_context}

When referencing these documents, cite them as:
"According to [DOC_ID] v[VERSION] (Section: [SECTION])..."
"""
```

#### 4. Update Output Schema

```python
# cc_coach/schemas/coaching_output.py - additions

class CoachingOutput(BaseModel):
    # ... existing fields ...

    # NEW: Citations from RAG
    citations: list[str] = Field(
        default_factory=list,
        description="Document citations used for coaching feedback"
    )

    rag_context_used: bool = Field(
        default=False,
        description="Whether RAG context was included in generation"
    )
```

---

## Implementation Plan

### Phase 1: Infrastructure (Terraform)

1. Create `rag_knowledge_base.tf` with:
   - GCS bucket for KB documents
   - BQ tables (`kb_documents`, `kb_retrieval_log`)

2. Apply Terraform:
   ```bash
   cd artifacts/terraform
   terraform plan -out=tfplan
   terraform apply tfplan
   ```

3. Manual: Create Vertex AI Search Data Store + App via gcloud/console

4. Set environment variables:
   ```bash
   export RAG_GCS_BUCKET=${PROJECT_ID}-cc-kb-docs
   export RAG_DATA_STORE_ID=cc-kb-datastore
   ```

### Phase 2: Document Ingestion

1. Run initial ingestion:
   ```bash
   cc-coach rag ingest --path ../../../documents
   ```

2. Verify in BQ:
   ```sql
   SELECT doc_id, version, status, title
   FROM conversation_coach.kb_documents
   WHERE status = 'active'
   ```

3. Verify in GCS:
   ```bash
   gsutil ls gs://${PROJECT_ID}-cc-kb-docs/kb/
   ```

4. Wait for Vertex AI Search to index (~5-10 minutes)

5. Test retrieval:
   ```bash
   cc-coach rag search "hardship rules"
   ```

### Phase 3: Coach Integration

1. Create `cc_coach/rag/topic_extractor.py`

2. Update `cc_coach/services/coaching.py`:
   - Add RAG retrieval step
   - Include context in prompt
   - Add citations to output

3. Update prompts in `cc_coach/prompts/`

4. Update output schema

5. Add tests for integration

6. Test end-to-end:
   ```bash
   cc-coach coach generate <conversation_id> --verbose
   ```

---

## File Changes Summary

### New Files

| File | Description |
|------|-------------|
| `artifacts/terraform/rag_knowledge_base.tf` | Terraform for RAG infrastructure |
| `cc_coach/rag/topic_extractor.py` | Extract topics from conversation for RAG |

### Modified Files

| File | Changes |
|------|---------|
| `cc_coach/services/coaching.py` | Add RAG retrieval, include context in prompt |
| `cc_coach/prompts/coach_system_prompt.py` | Add RAG context section |
| `cc_coach/schemas/coaching_output.py` | Add citations field |

### Environment Variables Required

```bash
# For RAG pipeline
export GCP_PROJECT_ID=your-project
export RAG_GCS_BUCKET=your-project-cc-kb-docs
export RAG_DATA_STORE_ID=cc-kb-datastore

# Optional
export GCP_LOCATION=australia-southeast1
export BQ_DATASET=conversation_coach
```

---

## Cost Considerations

| Component | Pricing Model | Est. Demo Cost |
|-----------|---------------|----------------|
| GCS Bucket | $0.02/GB/month | < $0.01 (< 1MB docs) |
| Vertex AI Search | ~$0.005/query | ~$0.50 (100 queries) |
| BigQuery | $5/TB queried | < $0.01 (small queries) |
| **Total** | | **< $1/month demo** |

---

## Open Questions

1. **Topic extraction approach**: Simple keyword matching vs. LLM-based extraction?
2. **Maximum context length**: How much RAG context to include in prompt?
3. **Relevance threshold**: What minimum score to include documents?
4. **Citation format**: How verbose should citations be in output?

---

## Appendix: Vertex AI Search Terraform Status

As of January 2025, Terraform support for Vertex AI Search (Discovery Engine) is limited:

- `google_discovery_engine_data_store` - Available but may not support all features
- `google_discovery_engine_search_engine` - Limited support
- GCS source linking may require API calls

Recommend:
1. Use Terraform for what's supported (GCS, BQ)
2. Use gcloud/API for Vertex AI Search components
3. Document manual steps clearly
4. Re-evaluate Terraform support in future

Reference: [Terraform Google Provider - Discovery Engine](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/discovery_engine_data_store)
