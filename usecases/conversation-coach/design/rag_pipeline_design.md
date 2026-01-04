# RAG Pipeline Design

## Document Information

| Field | Value |
|-------|-------|
| **Version** | 1.0.0 |
| **Status** | Draft |
| **Author** | Platform Team |
| **Created** | 2025-01-03 |
| **Last Updated** | 2025-01-03 |

### Related Documents

| Document | Relationship | Description |
|----------|--------------|-------------|
| [rag_knowledge_base_design.md](./rag_knowledge_base_design.md) | Parent | System architecture, document lifecycle, BQ schemas |
| [metadata_management_design.md](./metadata_management_design.md) | Sibling | YAML parsing, chunking algorithms, change detection |

---

## 1. Executive Summary

This document provides the implementation design for the RAG (Retrieval-Augmented Generation) pipeline using Google Cloud Vertex AI. The pipeline ingests compliance and coaching documents, creates searchable embeddings, and enables the Conversation Coach to retrieve relevant context for agent coaching.

### 1.1 Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector Store | Vertex AI Vector Search | Full control, cost-effective at scale, filtering support |
| Embedding Model | text-embedding-005 | Latest Google model, 768 dimensions, multilingual |
| Orchestration | Cloud Run Jobs | Cost-effective for batch, no idle costs |
| Document Storage | GCS + BigQuery | GCS for source, BQ for metadata/audit |

### 1.2 Architecture Option Analysis

Before implementation, we evaluated two Vertex AI approaches:

#### Option A: Vertex AI Search (Managed RAG)

```
┌─────────────────────────────────────────────────────────────────┐
│  Vertex AI Search (Agent Builder)                               │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Data    │───►│  Auto    │───►│  Managed │───►│  Search  │  │
│  │  Store   │    │  Index   │    │  Serving │    │  API     │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

| Pros | Cons |
|------|------|
| Fully managed | Less control over chunking |
| Built-in grounding | Higher cost at scale |
| Auto-reindexing | Limited filtering options |
| Quick to set up | Black-box ranking |

#### Option B: Vertex AI Vector Search (Self-Managed)

```
┌─────────────────────────────────────────────────────────────────┐
│  Custom Pipeline                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  GCS     │───►│  Custom  │───►│  Vector  │───►│  Custom  │  │
│  │  Bucket  │    │  Chunker │    │  Search  │    │  Retriever│  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

| Pros | Cons |
|------|------|
| Full control | More implementation work |
| Custom chunking | Must manage infrastructure |
| Advanced filtering | Must handle updates |
| Lower cost at scale | More operational overhead |

#### Decision: Option B (Vector Search)

**Rationale:**
1. Need custom chunking by document sections (see metadata_management_design.md)
2. Need filtering by `doc_type`, `business_line`, `priority`
3. Small document corpus (~20 docs initially) = low operational overhead
4. Cost optimization important for POC budget

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RAG PIPELINE ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INGESTION FLOW (Batch)                                                     │
│  ════════════════════════                                                   │
│                                                                             │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   GCS    │    │  Cloud Run   │    │   Vertex AI  │    │   Vertex AI  │  │
│  │  Bucket  │───►│    Job       │───►│  Embeddings  │───►│ Vector Search│  │
│  │documents/│    │ (Ingestion)  │    │    API       │    │   (Index)    │  │
│  └──────────┘    └──────┬───────┘    └──────────────┘    └──────────────┘  │
│                         │                                                   │
│                         ▼                                                   │
│                  ┌──────────────┐                                           │
│                  │   BigQuery   │                                           │
│                  │  (Metadata)  │                                           │
│                  └──────────────┘                                           │
│                                                                             │
│  RETRIEVAL FLOW (Real-time)                                                 │
│  ══════════════════════════                                                 │
│                                                                             │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Coach   │    │   Vertex AI  │    │   Vertex AI  │    │   BigQuery   │  │
│  │  Agent   │───►│  Embeddings  │───►│ Vector Search│───►│  (Content)   │  │
│  │ (Query)  │    │    API       │    │   (Query)    │    │              │  │
│  └────┬─────┘    └──────────────┘    └──────────────┘    └──────┬───────┘  │
│       │                                                          │          │
│       │                    ┌──────────────┐                      │          │
│       └───────────────────►│   Gemini     │◄─────────────────────┘          │
│         Query + Context    │  (Generate)  │  Retrieved Chunks               │
│                            └──────────────┘                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Details

| Component | GCP Service | Purpose | Scaling |
|-----------|-------------|---------|---------|
| Document Storage | Cloud Storage | Source markdown files | N/A |
| Ingestion Job | Cloud Run Jobs | Parse, chunk, embed, index | 0 → 1 (on-demand) |
| Embedding API | Vertex AI text-embedding-005 | Generate 768-dim vectors | Auto-scaled |
| Vector Index | Vertex AI Vector Search | Store and query embeddings | Configurable replicas |
| Metadata Store | BigQuery | Document registry, chunks, audit | Serverless |
| Coach Agent | Cloud Run Service | Query and generate responses | 0 → N |
| Generation | Gemini 1.5 Flash | Generate coaching responses | Auto-scaled |

### 2.3 Data Flow

```
                    INGESTION                              RETRIEVAL
                    ─────────                              ─────────

    ┌─────────────────────────────────┐      ┌─────────────────────────────────┐
    │                                 │      │                                 │
    │  1. Read from GCS               │      │  1. Receive query               │
    │     ↓                           │      │     ↓                           │
    │  2. Parse YAML frontmatter      │      │  2. Generate query embedding    │
    │     (metadata_management)       │      │     ↓                           │
    │     ↓                           │      │  3. Search Vector Index         │
    │  3. Validate metadata           │      │     (with filters)              │
    │     ↓                           │      │     ↓                           │
    │  4. Compute checksum            │      │  4. Get chunk IDs               │
    │     ↓                           │      │     ↓                           │
    │  5. Compare with stored         │      │  5. Fetch content from BQ       │
    │     ↓                           │      │     ↓                           │
    │  6. Chunk by sections           │      │  6. Construct prompt            │
    │     ↓                           │      │     ↓                           │
    │  7. Generate embeddings         │      │  7. Generate with Gemini        │
    │     (batch)                     │      │     ↓                           │
    │     ↓                           │      │  8. Return response             │
    │  8. Upsert to Vector Search     │      │     + citations                 │
    │     ↓                           │      │                                 │
    │  9. Write metadata to BQ        │      └─────────────────────────────────┘
    │     ↓                           │
    │ 10. Log ingestion result        │
    │                                 │
    └─────────────────────────────────┘
```

---

## 3. Vertex AI Vector Search Configuration

### 3.1 Index Configuration

```python
# Index configuration for conversation-coach KB
INDEX_CONFIG = {
    "display_name": "conversation-coach-kb-index",
    "description": "Knowledge base for conversation coaching",

    # Embedding configuration
    "dimensions": 768,  # text-embedding-005 output size
    "approximate_neighbors_count": 10,  # Default k for ANN

    # Algorithm configuration
    "algorithm_config": {
        "tree_ah_config": {
            "leaf_node_embedding_count": 1000,
            "leaf_nodes_to_search_percent": 10,
        }
    },

    # Distance metric
    "distance_measure_type": "DOT_PRODUCT_DISTANCE",

    # Shard configuration (for small corpus)
    "shard_size": "SHARD_SIZE_SMALL",  # < 100K vectors
}
```

### 3.2 Index Endpoint Configuration

```python
ENDPOINT_CONFIG = {
    "display_name": "conversation-coach-kb-endpoint",

    # Deployed index configuration
    "deployed_indexes": [{
        "id": "kb-index-deployed",
        "index": INDEX_RESOURCE_NAME,

        # Machine configuration (cost-optimized for POC)
        "dedicated_resources": {
            "machine_spec": {
                "machine_type": "e2-standard-2",  # Smallest option
            },
            "min_replica_count": 1,
            "max_replica_count": 1,  # No auto-scaling for POC
        },

        # Or use automatic resources (simpler, slightly higher cost)
        # "automatic_resources": {
        #     "min_replica_count": 1,
        #     "max_replica_count": 2,
        # },
    }]
}
```

### 3.3 Filtering (Restricts)

Vector Search supports namespace-based filtering:

```python
# Restrict namespaces defined at index time
RESTRICT_NAMESPACES = [
    "doc_type",       # policy, coaching, example
    "business_line",  # COLLECTIONS, HARDSHIP
    "priority",       # high, medium, low
    "status",         # active (always filter to active)
]

# At query time
def query_with_filters(
    query_embedding: List[float],
    doc_types: List[str] = None,
    business_line: str = "COLLECTIONS",
    top_k: int = 10,
) -> List[MatchResult]:

    restricts = [
        Namespace(name="status", allow_tokens=["active"]),
        Namespace(name="business_line", allow_tokens=[business_line]),
    ]

    if doc_types:
        restricts.append(
            Namespace(name="doc_type", allow_tokens=doc_types)
        )

    return index_endpoint.find_neighbors(
        deployed_index_id="kb-index-deployed",
        queries=[query_embedding],
        num_neighbors=top_k,
        restricts=restricts,
    )
```

---

## 4. Embedding Strategy

### 4.1 Model Selection

| Model | Dimensions | Max Tokens | Cost (per 1K chars) | Notes |
|-------|------------|------------|---------------------|-------|
| text-embedding-005 | 768 | 2,048 | $0.00002 | **Selected** - Latest, best quality |
| text-embedding-004 | 768 | 2,048 | $0.00002 | Previous gen |
| textembedding-gecko@003 | 768 | 3,072 | $0.00002 | Deprecated |

### 4.2 Embedding Generation

```python
from vertexai.language_models import TextEmbeddingModel

class EmbeddingService:
    """Service for generating embeddings."""

    def __init__(self, model_name: str = "text-embedding-005"):
        self.model = TextEmbeddingModel.from_pretrained(model_name)

    def embed_texts(
        self,
        texts: List[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            task_type: RETRIEVAL_DOCUMENT (for indexing) or
                      RETRIEVAL_QUERY (for searching)

        Returns:
            List of embedding vectors
        """
        # Batch for efficiency (max 250 per request)
        batch_size = 250
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            embeddings = self.model.get_embeddings(
                texts=batch,
                task_type=task_type,
            )

            all_embeddings.extend([e.values for e in embeddings])

        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """Generate embedding for a search query."""
        embeddings = self.model.get_embeddings(
            texts=[query],
            task_type="RETRIEVAL_QUERY",
        )
        return embeddings[0].values
```

### 4.3 Task Type Usage

| Scenario | Task Type | When |
|----------|-----------|------|
| Indexing documents | `RETRIEVAL_DOCUMENT` | During ingestion |
| Searching | `RETRIEVAL_QUERY` | During coach query |
| Similarity comparison | `SEMANTIC_SIMILARITY` | If comparing chunks |

---

## 5. Ingestion Pipeline Implementation

### 5.1 Pipeline Code Structure

```
kb_ingestion/
├── __init__.py
├── main.py              # Entry point (Cloud Run Job)
├── config.py            # Configuration management
├── parser.py            # YAML/markdown parsing (from metadata_management_design)
├── chunker.py           # Content chunking (from metadata_management_design)
├── embeddings.py        # Embedding generation
├── vector_store.py      # Vector Search operations
├── bq_client.py         # BigQuery operations
├── sync.py              # Orchestration logic
└── utils/
    ├── checksum.py      # Change detection
    └── logging.py       # Structured logging
```

### 5.2 Main Orchestration

```python
# kb_ingestion/main.py

import os
from google.cloud import storage, bigquery
from .config import Config
from .parser import parse_document
from .chunker import chunk_document
from .embeddings import EmbeddingService
from .vector_store import VectorStoreClient
from .bq_client import BQClient


def run_ingestion(mode: str = "incremental"):
    """
    Main ingestion entry point.

    Args:
        mode: "full_refresh" or "incremental"
    """
    config = Config.from_env()

    # Initialize clients
    gcs = storage.Client()
    bq = BQClient(config.project, config.dataset)
    embeddings = EmbeddingService()
    vector_store = VectorStoreClient(
        config.project,
        config.location,
        config.index_endpoint_id,
        config.deployed_index_id,
    )

    # Get documents from GCS
    bucket = gcs.bucket(config.kb_bucket)
    blobs = list(bucket.list_blobs(prefix="documents/"))

    md_files = [b for b in blobs if b.name.endswith('.md')]

    if mode == "full_refresh":
        # Clear existing data
        vector_store.remove_all_datapoints()
        bq.mark_all_superseded()

    # Get stored checksums for comparison
    stored_checksums = bq.get_document_checksums()

    # Process documents
    stats = {"added": 0, "updated": 0, "unchanged": 0, "errors": 0}

    for blob in md_files:
        try:
            result = process_document(
                blob=blob,
                stored_checksums=stored_checksums,
                embeddings=embeddings,
                vector_store=vector_store,
                bq=bq,
                mode=mode,
            )
            stats[result] += 1

        except Exception as e:
            logging.error(f"Error processing {blob.name}: {e}")
            stats["errors"] += 1

    # Log completion
    bq.log_ingestion(
        mode=mode,
        stats=stats,
    )

    return stats


def process_document(
    blob,
    stored_checksums: dict,
    embeddings: EmbeddingService,
    vector_store: VectorStoreClient,
    bq: BQClient,
    mode: str,
) -> str:
    """Process a single document."""

    # 1. Parse document
    content = blob.download_as_text()
    doc = parse_document(content, blob.name)

    # 2. Check if changed (skip for full_refresh)
    if mode == "incremental":
        stored_checksum = stored_checksums.get(doc.metadata.doc_id)
        if stored_checksum == doc.checksum:
            return "unchanged"

    # 3. Chunk content
    chunks = chunk_document(
        doc_id=doc.metadata.doc_id,
        doc_version=doc.metadata.version,
        content=doc.content,
    )

    # 4. Generate embeddings
    chunk_texts = [c.content for c in chunks]
    chunk_embeddings = embeddings.embed_texts(
        chunk_texts,
        task_type="RETRIEVAL_DOCUMENT",
    )

    # 5. Build datapoints for Vector Search
    datapoints = []
    for chunk, embedding in zip(chunks, chunk_embeddings):
        datapoints.append({
            "datapoint_id": chunk.chunk_id,
            "feature_vector": embedding,
            "restricts": [
                {"namespace": "doc_type", "allow_list": [doc.metadata.doc_type]},
                {"namespace": "business_line", "allow_list": doc.metadata.business_lines},
                {"namespace": "priority", "allow_list": [doc.metadata.priority]},
                {"namespace": "status", "allow_list": ["active"]},
            ],
        })

    # 6. Remove old version from Vector Search (if updating)
    if doc.metadata.doc_id in stored_checksums:
        vector_store.remove_by_prefix(doc.metadata.doc_id)

    # 7. Upsert to Vector Search
    vector_store.upsert_datapoints(datapoints)

    # 8. Write to BigQuery
    bq.upsert_document(doc)
    bq.insert_chunks(chunks, doc.metadata)

    return "updated" if doc.metadata.doc_id in stored_checksums else "added"


if __name__ == "__main__":
    mode = os.environ.get("INGESTION_MODE", "incremental")
    stats = run_ingestion(mode)
    print(f"Ingestion complete: {stats}")
```

### 5.3 Cloud Run Job Definition

```yaml
# deploy/cloud-run-job.yaml
apiVersion: run.googleapis.com/v1
kind: Job
metadata:
  name: kb-ingestion
  annotations:
    run.googleapis.com/launch-stage: BETA
spec:
  template:
    spec:
      template:
        spec:
          containers:
            - image: gcr.io/${PROJECT_ID}/kb-ingestion:latest
              env:
                - name: PROJECT_ID
                  value: ${PROJECT_ID}
                - name: LOCATION
                  value: australia-southeast1
                - name: KB_BUCKET
                  value: ${PROJECT_ID}-kb-documents
                - name: BQ_DATASET
                  value: conversation_coach
                - name: INDEX_ENDPOINT_ID
                  value: ${INDEX_ENDPOINT_ID}
                - name: DEPLOYED_INDEX_ID
                  value: kb-index-deployed
              resources:
                limits:
                  cpu: "2"
                  memory: "4Gi"
          timeoutSeconds: 3600
          serviceAccountName: kb-ingestion-sa@${PROJECT_ID}.iam.gserviceaccount.com
```

---

## 6. Retrieval Implementation

### 6.1 Retrieval Service

```python
# cc_coach/retrieval/rag_retriever.py

from typing import List, Optional
from dataclasses import dataclass
from google.cloud import bigquery
from vertexai.language_models import TextEmbeddingModel


@dataclass
class RetrievedChunk:
    """A chunk retrieved from the knowledge base."""
    chunk_id: str
    doc_id: str
    doc_type: str
    section_path: str
    content: str
    score: float
    priority: str


class RAGRetriever:
    """Retrieve relevant context from the knowledge base."""

    def __init__(
        self,
        project: str,
        location: str,
        index_endpoint_id: str,
        deployed_index_id: str,
        bq_dataset: str,
    ):
        self.project = project
        self.location = location
        self.index_endpoint_id = index_endpoint_id
        self.deployed_index_id = deployed_index_id
        self.bq_dataset = bq_dataset

        # Initialize clients
        self.embedding_model = TextEmbeddingModel.from_pretrained(
            "text-embedding-005"
        )
        self.bq_client = bigquery.Client()

        # Initialize Vector Search client
        from google.cloud import aiplatform
        aiplatform.init(project=project, location=location)

        self.index_endpoint = aiplatform.MatchingEngineIndexEndpoint(
            index_endpoint_id
        )

    def retrieve(
        self,
        query: str,
        business_line: str = "COLLECTIONS",
        doc_types: Optional[List[str]] = None,
        top_k: int = 10,
        min_score: float = 0.5,
    ) -> List[RetrievedChunk]:
        """
        Retrieve relevant chunks for a query.

        Args:
            query: The search query
            business_line: Filter by business line
            doc_types: Filter by document types (None = all)
            top_k: Number of results to return
            min_score: Minimum similarity score

        Returns:
            List of retrieved chunks with content
        """
        # 1. Generate query embedding
        embedding = self._embed_query(query)

        # 2. Build filters
        restricts = [
            {"namespace": "status", "allow_list": ["active"]},
            {"namespace": "business_line", "allow_list": [business_line]},
        ]

        if doc_types:
            restricts.append({
                "namespace": "doc_type",
                "allow_list": doc_types,
            })

        # 3. Query Vector Search
        response = self.index_endpoint.find_neighbors(
            deployed_index_id=self.deployed_index_id,
            queries=[embedding],
            num_neighbors=top_k,
            restricts=restricts,
        )

        # 4. Filter by score and get chunk IDs
        chunk_ids = []
        scores = {}

        for neighbor in response[0]:
            if neighbor.distance >= min_score:
                chunk_ids.append(neighbor.id)
                scores[neighbor.id] = neighbor.distance

        if not chunk_ids:
            return []

        # 5. Fetch content from BigQuery
        chunks = self._fetch_chunks_from_bq(chunk_ids)

        # 6. Combine with scores and return
        results = []
        for chunk in chunks:
            results.append(RetrievedChunk(
                chunk_id=chunk["chunk_id"],
                doc_id=chunk["doc_id"],
                doc_type=chunk["doc_type"],
                section_path=chunk["section_path"],
                content=chunk["content"],
                score=scores[chunk["chunk_id"]],
                priority=chunk["priority"],
            ))

        # Sort by score (highest first)
        results.sort(key=lambda x: x.score, reverse=True)

        return results

    def _embed_query(self, query: str) -> List[float]:
        """Generate embedding for search query."""
        embeddings = self.embedding_model.get_embeddings(
            texts=[query],
            task_type="RETRIEVAL_QUERY",
        )
        return embeddings[0].values

    def _fetch_chunks_from_bq(self, chunk_ids: List[str]) -> List[dict]:
        """Fetch chunk content from BigQuery."""
        # Use parameterized query for safety
        query = f"""
            SELECT
                chunk_id,
                doc_id,
                doc_type,
                section_path,
                content,
                priority
            FROM `{self.project}.{self.bq_dataset}.kb_chunks`
            WHERE chunk_id IN UNNEST(@chunk_ids)
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("chunk_ids", "STRING", chunk_ids)
            ]
        )

        results = self.bq_client.query(query, job_config=job_config)

        return [dict(row) for row in results]
```

### 6.2 Integration with Coach Agent

```python
# cc_coach/agents/coach.py

class ConversationCoach:
    """Coach agent with RAG integration."""

    def __init__(self, config: CoachConfig):
        self.config = config

        # Initialize RAG retriever
        self.retriever = RAGRetriever(
            project=config.project_id,
            location=config.location,
            index_endpoint_id=config.index_endpoint_id,
            deployed_index_id=config.deployed_index_id,
            bq_dataset=config.bq_dataset,
        )

        # Initialize generation model
        self.model = GenerativeModel("gemini-1.5-flash")

    def coach_conversation(
        self,
        transcript: str,
        business_line: str = "COLLECTIONS",
    ) -> CoachingResponse:
        """
        Coach a conversation using RAG.

        1. Analyze transcript to extract key topics
        2. Retrieve relevant policy and coaching context
        3. Generate coaching feedback with citations
        """
        # 1. Extract topics for retrieval
        topics = self._extract_topics(transcript)

        # 2. Retrieve relevant context
        all_chunks = []

        # Get policy context (compliance)
        policy_chunks = self.retriever.retrieve(
            query=f"compliance rules for: {topics}",
            business_line=business_line,
            doc_types=["policy"],
            top_k=5,
        )
        all_chunks.extend(policy_chunks)

        # Get coaching context (best practices)
        coaching_chunks = self.retriever.retrieve(
            query=f"coaching guidance for: {topics}",
            business_line=business_line,
            doc_types=["coaching", "example"],
            top_k=5,
        )
        all_chunks.extend(coaching_chunks)

        # 3. Build context for generation
        context = self._build_context(all_chunks)

        # 4. Generate coaching response
        response = self._generate_coaching(transcript, context)

        # 5. Add citations
        response.citations = self._extract_citations(all_chunks)

        return response

    def _build_context(self, chunks: List[RetrievedChunk]) -> str:
        """Build context string from retrieved chunks."""
        context_parts = []

        for chunk in chunks:
            context_parts.append(
                f"[{chunk.doc_id}] {chunk.section_path}:\n{chunk.content}"
            )

        return "\n\n---\n\n".join(context_parts)
```

---

## 7. Production Operations

### 7.1 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEPLOYMENT ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         PRODUCTION                                   │   │
│  │                                                                      │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │   │
│  │  │ GCS Bucket   │    │ Cloud Run    │    │ Vector Search        │  │   │
│  │  │ (documents)  │    │ Job          │    │ Endpoint             │  │   │
│  │  │              │    │ (ingestion)  │    │ (1 replica min)      │  │   │
│  │  └──────────────┘    └──────────────┘    └──────────────────────┘  │   │
│  │         │                   │                       │              │   │
│  │         │            ┌──────┴──────┐               │              │   │
│  │         │            │   BigQuery  │◄──────────────┘              │   │
│  │         │            │  (metadata) │                              │   │
│  │         │            └─────────────┘                              │   │
│  │         │                                                          │   │
│  │         ▼                                                          │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │   │
│  │  │ Cloud Build  │    │ Cloud        │    │ Cloud Run            │  │   │
│  │  │ (CI/CD)      │    │ Scheduler    │    │ Service (Coach)      │  │   │
│  │  └──────────────┘    │ (weekly)     │    │                      │  │   │
│  │                      └──────────────┘    └──────────────────────┘  │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  TRIGGERS                                                                   │
│  ────────                                                                   │
│  • Git merge → Cloud Build → GCS sync → Ingestion job                      │
│  • Weekly schedule → Full refresh ingestion                                 │
│  • Manual → gcloud run jobs execute                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Monitoring & Alerting

```yaml
# monitoring/alerts.yaml

# Alert: Ingestion job failed
- name: kb-ingestion-failed
  condition: >
    resource.type="cloud_run_job"
    AND resource.labels.job_name="kb-ingestion"
    AND jsonPayload.status="FAILED"
  notification_channels: [ops-team-email]
  severity: WARNING

# Alert: Vector Search endpoint unhealthy
- name: vector-search-unhealthy
  condition: >
    metric.type="aiplatform.googleapis.com/matching_engine/index_endpoint/query_count"
    AND metric.labels.response_code != "OK"
  threshold:
    comparison: COMPARISON_GT
    threshold_value: 10
    duration: 300s
  notification_channels: [ops-team-pager]
  severity: CRITICAL

# Alert: High retrieval latency
- name: retrieval-latency-high
  condition: >
    metric.type="aiplatform.googleapis.com/matching_engine/index_endpoint/query_latencies"
  threshold:
    comparison: COMPARISON_GT
    threshold_value: 500  # ms
    duration: 300s
    aggregation:
      alignment_period: 60s
      per_series_aligner: ALIGN_PERCENTILE_99
  notification_channels: [ops-team-email]
  severity: WARNING
```

### 7.3 Logging Strategy

```python
# kb_ingestion/utils/logging.py

import json
import logging
from datetime import datetime


class StructuredLogger:
    """Structured logging for Cloud Logging."""

    def __init__(self, component: str):
        self.component = component
        self.logger = logging.getLogger(component)

    def log(self, level: str, message: str, **kwargs):
        """Log structured message."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "component": self.component,
            "message": message,
            "severity": level.upper(),
            **kwargs,
        }

        # Cloud Logging expects JSON on stdout
        print(json.dumps(entry))

    def info(self, message: str, **kwargs):
        self.log("INFO", message, **kwargs)

    def error(self, message: str, **kwargs):
        self.log("ERROR", message, **kwargs)

    def metric(self, metric_name: str, value: float, labels: dict = None):
        """Log a custom metric."""
        self.log("INFO", f"metric:{metric_name}", **{
            "metric_name": metric_name,
            "metric_value": value,
            "metric_labels": labels or {},
        })


# Usage in ingestion
logger = StructuredLogger("kb-ingestion")

logger.info("Starting ingestion", mode="full_refresh", bucket="kb-docs")

logger.metric(
    "documents_processed",
    value=15,
    labels={"mode": "full_refresh", "status": "success"}
)
```

### 7.4 Health Checks

```python
# cc_coach/health.py

from dataclasses import dataclass
from typing import Dict


@dataclass
class HealthStatus:
    healthy: bool
    checks: Dict[str, bool]
    message: str


def check_rag_health(retriever: RAGRetriever) -> HealthStatus:
    """Check RAG system health."""
    checks = {}

    # Check 1: Vector Search endpoint
    try:
        # Simple query to verify connectivity
        results = retriever.retrieve(
            query="test query",
            top_k=1,
        )
        checks["vector_search"] = True
    except Exception as e:
        checks["vector_search"] = False

    # Check 2: BigQuery connectivity
    try:
        retriever.bq_client.query("SELECT 1").result()
        checks["bigquery"] = True
    except Exception:
        checks["bigquery"] = False

    # Check 3: Embedding API
    try:
        retriever._embed_query("test")
        checks["embedding_api"] = True
    except Exception:
        checks["embedding_api"] = False

    healthy = all(checks.values())

    return HealthStatus(
        healthy=healthy,
        checks=checks,
        message="All systems operational" if healthy else "Degraded",
    )
```

---

## 8. Cost Analysis

### 8.1 Component Costs (australia-southeast1)

| Component | Pricing Model | Estimated Monthly Cost |
|-----------|---------------|------------------------|
| **Vector Search Index** | $0.35/node-hour | ~$250/month (1 node, 24/7) |
| **Embedding API** | $0.00002/1K chars | ~$1/month (low volume) |
| **Cloud Storage** | $0.020/GB/month | ~$1/month (<1GB docs) |
| **BigQuery** | $0.02/GB scanned | ~$5/month (low queries) |
| **Cloud Run Job** | $0.00002400/vCPU-sec | ~$1/month (occasional runs) |
| **Gemini 1.5 Flash** | $0.075/1M input tokens | Included in coach costs |

### 8.2 Cost Breakdown by Phase

| Phase | Monthly Cost | Notes |
|-------|--------------|-------|
| **POC (Minimal)** | ~$260 | 1 Vector Search node, minimal queries |
| **Development** | ~$300 | More frequent ingestion, testing |
| **Production** | ~$500+ | Higher query volume, monitoring |

### 8.3 Cost Optimization Strategies

#### Strategy 1: Vector Search Sizing

```python
# POC: Use smallest configuration
SHARD_SIZE = "SHARD_SIZE_SMALL"  # < 100K vectors
MACHINE_TYPE = "e2-standard-2"   # 2 vCPU, 8GB
MIN_REPLICAS = 1
MAX_REPLICAS = 1                 # No auto-scaling for POC

# Production: Scale based on QPS
# 1 replica handles ~100 QPS
# Add replicas for higher throughput
```

#### Strategy 2: Embedding Batching

```python
# Batch embeddings to reduce API calls
# Each call can process up to 250 texts

def efficient_embed(texts: List[str]) -> List[List[float]]:
    # Instead of N calls for N texts
    # Make ceil(N/250) calls
    batch_size = 250
    results = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = model.get_embeddings(batch)
        results.extend([e.values for e in embeddings])

    return results
```

#### Strategy 3: Caching Query Embeddings

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_cached_query_embedding(query: str) -> tuple:
    """Cache common queries to reduce embedding costs."""
    embedding = embed_query(query)
    return tuple(embedding)  # Hashable for cache
```

#### Strategy 4: Reduce Vector Search Costs (Dev/POC)

```python
# Option: Use BigQuery vector search for POC (no dedicated endpoint)
# Pros: No minimum cost, pay per query
# Cons: Higher latency, less features

# In BQ, store embeddings directly
"""
CREATE TABLE kb_chunks_with_embeddings (
  chunk_id STRING,
  content STRING,
  embedding ARRAY<FLOAT64>
);
"""

# Query with BQ vector search
"""
SELECT
  chunk_id,
  content,
  ML.DISTANCE(embedding, @query_embedding, 'COSINE') as distance
FROM kb_chunks_with_embeddings
ORDER BY distance
LIMIT 10
"""
```

### 8.4 Cost Monitoring

```sql
-- Query to monitor embedding API costs
SELECT
  DATE(usage_start_time) as date,
  service.description,
  sku.description,
  SUM(cost) as daily_cost,
  SUM(usage.amount) as usage_amount,
  usage.unit
FROM `billing_export.gcp_billing_export_v1_*`
WHERE service.description LIKE '%Vertex AI%'
  AND DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 1, 2, 3, 6
ORDER BY 1 DESC, 4 DESC
```

---

## 9. Security

### 9.1 IAM Roles

```yaml
# Service Accounts and Roles

# Ingestion Job SA
kb-ingestion-sa@${PROJECT}.iam.gserviceaccount.com:
  roles:
    - roles/storage.objectViewer           # Read from GCS
    - roles/bigquery.dataEditor            # Write to BQ
    - roles/aiplatform.user                # Embedding API
    - roles/aiplatform.indexEndpointUser   # Vector Search write

# Coach Service SA
coach-service-sa@${PROJECT}.iam.gserviceaccount.com:
  roles:
    - roles/bigquery.dataViewer            # Read from BQ
    - roles/aiplatform.user                # Embedding API + Gemini
    - roles/aiplatform.indexEndpointUser   # Vector Search query
```

### 9.2 Data Security

```python
# No PII in knowledge base documents
# All documents are internal policies and coaching materials

# Query sanitization
def sanitize_query(query: str) -> str:
    """Remove any potential PII from retrieval queries."""
    # Remove common PII patterns
    import re

    # Phone numbers
    query = re.sub(r'\b\d{10,11}\b', '[PHONE]', query)

    # Email addresses
    query = re.sub(r'\b[\w.-]+@[\w.-]+\.\w+\b', '[EMAIL]', query)

    # Credit card numbers
    query = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[CC]', query)

    return query
```

---

## 10. Implementation Plan

### 10.1 Phase 1: Infrastructure Setup (Week 1)

| Task | Description | Owner |
|------|-------------|-------|
| Create GCS bucket | `${PROJECT}-kb-documents` | Platform |
| Create BQ dataset/tables | As per rag_knowledge_base_design.md | Platform |
| Create Vector Search index | Configure with 768 dimensions | Platform |
| Deploy index endpoint | 1 replica, e2-standard-2 | Platform |
| Create service accounts | Ingestion SA, Coach SA | Platform |

### 10.2 Phase 2: Ingestion Pipeline (Week 2)

| Task | Description | Owner |
|------|-------------|-------|
| Implement parser | As per metadata_management_design.md | Dev |
| Implement chunker | Section-based chunking | Dev |
| Implement embedding service | Batch embedding generation | Dev |
| Implement vector store client | Upsert/delete operations | Dev |
| Build Cloud Run Job | Container + deployment | Dev |
| Initial document load | Upload and ingest documents | Dev |

### 10.3 Phase 3: Retrieval Integration (Week 3)

| Task | Description | Owner |
|------|-------------|-------|
| Implement RAGRetriever | Query with filters | Dev |
| Integrate with Coach | Add context to coaching | Dev |
| Add citations | Track which docs were used | Dev |
| Testing | End-to-end retrieval tests | Dev |

### 10.4 Phase 4: Operations (Week 4)

| Task | Description | Owner |
|------|-------------|-------|
| Set up CI/CD | Cloud Build triggers | DevOps |
| Configure monitoring | Dashboards and alerts | DevOps |
| Set up Cloud Scheduler | Weekly full refresh | DevOps |
| Documentation | Runbooks, troubleshooting | Team |

---

## 11. Appendix

### 11.1 Terraform Resources

```hcl
# terraform/rag_pipeline.tf

# GCS Bucket for documents
resource "google_storage_bucket" "kb_documents" {
  name     = "${var.project_id}-kb-documents"
  location = var.region

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

# Vector Search Index
resource "google_vertex_ai_index" "kb_index" {
  display_name = "conversation-coach-kb-index"
  region       = var.region

  metadata {
    contents_delta_uri = "gs://${google_storage_bucket.kb_documents.name}/index-data/"
    config {
      dimensions                  = 768
      approximate_neighbors_count = 10
      shard_size                  = "SHARD_SIZE_SMALL"
      distance_measure_type       = "DOT_PRODUCT_DISTANCE"

      algorithm_config {
        tree_ah_config {
          leaf_node_embedding_count    = 1000
          leaf_nodes_to_search_percent = 10
        }
      }
    }
  }

  index_update_method = "STREAM_UPDATE"
}

# Vector Search Endpoint
resource "google_vertex_ai_index_endpoint" "kb_endpoint" {
  display_name = "conversation-coach-kb-endpoint"
  region       = var.region
}

# Cloud Run Job
resource "google_cloud_run_v2_job" "kb_ingestion" {
  name     = "kb-ingestion"
  location = var.region

  template {
    template {
      containers {
        image = "gcr.io/${var.project_id}/kb-ingestion:latest"

        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "KB_BUCKET"
          value = google_storage_bucket.kb_documents.name
        }
        env {
          name  = "INDEX_ENDPOINT_ID"
          value = google_vertex_ai_index_endpoint.kb_endpoint.id
        }

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }
      }

      service_account = google_service_account.kb_ingestion.email
      timeout         = "3600s"
    }
  }
}

# Cloud Scheduler for weekly refresh
resource "google_cloud_scheduler_job" "weekly_refresh" {
  name     = "kb-weekly-refresh"
  region   = var.region
  schedule = "0 2 * * 0"  # 2 AM every Sunday

  http_target {
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/kb-ingestion:run"
    http_method = "POST"

    oauth_token {
      service_account_email = google_service_account.kb_ingestion.email
    }
  }
}
```

### 11.2 Quick Reference: Key Commands

```bash
# Trigger manual ingestion
gcloud run jobs execute kb-ingestion \
  --region=australia-southeast1 \
  --update-env-vars INGESTION_MODE=full_refresh

# Check job status
gcloud run jobs executions list --job=kb-ingestion

# Query Vector Search (debug)
gcloud ai index-endpoints query \
  --region=australia-southeast1 \
  --index-endpoint=${ENDPOINT_ID} \
  --deployed-index-id=kb-index-deployed \
  --num-neighbors=5 \
  --queries='[0.1, 0.2, ...]'  # embedding vector

# Sync documents to GCS
gsutil -m rsync -r documents/ gs://${PROJECT}-kb-documents/documents/
```

### 11.3 Troubleshooting Guide

| Issue | Possible Cause | Solution |
|-------|---------------|----------|
| "Index not found" | Endpoint not deployed | Deploy index to endpoint |
| "Permission denied" | SA missing role | Add aiplatform.user role |
| Low retrieval quality | Wrong task_type | Use RETRIEVAL_QUERY for search |
| High latency | Cold start | Increase min replicas |
| Empty results | Filters too strict | Check business_line filter |
