-- RAG Knowledge Base Tables for Conversation Coach
--
-- These tables support the RAG pipeline with:
-- - kb_documents: Document registry with metadata, raw content, and version history
-- - kb_retrieval_log: Audit trail for RAG retrievals
--
-- Usage:
--   bq query --use_legacy_sql=false < create_kb_tables.sql
--
-- Or run each CREATE TABLE separately in BigQuery console.

-- ============================================================================
-- kb_documents: Document Registry
-- ============================================================================
-- Stores all document metadata and raw content. Supports immutable artifact
-- model where documents are never updated, only superseded by new versions.
--
-- Primary Key: uuid (deterministic from file_path + version)
-- GCS Sync: Only documents with status='active' are synced to GCS

CREATE TABLE IF NOT EXISTS conversation_coach.kb_documents (
  -- PRIMARY KEY (deterministic from file_path + version)
  uuid STRING NOT NULL,

  -- IDENTITY (from YAML frontmatter)
  doc_id STRING NOT NULL,           -- Human-readable ID: "POL-002"
  doc_type STRING NOT NULL,         -- "policy", "coaching", "example", "external"
  title STRING NOT NULL,
  version STRING NOT NULL,          -- Semantic version: "1.1.0"

  -- SOURCE (local file info)
  file_path STRING NOT NULL,        -- Relative path: "documents/policy/POL-002.md"

  -- STATUS (controls GCS sync)
  status STRING NOT NULL,           -- "active", "superseded", "retired", "deleted", "draft"
  status_reason STRING,             -- "expired", "replaced_by_v2", "policy_change", etc.
  superseded_by STRING,             -- UUID of replacement doc (if superseded)
  status_changed_at TIMESTAMP,

  -- SCOPE (for filtering during retrieval)
  business_lines ARRAY<STRING>,     -- ["COLLECTIONS", "HARDSHIP"]
  queues ARRAY<STRING>,             -- ["ALL", "INBOUND", "OUTBOUND"]
  regions ARRAY<STRING>,            -- ["AU", "NZ"]

  -- CONTENT
  raw_content STRING NOT NULL,      -- Full markdown including YAML frontmatter
  checksum STRING NOT NULL,         -- SHA-256 for change detection

  -- AUDIT
  author STRING,
  approved_by STRING,
  effective_date DATE,
  expiry_date DATE,
  last_reviewed DATE,

  -- TIMESTAMPS
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
OPTIONS(
  description = "Knowledge base document registry for RAG pipeline"
);

-- ============================================================================
-- kb_retrieval_log: Audit Trail for RAG Retrievals
-- ============================================================================
-- Logs every RAG retrieval for audit purposes. Enables:
-- - Tracing which documents were used for each coaching session
-- - Analytics on document usage patterns
-- - Debugging why specific coaching tips were generated

CREATE TABLE IF NOT EXISTS conversation_coach.kb_retrieval_log (
  -- IDENTITY
  retrieval_id STRING NOT NULL,
  conversation_id STRING NOT NULL,    -- Links to coaching session

  -- QUERY
  query_text STRING,                  -- The query sent to Vertex AI Search

  -- RESULTS (what was retrieved)
  retrieved_docs ARRAY<STRUCT<
    uuid STRING,                      -- Document UUID
    doc_id STRING,                    -- Human-readable ID
    version STRING,
    section STRING,                   -- Extracted from snippet
    snippet STRING,                   -- Text snippet from Vertex AI Search
    relevance_score FLOAT64
  >>,

  -- CONTEXT
  coach_model_version STRING,         -- e.g., "gemini-1.5-flash"
  prompt_version STRING,              -- Version of coaching prompt used
  business_line STRING,               -- Business context for the query

  -- TIMESTAMP
  retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
OPTIONS(
  description = "Audit log for RAG retrievals in coaching pipeline"
);

-- ============================================================================
-- Useful Queries
-- ============================================================================

-- Get all active documents
-- SELECT uuid, doc_id, version, title, doc_type
-- FROM conversation_coach.kb_documents
-- WHERE status = 'active'
-- ORDER BY doc_type, doc_id;

-- Get document history for a specific doc_id
-- SELECT uuid, version, status, status_reason, created_at
-- FROM conversation_coach.kb_documents
-- WHERE doc_id = 'POL-002'
-- ORDER BY created_at DESC;

-- Check which documents were used for a coaching session
-- SELECT retrieved_docs
-- FROM conversation_coach.kb_retrieval_log
-- WHERE conversation_id = 'conv_123';

-- Find most frequently retrieved documents
-- SELECT doc.doc_id, doc.version, COUNT(*) as retrieval_count
-- FROM conversation_coach.kb_retrieval_log, UNNEST(retrieved_docs) AS doc
-- WHERE retrieved_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
-- GROUP BY doc.doc_id, doc.version
-- ORDER BY retrieval_count DESC
-- LIMIT 20;
