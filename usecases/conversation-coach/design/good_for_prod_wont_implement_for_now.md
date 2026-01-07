# Production Features - Deferred for Now

This document captures CI features that are valuable for production scale but won't be implemented in the current MVP phase due to training data requirements.

---

## 1. CI Quality AI / QA Scorecard

### What It Does
Auto-answers custom questions for each conversation, producing consistent quality scores.

### How It Works
1. You create a scorecard with up to 50 questions
2. You provide 2,000+ manually labeled conversations as training examples
3. CI calibrates the model (4-8 hours)
4. CI auto-answers questions for new conversations

### Sample Scorecard Configuration

```yaml
Scorecard: "Collections Compliance v1"

Questions:
  - id: Q1
    text: "Did agent verify customer identity?"
    type: yes_no
    tag: Compliance

  - id: Q2
    text: "Did agent inform customer of right to dispute?"
    type: yes_no
    tag: Compliance

  - id: Q3
    text: "Did agent mention hardship options?"
    type: yes_no
    tag: Compliance

  - id: Q4
    text: "Did agent use threatening language?"
    type: yes_no
    tag: Compliance

  - id: Q5
    text: "Rate agent's empathy"
    type: scale_1_5
    tag: Customer_Experience

  - id: Q6
    text: "Was the call resolved?"
    type: multiple_choice
    choices: [Yes, No, Partial]
    tag: Resolution

  - id: Q7
    text: "Did agent follow proper closing script?"
    type: yes_no
    tag: Process

Tags:
  - Compliance: Q1, Q2, Q3, Q4
  - Customer_Experience: Q5
  - Resolution: Q6, Q7
```

### Sample Output (Per-Conversation)

```json
{
  "conversation_id": "a1b2c3d4-toxic-agent-test-0001",

  "qa_scorecard": {
    "scorecard_name": "Collections Compliance v1",
    "overall_score": 2.1,

    "answers": [
      {
        "question_id": "Q1",
        "question": "Did agent verify customer identity?",
        "answer": "Yes",
        "confidence": 0.92,
        "tag": "Compliance"
      },
      {
        "question_id": "Q2",
        "question": "Did agent inform customer of right to dispute?",
        "answer": "No",
        "confidence": 0.88,
        "tag": "Compliance"
      },
      {
        "question_id": "Q3",
        "question": "Did agent mention hardship options?",
        "answer": "No",
        "confidence": 0.95,
        "tag": "Compliance"
      },
      {
        "question_id": "Q4",
        "question": "Did agent use threatening language?",
        "answer": "Yes",
        "confidence": 0.97,
        "tag": "Compliance"
      },
      {
        "question_id": "Q5",
        "question": "Rate agent's empathy",
        "answer": "1",
        "confidence": 0.85,
        "tag": "Customer_Experience"
      },
      {
        "question_id": "Q6",
        "question": "Was the call resolved?",
        "answer": "No",
        "confidence": 0.91,
        "tag": "Resolution"
      }
    ],

    "tag_scores": {
      "Compliance": 1.5,
      "Customer_Experience": 1.0,
      "Resolution": 2.0
    }
  }
}
```

### Requirements
- **Training Data**: 2,000+ conversations with manual labels for each question
- **Calibration Time**: 4-8 hours per scorecard
- **Maintenance**: Re-calibration needed when questions change

### Why Deferred
- We have ~8 test conversations, need 2,000+ for training
- Manual labeling effort required
- ADK LLM coach can do similar scoring without training data

### When to Implement
- When you have accumulated 2,000+ conversations
- When you want deterministic scoring (same input = same output every time)
- When you need to reduce LLM costs at high volume
- When audit requires consistent, reproducible scores

### Migration Path
1. Accumulate conversations over time
2. Use ADK coach outputs as initial labels
3. QA team reviews/corrects labels
4. Train CI Scorecard on corrected labels
5. CI Scorecard handles first-pass scoring
6. ADK Coach handles edge cases + detailed coaching

---

## 2. CI Topic Model

### What It Does
Automatically categorizes conversations by call driver/topic.

### How It Works
1. You provide 1,000+ conversations (minimum)
2. CI trains a topic model (can take hours)
3. CI auto-generates topic names via Gemini
4. New conversations get topic labels

### Sample Topics (Auto-Generated)

```
Topic Model: "Collections Call Drivers v1"

Generated Topics:
├── Payment Plan Request (32%)
│   Description: "Customer inquiring about setting up payment arrangements"
│
├── Hardship Claim (28%)
│   Description: "Customer reporting financial difficulty due to job loss, medical, etc."
│
├── Dispute/Not My Debt (18%)
│   Description: "Customer disputing the validity of the debt"
│
├── Account Inquiry (12%)
│   Description: "Customer asking about balance, payment history, or account status"
│
└── Complaint (10%)
    Description: "Customer expressing dissatisfaction with service or treatment"
```

### Sample Output (Per-Conversation)

```json
{
  "conversation_id": "a1b2c3d4-toxic-agent-test-0001",

  "topic_model": {
    "model_name": "Collections Call Drivers v1",
    "primary_topic": {
      "name": "Hardship Claim",
      "confidence": 0.85
    },
    "secondary_topics": [
      {"name": "Payment Plan Request", "confidence": 0.45},
      {"name": "Complaint", "confidence": 0.30}
    ]
  }
}
```

### Requirements
- **Training Data**: 1,000+ conversations minimum (10,000 recommended)
- **Training Time**: Several hours
- **Granularity Options**: more_coarse, coarse, standard, fine, more_fine

### Why Deferred
- We have ~8 test conversations, need 1,000+ minimum
- Primary value is aggregate analytics (dashboard), not per-conversation coaching
- ADK LLM can categorize calls without training data

### When to Implement
- When you have 1,000+ conversations
- When you want aggregate call driver analytics on dashboard
- When you need trend analysis ("Hardship calls up 20% this week")

### Use Cases (When Implemented)

**Dashboard Analytics**:
```
┌─────────────────────────────────────────────────────────────────┐
│  Top Call Drivers This Week                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Payment Plans ████████████████████████████████ 32%             │
│  Hardship      ████████████████████████████ 28%                 │
│  Disputes      ██████████████████ 18%                           │
│  Inquiries     ████████████ 12%                                 │
│  Complaints    ██████████ 10%                                   │
│                                                                  │
│  Trend: Hardship calls ↑ 20% vs last week                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Weekly Coach Context**:
```
"This week, 40% of your calls were hardship-related.
Consider reviewing the hardship handling playbook."
```

---

## 3. Comparison: Current vs Future CI Features

| Feature | Current (Phase 1) | Future (Prod) |
|---------|-------------------|---------------|
| **Sentiment** | ✅ Enabled | ✅ Keep |
| **Summary** | ✅ Enabled | ✅ Keep |
| **Entities** | ✅ Enabled | ✅ Keep |
| **Phrase Matcher** | 🔜 Adding | ✅ Keep |
| **QA Scorecard** | ❌ Deferred | ✅ Add at 2000+ convos |
| **Topic Model** | ❌ Deferred | ✅ Add at 1000+ convos |

---

## 4. Future Schema Fields (When Implemented)

### ci_enrichment table additions

```python
# Add when QA Scorecard is implemented
("qa_scorecard_name", "STRING"),
("qa_overall_score", "FLOAT"),
("qa_answers", "JSON"),  # Full question/answer pairs
("qa_tag_scores", "JSON"),  # Scores by tag (Compliance, CX, etc.)

# Add when Topic Model is implemented
("topic_model_name", "STRING"),
("primary_topic", "STRING"),
("primary_topic_confidence", "FLOAT"),
("secondary_topics", "JSON"),  # Array of {topic, confidence}
```

---

## 5. Documentation Links

- [Quality AI Basics](https://cloud.google.com/contact-center/insights/docs/qai-basics)
- [Quality AI Setup Guide](https://cloud.google.com/contact-center/insights/docs/qai-setup-guide)
- [Quality AI Best Practices](https://cloud.google.com/contact-center/insights/docs/qai-best-practices)
- [Topic Modeling Overview](https://cloud.google.com/contact-center/insights/docs/topic-modeling-overview)
- [Topic Modeling How-To](https://cloud.google.com/contact-center/insights/docs/topic-modeling)

---

## 6. Coach Analysis Versioning & Data Lineage

### Problem Statement

Currently, `coach_analysis` uses simple INSERT, allowing multiple rows per `conversation_id`:

```sql
-- Current: Same conversation analyzed multiple times creates duplicates
SELECT conversation_id, COUNT(*)
FROM coach_analysis
GROUP BY 1
HAVING COUNT(*) > 1

-- Result: a1b2c3d4-toxic-agent-test-0001 has 9 rows!
```

**Issues:**
1. Aggregations may double-count (6 "calls" when it's 1 conversation analyzed 6 times)
2. No clear "latest" indicator
3. Can't track why re-analysis happened (model change? prompt update? KB update?)
4. No audit trail linking old → new analysis

### Design Decision

**Keep all analyses (append-only) + mark latest** for:
- Full audit trail
- Model/prompt version comparison
- Compliance tracking
- A/B testing capability

### Recommended Schema Changes

#### 6.1 New Columns for `coach_analysis`

```sql
-- Add these columns to coach_analysis table
ALTER TABLE coach_analysis ADD COLUMN IF NOT EXISTS
  analysis_id STRING;              -- UUID, unique per analysis run

ALTER TABLE coach_analysis ADD COLUMN IF NOT EXISTS
  superseded_by STRING;            -- NULL = current, else analysis_id of replacement

ALTER TABLE coach_analysis ADD COLUMN IF NOT EXISTS
  superseded_at TIMESTAMP;         -- When this analysis was superseded

ALTER TABLE coach_analysis ADD COLUMN IF NOT EXISTS
  is_current BOOLEAN DEFAULT TRUE; -- Denormalized for fast queries

ALTER TABLE coach_analysis ADD COLUMN IF NOT EXISTS
  reanalysis_reason STRING;        -- "prompt_update", "model_update", "kb_update", "manual"

ALTER TABLE coach_analysis ADD COLUMN IF NOT EXISTS
  rag_kb_snapshot_id STRING;       -- Optional: KB version identifier

ALTER TABLE coach_analysis ADD COLUMN IF NOT EXISTS
  rag_docs_retrieved JSON;         -- Exact documents used in RAG retrieval
```

#### 6.2 New Column for `conversation_registry`

```sql
-- Add pointer to latest analysis for fast lookup
ALTER TABLE conversation_registry ADD COLUMN IF NOT EXISTS
  latest_analysis_id STRING;       -- FK to coach_analysis.analysis_id
```

#### 6.3 Create View for Latest Analyses

```sql
CREATE OR REPLACE VIEW `{project}.{dataset}.coach_analysis_latest` AS
SELECT *
FROM `{project}.{dataset}.coach_analysis`
WHERE is_current = TRUE;

-- Alternative using superseded_by:
-- WHERE superseded_by IS NULL;
```

### Schema Diagram

```
coach_analysis (append-only audit table)
├── analysis_id (STRING, REQUIRED)     -- UUID, unique per analysis run
├── conversation_id (STRING, REQUIRED) -- FK to conversation
│
│ -- Versioning & Provenance
├── model_version (STRING)             -- "gemini-2.5-flash" (existing)
├── prompt_version (STRING)            -- "v2.1.0" (existing)
├── rag_context_used (BOOLEAN)         -- (existing)
├── rag_kb_snapshot_id (STRING)        -- NEW: KB snapshot version
├── rag_docs_retrieved (JSON)          -- NEW: [{doc_id, version, chunk_id, relevance}]
│
│ -- Lifecycle & Chain
├── analyzed_at (TIMESTAMP)            -- (existing)
├── superseded_by (STRING)             -- NEW: NULL = current, else analysis_id
├── superseded_at (TIMESTAMP)          -- NEW: When superseded
├── is_current (BOOLEAN)               -- NEW: Denormalized for perf
├── reanalysis_reason (STRING)         -- NEW: Why re-analyzed
│
│ -- Scores & Evidence (existing)
├── overall_score, empathy_score, ...
├── assessments (RECORD, REPEATED)
└── ...

conversation_registry
├── conversation_id (STRING)
├── status (STRING)                    -- ENRICHED, COACHED, etc.
├── latest_analysis_id (STRING)        -- NEW: FK to coach_analysis.analysis_id
└── ...

coach_analysis_latest (VIEW)
└── SELECT * FROM coach_analysis WHERE is_current = TRUE
```

### Workflow: Re-Analysis

When a conversation needs re-analysis (prompt update, model change, manual request):

```python
def reanalyze_conversation(conversation_id: str, reason: str):
    """Re-analyze a conversation, preserving audit trail."""

    # 1. Generate new analysis_id
    new_analysis_id = str(uuid.uuid4())

    # 2. Find current analysis
    current = bq.query("""
        SELECT analysis_id
        FROM coach_analysis
        WHERE conversation_id = @conv_id AND is_current = TRUE
    """)

    # 3. Mark current as superseded
    if current:
        bq.query("""
            UPDATE coach_analysis
            SET
                is_current = FALSE,
                superseded_by = @new_id,
                superseded_at = CURRENT_TIMESTAMP()
            WHERE analysis_id = @old_id
        """, params={
            "new_id": new_analysis_id,
            "old_id": current.analysis_id
        })

    # 4. Run new analysis
    result = coach.analyze_conversation(conversation_id)

    # 5. Insert new analysis with audit fields
    row = {
        "analysis_id": new_analysis_id,
        "conversation_id": conversation_id,
        "is_current": True,
        "superseded_by": None,
        "reanalysis_reason": reason,  # "prompt_update", "model_update", etc.
        "rag_docs_retrieved": [...],  # From RAG retrieval
        ...result
    }
    bq.insert_rows_json("coach_analysis", [row])

    # 6. Update registry pointer
    bq.query("""
        UPDATE conversation_registry
        SET latest_analysis_id = @analysis_id
        WHERE conversation_id = @conv_id
    """)
```

### Query Patterns

```sql
-- Get latest analysis for a conversation
SELECT * FROM coach_analysis_latest WHERE conversation_id = 'xxx';

-- Or via registry (faster, single lookup)
SELECT ca.*
FROM conversation_registry cr
JOIN coach_analysis ca ON cr.latest_analysis_id = ca.analysis_id
WHERE cr.conversation_id = 'xxx';

-- Get analysis history for a conversation
SELECT analysis_id, analyzed_at, model_version, prompt_version,
       overall_score, reanalysis_reason, superseded_by
FROM coach_analysis
WHERE conversation_id = 'xxx'
ORDER BY analyzed_at DESC;

-- Compare old vs new analysis
SELECT
    old.overall_score as old_score,
    new.overall_score as new_score,
    new.reanalysis_reason
FROM coach_analysis old
JOIN coach_analysis new ON old.superseded_by = new.analysis_id
WHERE old.conversation_id = 'xxx';

-- Find all analyses using a specific model version
SELECT * FROM coach_analysis WHERE model_version = 'gemini-2.5-flash';

-- Find analyses that used a specific RAG document
SELECT * FROM coach_analysis
WHERE JSON_VALUE(rag_docs_retrieved, '$[0].doc_id') = 'POL-002';
```

### Aggregation Updates

**IMPORTANT:** All aggregations must use the `coach_analysis_latest` view:

```sql
-- Daily summary (CORRECT - uses latest only)
SELECT agent_id, DATE(analyzed_at), AVG(overall_score)
FROM coach_analysis_latest  -- ← Use view, not base table
WHERE DATE(analyzed_at) = @date
GROUP BY 1, 2;

-- Weekly summary (CORRECT)
SELECT agent_id, AVG(overall_score), COUNT(*)
FROM coach_analysis_latest
WHERE DATE(analyzed_at) BETWEEN @week_start AND @week_end
GROUP BY agent_id;
```

### Files to Modify (Implementation)

| File | Change |
|------|--------|
| `cc_coach/schemas/coach_analysis.json` | Add analysis_id, superseded_by, is_current, reanalysis_reason, rag_docs_retrieved |
| `cc_coach/services/coaching.py` | Update _store_coaching_result() to generate analysis_id, handle re-analysis |
| `cc_coach/services/aggregation.py` | Change FROM coach_analysis → FROM coach_analysis_latest |
| `cc_coach/services/summary.py` | Change FROM coach_analysis → FROM coach_analysis_latest |
| Terraform/DDL | Create coach_analysis_latest view |
| Terraform/DDL | Alter conversation_registry to add latest_analysis_id |

### Migration Strategy

For existing test data with duplicates:

```sql
-- Step 1: Backfill analysis_id for all rows
UPDATE coach_analysis
SET analysis_id = GENERATE_UUID()
WHERE analysis_id IS NULL;

-- Step 2: Mark latest per conversation_id as current
WITH ranked AS (
    SELECT
        analysis_id,
        ROW_NUMBER() OVER (PARTITION BY conversation_id ORDER BY analyzed_at DESC) as rn
    FROM coach_analysis
)
UPDATE coach_analysis ca
SET is_current = (ranked.rn = 1)
FROM ranked
WHERE ca.analysis_id = ranked.analysis_id;

-- Step 3: Set superseded_by chain (optional - complex)
-- Or just leave superseded_by NULL for historical data
```

### When to Implement

- **Required for production:** Before compliance/audit requirements kick in
- **Not needed for MVP:** Current test data is acceptable with duplicates
- **Trigger:** When you need to answer "why did this score change?" or "what policy version was used?"

---

## 7. RAG Document Version Tracking

### Problem Statement

When coaching output changes due to updated compliance documents, we need to know:
1. Which documents were used for each analysis?
2. What version of each document?
3. When was the document retrieved?

### How Vertex AI Search Handles Metadata

**On Ingestion:** You can store custom metadata with each document:

```python
from google.cloud import discoveryengine

# When ingesting a document to Vertex AI Search
document = discoveryengine.Document(
    id="POL-002",  # Stable document ID
    content=discoveryengine.Document.Content(
        mime_type="text/html",
        raw_bytes=content_bytes,
    ),
    struct_data={
        "doc_version": "v1.2",
        "version_uuid": "a1b2c3d4-5678-...",
        "title": "Prohibited Language Policy",
        "effective_date": "2026-01-01",
        "category": "compliance",
        "last_updated": "2026-01-05T10:30:00Z"
    }
)

# Ingest to datastore
client.create_document(parent=datastore_path, document=document)
```

**On Retrieval:** The metadata comes back with search results:

```python
# When querying Vertex AI Search
response = client.search(request)

for result in response.results:
    doc_id = result.document.id              # "POL-002"
    doc_data = result.document.struct_data   # Your custom metadata!

    # Access metadata
    version = doc_data.get("doc_version")      # "v1.2"
    uuid = doc_data.get("version_uuid")        # "a1b2c3d4-5678-..."
    title = doc_data.get("title")              # "Prohibited Language Policy"

    # Build citation record
    citation = {
        "doc_id": doc_id,
        "doc_version": version,
        "version_uuid": uuid,
        "doc_title": title,
        "chunk_content": result.chunk.content[:200],  # First 200 chars
        "relevance_score": result.relevance_score,
        "retrieved_at": datetime.utcnow().isoformat()
    }
```

### Recommended `rag_docs_retrieved` Schema

```json
// Stored in coach_analysis.rag_docs_retrieved (JSON column)
[
  {
    "doc_id": "POL-002",
    "doc_version": "v1.2",
    "version_uuid": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
    "doc_title": "Prohibited Language Policy",
    "chunk_id": "section-3-paragraph-2",
    "chunk_preview": "Agents must never use threatening language including...",
    "relevance_score": 0.92,
    "retrieved_at": "2026-01-07T03:21:00Z"
  },
  {
    "doc_id": "GUIDE-001",
    "doc_version": "v1.5",
    "version_uuid": "b2c3d4e5-6789-01bc-defg-2345678901bc",
    "doc_title": "Hardship Handling Guidelines",
    "chunk_id": "section-5-list-1",
    "chunk_preview": "When customer discloses hardship, agent must offer...",
    "relevance_score": 0.87,
    "retrieved_at": "2026-01-07T03:21:00Z"
  }
]
```

### Implementation: RAG Service Update

```python
# cc_coach/services/rag.py (pseudocode)

def retrieve_context(self, query: str, conversation: dict) -> RagResult:
    """Retrieve relevant documents with version tracking."""

    # Call Vertex AI Search
    response = self.search_client.search(
        serving_config=self.serving_config,
        query=query,
        page_size=5,
    )

    # Build citations with version info
    docs_retrieved = []
    context_chunks = []

    for result in response.results:
        # Extract metadata (stored during ingestion)
        struct_data = result.document.struct_data or {}

        citation = {
            "doc_id": result.document.id,
            "doc_version": struct_data.get("doc_version", "unknown"),
            "version_uuid": struct_data.get("version_uuid"),
            "doc_title": struct_data.get("title", result.document.id),
            "chunk_id": getattr(result.chunk, 'id', None),
            "chunk_preview": result.chunk.content[:200] if result.chunk else None,
            "relevance_score": result.relevance_score,
            "retrieved_at": datetime.utcnow().isoformat(),
        }
        docs_retrieved.append(citation)
        context_chunks.append(result.chunk.content)

    return RagResult(
        context_text="\n\n".join(context_chunks),
        docs_retrieved=docs_retrieved,  # Store this in coach_analysis
        doc_count=len(docs_retrieved),
    )
```

### Document Ingestion Pipeline Update

```python
# cc_coach/services/kb_ingestion.py (pseudocode)

def ingest_document(self, doc_path: str, metadata: dict):
    """Ingest document to Vertex AI Search with version metadata."""

    # Generate or retrieve version info
    version_uuid = str(uuid.uuid4())
    doc_version = metadata.get("version", "v1.0")

    # Read content
    with open(doc_path, 'rb') as f:
        content = f.read()

    # Build document with metadata
    document = discoveryengine.Document(
        id=metadata["doc_id"],  # Stable ID (e.g., "POL-002")
        content=discoveryengine.Document.Content(
            mime_type=metadata.get("mime_type", "text/html"),
            raw_bytes=content,
        ),
        struct_data={
            "doc_version": doc_version,
            "version_uuid": version_uuid,
            "title": metadata["title"],
            "category": metadata.get("category"),
            "effective_date": metadata.get("effective_date"),
            "last_updated": datetime.utcnow().isoformat(),
            "author": metadata.get("author"),
        }
    )

    # Ingest to datastore
    self.client.create_document(
        parent=self.datastore_path,
        document=document,
        document_id=metadata["doc_id"],
    )

    # Also record in metadata_management table
    self._record_version(
        doc_id=metadata["doc_id"],
        version=doc_version,
        version_uuid=version_uuid,
        ...
    )
```

### Query Examples

```sql
-- Find all analyses that used a specific document
SELECT
    conversation_id,
    analyzed_at,
    overall_score,
    JSON_QUERY(rag_docs_retrieved, '$[*].doc_id') as docs_used
FROM coach_analysis
WHERE EXISTS (
    SELECT 1 FROM UNNEST(JSON_QUERY_ARRAY(rag_docs_retrieved, '$')) as doc
    WHERE JSON_VALUE(doc, '$.doc_id') = 'POL-002'
);

-- Find analyses using outdated document version
SELECT
    conversation_id,
    analyzed_at,
    JSON_VALUE(doc, '$.doc_id') as doc_id,
    JSON_VALUE(doc, '$.doc_version') as version_used
FROM coach_analysis,
UNNEST(JSON_QUERY_ARRAY(rag_docs_retrieved, '$')) as doc
WHERE JSON_VALUE(doc, '$.doc_id') = 'POL-002'
  AND JSON_VALUE(doc, '$.doc_version') != 'v1.3';  -- Current version is v1.3

-- Audit: What documents influenced this coaching decision?
SELECT
    analysis_id,
    model_version,
    prompt_version,
    rag_docs_retrieved
FROM coach_analysis
WHERE conversation_id = 'xxx' AND is_current = TRUE;
```

### When to Implement

**Phase 1 (MVP - skip):**
- Current RAG retrieval doesn't track document versions
- Acceptable for testing

**Phase 2 (Pre-production):**
- Add `rag_docs_retrieved` column to coach_analysis
- Update RAG service to capture document metadata
- Update ingestion pipeline to store version in struct_data

**Phase 3 (Production):**
- Add document version tracking to KB management UI
- Build audit reports for compliance
- Support "re-analyze with current KB" functionality

---

## 8. When to Re-Analyze Conversations

### Decision Matrix

| Trigger | Re-analyze? | Scope | Reason |
|---------|-------------|-------|--------|
| Model upgrade (gemini-2.5-flash → pro) | Optional | Sample | May improve accuracy |
| Prompt refinement (add hardship rules) | Optional | Sample | May catch new patterns |
| KB doc update (minor typo fix) | No | - | Original was correct at time |
| KB doc update (new compliance rule) | Selective | Compliance breaches | May find new violations |
| Bug fix in scoring logic | Selective | Affected subset | Fix incorrect scores |
| Manual supervisor request | Yes | Single conversation | Re-evaluation requested |

### Selective Re-Analysis Query

```sql
-- Find conversations to re-analyze after KB update
SELECT conversation_id
FROM coach_analysis_latest
WHERE
    -- Has compliance issues
    compliance_score < 5
    -- And used the old document version
    AND EXISTS (
        SELECT 1 FROM UNNEST(JSON_QUERY_ARRAY(rag_docs_retrieved, '$')) as doc
        WHERE JSON_VALUE(doc, '$.doc_id') = 'POL-002'
          AND JSON_VALUE(doc, '$.doc_version') = 'v1.1'  -- Old version
    )
    -- And was analyzed before the update
    AND analyzed_at < '2026-01-07';
```

### Batch Re-Analysis Script (Future)

```python
# cc_coach/scripts/reanalyze_batch.py (future)

def reanalyze_batch(
    reason: str,
    filter_query: str,
    dry_run: bool = True
):
    """Re-analyze a batch of conversations."""

    # Find conversations to re-analyze
    conversations = bq.query(filter_query)

    print(f"Found {len(conversations)} conversations to re-analyze")
    print(f"Reason: {reason}")

    if dry_run:
        print("DRY RUN - no changes made")
        return

    for conv in conversations:
        reanalyze_conversation(
            conversation_id=conv.conversation_id,
            reason=reason
        )

    print(f"Re-analyzed {len(conversations)} conversations")
```

---

## 9. Summary: Deferred Production Features

| Feature | Status | Trigger to Implement |
|---------|--------|---------------------|
| CI QA Scorecard | Deferred | 2,000+ labeled conversations |
| CI Topic Model | Deferred | 1,000+ conversations |
| Analysis versioning (analysis_id, superseded_by) | Deferred | Pre-production audit requirements |
| RAG document tracking (rag_docs_retrieved) | Deferred | Pre-production, KB versioning needed |
| Re-analysis workflow | Deferred | When prompt/model/KB updates are frequent |
| coach_analysis_latest view | Deferred | When implementing analysis versioning |
| conversation_registry.latest_analysis_id | Deferred | When implementing analysis versioning |
