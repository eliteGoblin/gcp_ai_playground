# Metadata Management Design

## Overview

This document describes the production-ready approach for managing document metadata during RAG ingestion. The design ensures:
- Consistent metadata extraction from YAML frontmatter
- Change detection via checksums
- Full audit trail in BigQuery
- Reliable ingestion pipeline

---

## 1. Document Metadata Schema

### 1.1 YAML Frontmatter Structure

All documents use YAML frontmatter for metadata:

```yaml
---
# Identity (Required)
doc_id: POL-002                    # Unique identifier
doc_type: policy                   # policy | coaching | example | external_ref
title: Prohibited Language         # Human-readable title
version: "1.0.0"                   # Semantic version
status: active                     # draft | active | superseded | deprecated

# Scope (Required for filtering)
business_lines: [COLLECTIONS]      # Which business lines this applies to
queues: [ALL]                      # Which queues (ALL = universal)
regions: [AU]                      # Geographic regions

# Optional Scope
call_directions: [INBOUND, OUTBOUND]  # Call direction applicability

# Audit (Required)
author: compliance-team            # Who created/owns this
last_reviewed: "2025-01-03"        # Last review date

# Optional Audit
approved_by: legal-team            # Approval authority
priority: high                     # high | medium | low (RAG ranking hint)
keywords: [threats, prohibited]    # Search keywords

# Versioning
changelog:
  - version: "1.0.0"
    date: "2025-01-03"
    changes: Initial version

# Example-specific (for doc_type: example)
example_type: GOOD_EXAMPLE         # GOOD_EXAMPLE | NEEDS_WORK
overall_score: 9.5                 # Numeric score
source_conversation_id: conv_003   # Reference to source conversation
key_dimensions:                    # Scores by dimension
  empathy: 10
  compliance: 10
  resolution: 9
---
```

### 1.2 Required vs Optional Fields

| Field | Required | Default | Notes |
|-------|----------|---------|-------|
| doc_id | Yes | - | Must be unique |
| doc_type | Yes | - | Determines processing |
| title | Yes | - | - |
| version | Yes | - | Semantic versioning |
| status | Yes | active | - |
| business_lines | Yes | - | Array, at least one |
| queues | Yes | [ALL] | - |
| regions | Yes | - | - |
| author | Yes | - | - |
| last_reviewed | Yes | - | ISO date |
| call_directions | No | [ALL] | - |
| approved_by | No | null | - |
| priority | No | medium | - |
| keywords | No | [] | - |
| changelog | No | [] | - |

---

## 2. Ingestion Pipeline Architecture

### 2.1 Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INGESTION PIPELINE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌────────┐│
│  │   GCS    │───►│  Parse   │───►│ Validate │───►│  Chunk   │───►│  Embed ││
│  │  Bucket  │    │  YAML    │    │ Metadata │    │ Content  │    │  Text  ││
│  └──────────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘    └───┬────┘│
│                       │               │               │              │      │
│                       ▼               ▼               ▼              ▼      │
│                  ┌─────────────────────────────────────────────────────┐    │
│                  │                    BigQuery                         │    │
│                  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │    │
│                  │  │ kb_documents│  │  kb_chunks  │  │ kb_ingest   │ │    │
│                  │  │ (registry)  │  │ (content)   │  │ (log)       │ │    │
│                  │  └─────────────┘  └─────────────┘  └─────────────┘ │    │
│                  └─────────────────────────────────────────────────────┘    │
│                                                      │                      │
│                                                      ▼                      │
│                                            ┌──────────────────┐             │
│                                            │   Vector Store   │             │
│                                            │   (Vertex AI)    │             │
│                                            └──────────────────┘             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Processing Steps

1. **Scan**: List all files in GCS bucket
2. **Parse**: Extract YAML frontmatter and markdown content
3. **Validate**: Check required fields, validate types
4. **Checksum**: Compute SHA-256 of content + metadata
5. **Compare**: Check if checksum differs from stored version
6. **Chunk**: Split content by sections (## headers)
7. **Embed**: Generate embeddings for each chunk
8. **Store**: Upsert to Vector Store and BQ

---

## 3. Metadata Parsing Implementation

### 3.1 Parser Code Structure

```python
# kb_ingestion/parser.py

import yaml
import hashlib
import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import date


@dataclass
class DocumentMetadata:
    """Parsed document metadata from YAML frontmatter."""

    # Identity
    doc_id: str
    doc_type: str  # policy, coaching, example, external_ref
    title: str
    version: str
    status: str  # draft, active, superseded, deprecated

    # Scope
    business_lines: List[str]
    queues: List[str]
    regions: List[str]
    call_directions: List[str]

    # Audit
    author: str
    last_reviewed: str
    approved_by: Optional[str]
    priority: str
    keywords: List[str]

    # Versioning
    changelog: List[Dict[str, Any]]

    # Example-specific
    example_type: Optional[str]
    overall_score: Optional[float]
    source_conversation_id: Optional[str]
    key_dimensions: Optional[Dict[str, int]]


@dataclass
class ParsedDocument:
    """Complete parsed document with metadata and content."""

    metadata: DocumentMetadata
    content: str  # Markdown content without frontmatter
    raw_content: str  # Original file content
    checksum: str  # SHA-256 of raw_content
    source_path: str  # GCS path


def parse_frontmatter(file_content: str) -> tuple[dict, str]:
    """
    Extract YAML frontmatter from markdown file.

    Returns:
        Tuple of (metadata_dict, content_without_frontmatter)
    """
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, file_content, re.DOTALL)

    if not match:
        raise ValueError("No valid YAML frontmatter found")

    yaml_content = match.group(1)
    markdown_content = match.group(2).strip()

    metadata = yaml.safe_load(yaml_content)
    return metadata, markdown_content


def compute_checksum(content: str) -> str:
    """Compute SHA-256 checksum of content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def validate_metadata(metadata: dict) -> List[str]:
    """
    Validate metadata against schema.

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Required fields
    required = ['doc_id', 'doc_type', 'title', 'version', 'status',
                'business_lines', 'queues', 'regions', 'author', 'last_reviewed']

    for field in required:
        if field not in metadata:
            errors.append(f"Missing required field: {field}")

    # Type validation
    if 'doc_type' in metadata:
        valid_types = ['policy', 'coaching', 'example', 'external_ref']
        if metadata['doc_type'] not in valid_types:
            errors.append(f"Invalid doc_type: {metadata['doc_type']}")

    if 'status' in metadata:
        valid_statuses = ['draft', 'active', 'superseded', 'deprecated']
        if metadata['status'] not in valid_statuses:
            errors.append(f"Invalid status: {metadata['status']}")

    if 'priority' in metadata:
        valid_priorities = ['high', 'medium', 'low']
        if metadata['priority'] not in valid_priorities:
            errors.append(f"Invalid priority: {metadata['priority']}")

    # Array field validation
    array_fields = ['business_lines', 'queues', 'regions']
    for field in array_fields:
        if field in metadata and not isinstance(metadata[field], list):
            errors.append(f"{field} must be an array")

    return errors


def parse_document(file_content: str, source_path: str) -> ParsedDocument:
    """
    Parse a complete document from file content.

    Args:
        file_content: Raw file content
        source_path: GCS path to the file

    Returns:
        ParsedDocument with metadata and content

    Raises:
        ValueError: If parsing or validation fails
    """
    # Parse frontmatter
    metadata_dict, content = parse_frontmatter(file_content)

    # Validate
    errors = validate_metadata(metadata_dict)
    if errors:
        raise ValueError(f"Validation errors: {errors}")

    # Build metadata object with defaults
    metadata = DocumentMetadata(
        doc_id=metadata_dict['doc_id'],
        doc_type=metadata_dict['doc_type'],
        title=metadata_dict['title'],
        version=metadata_dict['version'],
        status=metadata_dict.get('status', 'active'),
        business_lines=metadata_dict['business_lines'],
        queues=metadata_dict['queues'],
        regions=metadata_dict['regions'],
        call_directions=metadata_dict.get('call_directions', ['ALL']),
        author=metadata_dict['author'],
        last_reviewed=metadata_dict['last_reviewed'],
        approved_by=metadata_dict.get('approved_by'),
        priority=metadata_dict.get('priority', 'medium'),
        keywords=metadata_dict.get('keywords', []),
        changelog=metadata_dict.get('changelog', []),
        example_type=metadata_dict.get('example_type'),
        overall_score=metadata_dict.get('overall_score'),
        source_conversation_id=metadata_dict.get('source_conversation_id'),
        key_dimensions=metadata_dict.get('key_dimensions'),
    )

    return ParsedDocument(
        metadata=metadata,
        content=content,
        raw_content=file_content,
        checksum=compute_checksum(file_content),
        source_path=source_path,
    )
```

### 3.2 Chunking Implementation

```python
# kb_ingestion/chunker.py

import re
from dataclasses import dataclass
from typing import List
import tiktoken


@dataclass
class Chunk:
    """A chunk of document content for embedding."""

    chunk_id: str
    doc_id: str
    doc_version: str
    section_path: str  # e.g., "Prohibited Language > Threats > Legal Action"
    content: str
    token_count: int
    chunk_index: int  # Order within document


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Count tokens using tiktoken."""
    encoding = tiktoken.get_encoding(model)
    return len(encoding.encode(text))


def split_by_headers(content: str) -> List[tuple[str, str]]:
    """
    Split markdown content by headers.

    Returns:
        List of (header_path, content) tuples
    """
    # Pattern for markdown headers
    pattern = r'^(#{1,4})\s+(.+)$'

    sections = []
    current_path = []
    current_content = []
    current_level = 0

    for line in content.split('\n'):
        match = re.match(pattern, line)
        if match:
            # Save previous section if exists
            if current_content:
                path = ' > '.join(current_path) if current_path else 'Introduction'
                sections.append((path, '\n'.join(current_content).strip()))
                current_content = []

            # Update path based on header level
            level = len(match.group(1))
            header = match.group(2)

            if level <= current_level:
                # Pop back to appropriate level
                current_path = current_path[:level-1]

            current_path.append(header)
            current_level = level
        else:
            current_content.append(line)

    # Don't forget last section
    if current_content:
        path = ' > '.join(current_path) if current_path else 'Introduction'
        sections.append((path, '\n'.join(current_content).strip()))

    return sections


def chunk_document(
    doc_id: str,
    doc_version: str,
    content: str,
    max_tokens: int = 500,
    min_tokens: int = 100,
) -> List[Chunk]:
    """
    Chunk document content by sections.

    Args:
        doc_id: Document ID
        doc_version: Document version
        content: Markdown content
        max_tokens: Maximum tokens per chunk
        min_tokens: Minimum tokens (combine small sections)

    Returns:
        List of Chunk objects
    """
    sections = split_by_headers(content)
    chunks = []
    chunk_index = 0

    pending_content = ""
    pending_path = ""

    for section_path, section_content in sections:
        if not section_content.strip():
            continue

        token_count = count_tokens(section_content)

        if token_count > max_tokens:
            # Large section: split by paragraphs
            paragraphs = section_content.split('\n\n')
            para_buffer = ""

            for para in paragraphs:
                if count_tokens(para_buffer + para) > max_tokens and para_buffer:
                    chunks.append(Chunk(
                        chunk_id=f"{doc_id}-v{doc_version}-{chunk_index:03d}",
                        doc_id=doc_id,
                        doc_version=doc_version,
                        section_path=section_path,
                        content=para_buffer.strip(),
                        token_count=count_tokens(para_buffer),
                        chunk_index=chunk_index,
                    ))
                    chunk_index += 1
                    para_buffer = para
                else:
                    para_buffer += "\n\n" + para if para_buffer else para

            if para_buffer:
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}-v{doc_version}-{chunk_index:03d}",
                    doc_id=doc_id,
                    doc_version=doc_version,
                    section_path=section_path,
                    content=para_buffer.strip(),
                    token_count=count_tokens(para_buffer),
                    chunk_index=chunk_index,
                ))
                chunk_index += 1

        elif token_count < min_tokens and pending_content:
            # Small section: combine with pending
            pending_content += f"\n\n## {section_path}\n{section_content}"

            if count_tokens(pending_content) >= min_tokens:
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}-v{doc_version}-{chunk_index:03d}",
                    doc_id=doc_id,
                    doc_version=doc_version,
                    section_path=pending_path,
                    content=pending_content.strip(),
                    token_count=count_tokens(pending_content),
                    chunk_index=chunk_index,
                ))
                chunk_index += 1
                pending_content = ""
                pending_path = ""

        else:
            # Normal section: create chunk
            if pending_content:
                # Flush pending first
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}-v{doc_version}-{chunk_index:03d}",
                    doc_id=doc_id,
                    doc_version=doc_version,
                    section_path=pending_path,
                    content=pending_content.strip(),
                    token_count=count_tokens(pending_content),
                    chunk_index=chunk_index,
                ))
                chunk_index += 1
                pending_content = ""
                pending_path = ""

            if token_count < min_tokens:
                pending_content = section_content
                pending_path = section_path
            else:
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}-v{doc_version}-{chunk_index:03d}",
                    doc_id=doc_id,
                    doc_version=doc_version,
                    section_path=section_path,
                    content=section_content.strip(),
                    token_count=token_count,
                    chunk_index=chunk_index,
                ))
                chunk_index += 1

    # Flush any remaining pending content
    if pending_content:
        chunks.append(Chunk(
            chunk_id=f"{doc_id}-v{doc_version}-{chunk_index:03d}",
            doc_id=doc_id,
            doc_version=doc_version,
            section_path=pending_path,
            content=pending_content.strip(),
            token_count=count_tokens(pending_content),
            chunk_index=chunk_index,
        ))

    return chunks
```

---

## 4. Change Detection

### 4.1 Checksum-Based Detection

```python
# kb_ingestion/change_detector.py

from google.cloud import bigquery
from typing import Dict, Set


def get_stored_checksums(client: bigquery.Client, dataset: str) -> Dict[str, str]:
    """
    Get checksums of all active documents from BQ.

    Returns:
        Dict mapping doc_id to checksum
    """
    query = f"""
        SELECT doc_id, checksum
        FROM `{dataset}.kb_documents`
        WHERE status = 'active'
    """

    results = client.query(query).result()
    return {row.doc_id: row.checksum for row in results}


def detect_changes(
    stored_checksums: Dict[str, str],
    current_documents: Dict[str, str],  # doc_id -> checksum
) -> tuple[Set[str], Set[str], Set[str]]:
    """
    Detect document changes.

    Returns:
        Tuple of (new_docs, updated_docs, deleted_docs)
    """
    stored_ids = set(stored_checksums.keys())
    current_ids = set(current_documents.keys())

    new_docs = current_ids - stored_ids
    deleted_docs = stored_ids - current_ids

    # Check for updates (same ID, different checksum)
    common_ids = stored_ids & current_ids
    updated_docs = {
        doc_id for doc_id in common_ids
        if stored_checksums[doc_id] != current_documents[doc_id]
    }

    return new_docs, updated_docs, deleted_docs
```

### 4.2 Incremental vs Full Refresh

| Mode | When to Use | What Happens |
|------|-------------|--------------|
| **Full Refresh** | Initial load, weekly maintenance | Delete all, re-ingest all |
| **Incremental** | On file change (Eventarc trigger) | Only process changed files |

```python
# kb_ingestion/sync.py

def full_refresh(bucket_name: str, dataset: str):
    """
    Full refresh: clear and re-ingest everything.

    Use for:
    - Initial ingestion
    - Weekly maintenance
    - After major structural changes
    """
    # 1. Mark all existing as superseded
    mark_all_superseded(dataset)

    # 2. Delete all from vector store
    clear_vector_store()

    # 3. List all documents in GCS
    documents = list_gcs_documents(bucket_name)

    # 4. Process each document
    for doc_path in documents:
        ingest_document(doc_path, dataset)

    # 5. Log completion
    log_sync_event("full_refresh", len(documents))


def incremental_sync(changed_files: List[str], dataset: str):
    """
    Incremental sync: only process changed files.

    Triggered by Eventarc on GCS object changes.
    """
    for file_path in changed_files:
        if file_path.endswith('.md'):
            # Parse and check if exists
            doc = parse_document_from_gcs(file_path)
            existing = get_document_by_id(dataset, doc.metadata.doc_id)

            if existing:
                if existing.checksum != doc.checksum:
                    update_document(doc, dataset)
            else:
                ingest_document(doc, dataset)
```

---

## 5. BigQuery Tables

### 5.1 kb_documents (Document Registry)

```sql
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.kb_documents` (
  -- Identity
  doc_id STRING NOT NULL,
  doc_type STRING NOT NULL,
  title STRING NOT NULL,
  version STRING NOT NULL,
  status STRING NOT NULL,

  -- Scope
  business_lines ARRAY<STRING>,
  queues ARRAY<STRING>,
  regions ARRAY<STRING>,
  call_directions ARRAY<STRING>,

  -- Audit
  author STRING,
  approved_by STRING,
  last_reviewed DATE,
  priority STRING,
  keywords ARRAY<STRING>,

  -- Content
  raw_content STRING,  -- Full markdown including frontmatter
  checksum STRING,     -- SHA-256 for change detection
  source_path STRING,  -- GCS path

  -- Processing
  chunk_count INT64,
  indexed_at TIMESTAMP,

  -- Example-specific (nullable)
  example_type STRING,
  overall_score FLOAT64,
  source_conversation_id STRING,
  key_dimensions JSON,

  -- Versioning
  changelog JSON,
  superseded_by STRING,
  superseded_at TIMESTAMP,

  -- Partitioning/Clustering
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(created_at)
CLUSTER BY doc_type, status;
```

### 5.2 kb_chunks (Chunk Registry)

```sql
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.kb_chunks` (
  chunk_id STRING NOT NULL,
  doc_id STRING NOT NULL,
  doc_version STRING NOT NULL,

  -- Content
  section_path STRING,
  content STRING,
  token_count INT64,
  chunk_index INT64,

  -- Inherited metadata (denormalized for query performance)
  doc_type STRING,
  business_lines ARRAY<STRING>,
  priority STRING,

  -- Vector reference
  embedding_id STRING,  -- ID in vector store

  -- Processing
  indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY doc_id, doc_type;
```

### 5.3 kb_ingest_log (Audit Trail)

```sql
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.kb_ingest_log` (
  ingest_id STRING NOT NULL,

  -- Operation
  operation STRING,  -- full_refresh, incremental, single

  -- Stats
  docs_processed INT64,
  docs_added INT64,
  docs_updated INT64,
  docs_superseded INT64,
  chunks_created INT64,

  -- Timing
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  duration_seconds FLOAT64,

  -- Status
  status STRING,  -- success, partial_failure, failed
  error_message STRING,

  -- Details
  processed_docs JSON  -- Array of {doc_id, status, error}
);
```

---

## 6. Vector Store Integration

### 6.1 Vertex AI Vector Search

```python
# kb_ingestion/vector_store.py

from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel


class VectorStoreManager:
    """Manage Vector Search index for KB chunks."""

    def __init__(self, project: str, location: str, index_name: str):
        self.project = project
        self.location = location
        self.index_name = index_name
        self.embedding_model = TextEmbeddingModel.from_pretrained(
            "text-embedding-005"
        )

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        embeddings = self.embedding_model.get_embeddings([text])
        return embeddings[0].values

    def upsert_chunks(self, chunks: List[Chunk], metadata: DocumentMetadata):
        """
        Upsert chunks to vector store.

        Each chunk includes:
        - ID: chunk_id
        - Vector: embedding
        - Restricts (filters): doc_type, business_lines, priority
        """
        datapoints = []

        for chunk in chunks:
            embedding = self.generate_embedding(chunk.content)

            datapoints.append({
                "datapoint_id": chunk.chunk_id,
                "feature_vector": embedding,
                "restricts": [
                    {"namespace": "doc_type", "allow_list": [metadata.doc_type]},
                    {"namespace": "business_line", "allow_list": metadata.business_lines},
                    {"namespace": "priority", "allow_list": [metadata.priority]},
                    {"namespace": "status", "allow_list": ["active"]},
                ],
            })

        # Upsert to index
        self._upsert_to_index(datapoints)

    def delete_by_doc_id(self, doc_id: str, version: str):
        """Delete all chunks for a specific document version."""
        # Use pattern matching on chunk_id prefix
        prefix = f"{doc_id}-v{version}"
        self._delete_by_prefix(prefix)
```

### 6.2 Retrieval with Filters

```python
def retrieve_chunks(
    query: str,
    business_line: str,
    doc_types: List[str] = None,
    top_k: int = 10,
) -> List[dict]:
    """
    Retrieve relevant chunks with filtering.

    Always filters to status=active (current versions only).
    """
    query_embedding = generate_embedding(query)

    restricts = [
        {"namespace": "status", "allow_list": ["active"]},
        {"namespace": "business_line", "allow_list": [business_line]},
    ]

    if doc_types:
        restricts.append({
            "namespace": "doc_type",
            "allow_list": doc_types
        })

    results = vector_index.match(
        deployed_index_id=DEPLOYED_INDEX_ID,
        queries=[query_embedding],
        num_neighbors=top_k,
        restricts=restricts,
    )

    return results
```

---

## 7. File Organization in GCS

### 7.1 Bucket Structure

```
gs://conversation-coach-kb/
├── documents/
│   ├── policy/
│   │   ├── POL-001_compliance_overview.md
│   │   ├── POL-002_prohibited_language.md
│   │   └── ...
│   ├── coaching/
│   │   ├── COACH-001_agent_playbook.md
│   │   └── ...
│   ├── examples/
│   │   ├── EX-001_good_hardship_handling.md
│   │   └── ...
│   └── external/
│       ├── EXT-001_asic_rg96_reference.md
│       └── ASIC_RG96_debt_collection_guideline.pdf
├── archive/
│   └── 2025-01-01/
│       └── POL-002_prohibited_language.md.bak
└── _metadata/
    └── last_sync.json
```

### 7.2 Naming Conventions

| Pattern | Example | Description |
|---------|---------|-------------|
| `{TYPE}-{NUM}_{slug}.md` | `POL-001_compliance_overview.md` | Main documents |
| `{TYPE}-{NUM}.{NUM}_{slug}.md` | `POL-001.1_amendment.md` | Sub-documents |
| `{doc_id}.md.bak` | `POL-002.md.bak` | Archived versions |

---

## 8. CI/CD Integration

### 8.1 GitHub Actions Workflow

```yaml
# .github/workflows/kb-sync.yml
name: KB Document Sync

on:
  push:
    branches: [main]
    paths:
      - 'documents/**/*.md'
  workflow_dispatch:
    inputs:
      full_refresh:
        description: 'Run full refresh'
        required: false
        default: 'false'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Validate Documents
        run: |
          pip install pyyaml
          python scripts/validate_documents.py documents/

  sync:
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Authenticate to GCP
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - name: Sync to GCS
        run: |
          gcloud storage rsync documents/ gs://${{ vars.KB_BUCKET }}/documents/ \
            --recursive \
            --delete-unmatched-destination-objects

      - name: Trigger Ingestion
        run: |
          if [ "${{ inputs.full_refresh }}" == "true" ]; then
            MODE="full_refresh"
          else
            MODE="incremental"
          fi

          gcloud run jobs execute kb-ingestion \
            --region=australia-southeast1 \
            --update-env-vars MODE=$MODE
```

### 8.2 Validation Script

```python
# scripts/validate_documents.py

import sys
import os
from pathlib import Path
import yaml


def validate_document(file_path: Path) -> list[str]:
    """Validate a single document."""
    errors = []

    content = file_path.read_text()

    # Check frontmatter exists
    if not content.startswith('---'):
        errors.append(f"{file_path}: Missing YAML frontmatter")
        return errors

    # Parse frontmatter
    try:
        parts = content.split('---', 2)
        if len(parts) < 3:
            errors.append(f"{file_path}: Invalid frontmatter format")
            return errors

        metadata = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        errors.append(f"{file_path}: YAML parse error: {e}")
        return errors

    # Check required fields
    required = ['doc_id', 'doc_type', 'title', 'version', 'status']
    for field in required:
        if field not in metadata:
            errors.append(f"{file_path}: Missing required field: {field}")

    # Check doc_id matches filename
    expected_prefix = metadata.get('doc_id', '')
    if not file_path.stem.startswith(expected_prefix):
        errors.append(
            f"{file_path}: doc_id '{expected_prefix}' doesn't match filename"
        )

    return errors


def main():
    docs_dir = Path(sys.argv[1])
    all_errors = []

    for md_file in docs_dir.rglob('*.md'):
        errors = validate_document(md_file)
        all_errors.extend(errors)

    if all_errors:
        print("Validation errors:")
        for error in all_errors:
            print(f"  - {error}")
        sys.exit(1)

    print(f"All documents valid ({len(list(docs_dir.rglob('*.md')))} files)")
    sys.exit(0)


if __name__ == '__main__':
    main()
```

---

## 9. Summary

### Key Design Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Metadata Format | YAML frontmatter | Human-readable, git-friendly |
| Change Detection | SHA-256 checksum | Fast, reliable |
| Storage | BQ + Vector Store | Full audit + fast retrieval |
| Sync Mode | Full refresh for POC | Simpler, reliable |
| Chunking | By markdown headers | Semantic boundaries |
| Versioning | Semantic (x.y.z) | Clear intent |

### Files to Implement

1. `kb_ingestion/parser.py` - YAML/markdown parsing
2. `kb_ingestion/chunker.py` - Content chunking
3. `kb_ingestion/change_detector.py` - Checksum comparison
4. `kb_ingestion/vector_store.py` - Vertex AI integration
5. `kb_ingestion/sync.py` - Orchestration
6. `scripts/validate_documents.py` - CI validation
7. `sql/create_kb_tables.sql` - BQ schema

### Next Steps

1. Create GCS bucket for documents
2. Deploy BQ tables
3. Implement ingestion pipeline
4. Set up Eventarc trigger
5. Configure GitHub Actions
