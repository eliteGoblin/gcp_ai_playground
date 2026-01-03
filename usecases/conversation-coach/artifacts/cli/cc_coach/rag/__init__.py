"""RAG (Retrieval-Augmented Generation) module for Conversation Coach.

This module provides:
- Document ingestion from local markdown files to BQ + GCS
- Retrieval from Vertex AI Search with BQ metadata enrichment
- Audit logging for all retrievals

Architecture:
- Local files (source of truth) -> BQ (metadata mirror) -> GCS (active docs) -> Vertex AI Search
- Immutable artifact model: documents never update, only supersede
- Deterministic UUID generation from file_path + version
"""

from cc_coach.rag.config import RAGConfig
from cc_coach.rag.parser import parse_document, validate_metadata
from cc_coach.rag.metadata import MetadataStore
from cc_coach.rag.ingest import DocumentIngester
from cc_coach.rag.retriever import RAGRetriever

__all__ = [
    "RAGConfig",
    "parse_document",
    "validate_metadata",
    "MetadataStore",
    "DocumentIngester",
    "RAGRetriever",
]
