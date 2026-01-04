# RAG Local MVP/POC

## Quick Summary: What We're Building

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LOCAL MVP RAG PIPELINE                                    │
│                    ─────────────────────                                     │
│                                                                             │
│   GOAL: Coach agent retrieves relevant policy/coaching docs when analyzing  │
│         a conversation, so feedback is grounded in company guidelines.      │
│                                                                             │
│   INPUT:  Agent-customer conversation transcript                            │
│   OUTPUT: Coaching feedback with citations to policy/coaching docs          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LOCAL MVP ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DOCUMENTS (Local)                                                          │
│  ─────────────────                                                          │
│  documents/                                                                 │
│  ├── policy/        (6 files: POL-001 to POL-006)                          │
│  ├── coaching/      (5 files: COACH-001 to COACH-005)                      │
│  ├── examples/      (4 files: EX-001 to EX-004)                            │
│  └── external/      (1 file: EXT-001 + PDF)                                │
│                                                                             │
│         │                                                                   │
│         │  INGEST (run once, or when docs change)                          │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     INGESTION PIPELINE                               │   │
│  │                                                                      │   │
│  │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │   │
│  │  │  Scan    │──►│  Parse   │──►│  Chunk   │──►│  Embed           │ │   │
│  │  │  .md     │   │  YAML +  │   │  by      │   │  (Vertex AI API) │ │   │
│  │  │  files   │   │  content │   │  section │   │                  │ │   │
│  │  └──────────┘   └──────────┘   └──────────┘   └────────┬─────────┘ │   │
│  │                                                         │          │   │
│  └─────────────────────────────────────────────────────────┼──────────┘   │
│                                                             │              │
│         ┌───────────────────────────────────────────────────┘              │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      LOCAL STORAGE                                   │   │
│  │                                                                      │   │
│  │  ┌──────────────────────┐    ┌──────────────────────────────────┐  │   │
│  │  │  ChromaDB            │    │  SQLite                          │  │   │
│  │  │  (Vector Store)      │    │  (Metadata)                      │  │   │
│  │  │                      │    │                                  │  │   │
│  │  │  • chunk embeddings  │    │  • doc registry                  │  │   │
│  │  │  • similarity search │    │  • chunk content                 │  │   │
│  │  │  • filtering         │    │  • checksums                     │  │   │
│  │  │                      │    │                                  │  │   │
│  │  │  ./data/chroma/      │    │  ./data/kb.db                    │  │   │
│  │  └──────────────────────┘    └──────────────────────────────────┘  │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│         │                                                                   │
│         │  RETRIEVE (every coaching request)                               │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     RETRIEVAL + GENERATION                           │   │
│  │                                                                      │   │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐│   │
│  │  │  Coach CLI   │──►│  RAG         │──►│  Gemini API              ││   │
│  │  │              │   │  Retriever   │   │                          ││   │
│  │  │  cc coach    │   │              │   │  Query + Context         ││   │
│  │  │  <file>      │   │  1. Embed Q  │   │  → Coaching Response     ││   │
│  │  │              │   │  2. Search   │   │  → Citations             ││   │
│  │  │              │   │  3. Rank     │   │                          ││   │
│  │  └──────────────┘   └──────────────┘   └──────────────────────────┘│   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Triggering the Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HOW TO TRIGGER                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. INGEST (one-time or when docs change)                                   │
│  ─────────────────────────────────────────                                  │
│                                                                             │
│     $ cd usecases/conversation-coach/artifacts/cli                          │
│     $ source .venv/bin/activate                                             │
│     $ cc ingest                          # Scan all docs, build index       │
│                                                                             │
│     OR with options:                                                        │
│     $ cc ingest --full-refresh           # Rebuild from scratch             │
│     $ cc ingest --doc-type policy        # Only ingest policy docs          │
│                                                                             │
│  ───────────────────────────────────────────────────────────────────────── │
│                                                                             │
│  2. COACH WITH RAG (every conversation)                                     │
│  ──────────────────────────────────────                                     │
│                                                                             │
│     $ cc coach conversation.json         # Coach with RAG context           │
│                                                                             │
│     Under the hood:                                                         │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │  1. Load conversation                                            │    │
│     │  2. Extract topics: "hardship", "legal threat", "payment plan"  │    │
│     │  3. Query ChromaDB for relevant chunks                           │    │
│     │  4. Build prompt: system + context + conversation                │    │
│     │  5. Call Gemini → get coaching response                          │    │
│     │  6. Return response with citations                               │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ───────────────────────────────────────────────────────────────────────── │
│                                                                             │
│  3. INTERACTIVE MODE (optional)                                             │
│  ──────────────────────────────                                             │
│                                                                             │
│     $ cc chat                            # Interactive Q&A with KB          │
│                                                                             │
│     > What are the rules about threatening customers?                       │
│     [Searches KB, returns answer with citations]                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INGESTION FLOW (cc ingest)                                                 │
│  ══════════════════════════                                                 │
│                                                                             │
│  documents/*.md                                                             │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  For each .md file:                                                  │   │
│  │                                                                      │   │
│  │  POL-002_prohibited_language.md                                     │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Parse YAML frontmatter                                             │   │
│  │  {doc_id: POL-002, doc_type: policy, ...}                          │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Compute checksum (SHA-256)                                         │   │
│  │  "a1b2c3d4..."                                                      │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Changed? ──No──► Skip                                              │   │
│  │       │                                                              │   │
│  │      Yes                                                             │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Chunk by ## sections                                               │   │
│  │  [chunk1, chunk2, chunk3, ...]                                      │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Generate embeddings (Vertex AI API)                                │   │
│  │  [[0.1, 0.2, ...], [0.3, 0.4, ...], ...]                           │   │
│  │       │                                                              │   │
│  │       ├──────────────────────┬──────────────────────┐               │   │
│  │       ▼                      ▼                      ▼               │   │
│  │  ChromaDB              SQLite (docs)         SQLite (chunks)        │   │
│  │  • vectors             • doc_id              • chunk_id             │   │
│  │  • metadata            • checksum            • content              │   │
│  │  • chunk_id            • status              • section_path         │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  RETRIEVAL FLOW (cc coach)                                                  │
│  ═════════════════════════                                                  │
│                                                                             │
│  conversation.json                                                          │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  Extract key topics from conversation                               │   │
│  │  "Customer mentioned hardship, agent threatened legal action"       │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Embed query (Vertex AI API)                                        │   │
│  │  [0.12, -0.45, 0.78, ...]                                          │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Search ChromaDB (top 10, filtered by doc_type)                     │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Results:                                                            │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │ score=0.92  POL-002  "Threats of legal action prohibited..."  │  │   │
│  │  │ score=0.87  POL-004  "Hardship triggers: job loss, medical..."│  │   │
│  │  │ score=0.71  COACH-002 "De-escalation: LEARN framework..."     │  │   │
│  │  │ score=0.65  EX-003   "Poor example: agent threatened..."      │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Fetch full chunk content from SQLite                               │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Build prompt:                                                       │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │ SYSTEM: You are a conversation coach...                        │  │   │
│  │  │                                                                 │  │   │
│  │  │ CONTEXT:                                                        │  │   │
│  │  │ [POL-002] Threats of legal action are prohibited...            │  │   │
│  │  │ [POL-004] When customer mentions hardship...                   │  │   │
│  │  │ [COACH-002] Use LEARN framework...                             │  │   │
│  │  │                                                                 │  │   │
│  │  │ CONVERSATION:                                                   │  │   │
│  │  │ AGENT: If you don't pay, we'll take you to court...            │  │   │
│  │  │ CUSTOMER: I just lost my job...                                │  │   │
│  │  │                                                                 │  │   │
│  │  │ Provide coaching feedback with citations.                       │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Call Gemini API                                                     │   │
│  │       │                                                              │   │
│  │       ▼                                                              │   │
│  │  Coaching Response (with citations)                                  │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Stack (Local MVP)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TECHNOLOGY STACK                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Component          Local MVP                  Production (later)           │
│  ─────────          ─────────                  ──────────────────           │
│                                                                             │
│  Vector Store       ChromaDB (local)           Vertex AI Vector Search     │
│                     ./data/chroma/             (managed endpoint)           │
│                                                                             │
│  Metadata Store     SQLite (local)             BigQuery                     │
│                     ./data/kb.db               (serverless)                 │
│                                                                             │
│  Document Store     Local filesystem           Cloud Storage                │
│                     ./documents/               gs://bucket/documents/       │
│                                                                             │
│  Embeddings         Vertex AI API              Vertex AI API                │
│                     text-embedding-005         (same)                       │
│                                                                             │
│  Generation         Gemini API                 Gemini API                   │
│                     gemini-1.5-flash           (same)                       │
│                                                                             │
│  Orchestration      Python CLI                 Cloud Run Job                │
│                     (cc ingest/coach)          (triggered by scheduler)     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## File Structure (What to Build)

```
usecases/conversation-coach/artifacts/cli/
├── cc_coach/
│   ├── __init__.py
│   ├── cli.py                    # Existing CLI entry point
│   │
│   ├── rag/                      # NEW: RAG module
│   │   ├── __init__.py
│   │   ├── config.py             # RAG configuration
│   │   ├── parser.py             # YAML frontmatter parser
│   │   ├── chunker.py            # Section-based chunking
│   │   ├── embeddings.py         # Vertex AI embedding client
│   │   ├── vector_store.py       # ChromaDB wrapper
│   │   ├── metadata_store.py     # SQLite wrapper
│   │   ├── ingest.py             # Ingestion orchestration
│   │   └── retriever.py          # Retrieval logic
│   │
│   ├── services/
│   │   └── coaching.py           # UPDATE: integrate RAG retriever
│   │
│   └── prompts/
│       └── coach_with_rag.py     # NEW: prompt with context
│
├── data/                         # NEW: Local storage (gitignored)
│   ├── chroma/                   # ChromaDB files
│   └── kb.db                     # SQLite database
│
└── pyproject.toml                # UPDATE: add chromadb, etc.
```

## CLI Commands Summary

```bash
# SETUP (one-time)
cd usecases/conversation-coach/artifacts/cli
source .venv/bin/activate
pip install -e ".[rag]"           # Install with RAG dependencies

# INGEST (when docs change)
cc ingest                          # Incremental: only changed docs
cc ingest --full-refresh           # Full: rebuild everything
cc ingest --dry-run                # Preview what would be ingested

# COACH (with RAG)
cc coach conversation.json         # Coach with RAG context
cc coach conversation.json --no-rag  # Coach without RAG (compare)

# DEBUG / UTILITY
cc rag status                      # Show index stats
cc rag search "hardship rules"     # Test retrieval
cc rag show POL-002                # Show document chunks
```

## Migration Path to Production

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LOCAL → PRODUCTION MIGRATION                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LOCAL MVP                           PRODUCTION                             │
│  ─────────                           ──────────                             │
│                                                                             │
│  ChromaDB (local)         ────►      Vertex AI Vector Search                │
│  • Change vector_store.py            • New VectorStoreClient class          │
│  • Same interface                    • Same interface                       │
│                                                                             │
│  SQLite (local)           ────►      BigQuery                               │
│  • Change metadata_store.py          • New BQMetadataStore class            │
│  • Same interface                    • Same interface                       │
│                                                                             │
│  Local filesystem         ────►      Cloud Storage                          │
│  • Change ingest.py source           • gsutil or storage client             │
│                                                                             │
│  Python CLI               ────►      Cloud Run Job                          │
│  • Same code                         • Containerize                         │
│  • Manual trigger                    • Scheduler trigger                    │
│                                                                             │
│  KEY: Abstract storage behind interfaces, swap implementations              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Dependencies to Add

```toml
# pyproject.toml - add to [project.optional-dependencies]

[project.optional-dependencies]
rag = [
    "chromadb>=0.4.0",           # Local vector store
    "tiktoken>=0.5.0",           # Token counting for chunking
    "pyyaml>=6.0",               # YAML frontmatter parsing
]
```

## Quick Start (After Implementation)

```bash
# 1. Install
cd usecases/conversation-coach/artifacts/cli
pip install -e ".[rag]"

# 2. Set up GCP auth (for embeddings)
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/vertex-ai-demo-key.json

# 3. Ingest documents
cc ingest --full-refresh

# Expected output:
# Scanning documents/...
# Found 16 documents
# Processing POL-001_compliance_overview.md... 5 chunks
# Processing POL-002_prohibited_language.md... 8 chunks
# ...
# Ingestion complete: 16 docs, 87 chunks, 0 errors

# 4. Coach a conversation (with RAG)
cc coach sample_conversation.json

# Expected output:
# Retrieved 8 relevant chunks from knowledge base
#
# COACHING FEEDBACK:
# ...
# [Citations: POL-002, POL-004, COACH-002]
```
