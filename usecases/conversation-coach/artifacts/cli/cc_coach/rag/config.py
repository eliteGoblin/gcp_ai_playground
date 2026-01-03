"""Configuration for RAG pipeline.

Environment variables:
- GCP_PROJECT_ID: GCP project ID
- GCP_LOCATION: GCP region (default: australia-southeast1)
- RAG_GCS_BUCKET: GCS bucket for active documents
- RAG_DATA_STORE_ID: Vertex AI Search data store ID
- RAG_SEARCH_APP_ID: Vertex AI Search app ID (optional, uses data store if not set)
- BQ_DATASET: BigQuery dataset for metadata (default: conversation_coach)
"""

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# UUID namespace for deterministic generation (URL namespace from RFC 4122)
UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def generate_uuid(file_path: str, version: str) -> str:
    """Generate deterministic UUID from file path + version.

    Same inputs always produce same UUID, enabling:
    - Idempotent ingestion (re-running produces same UUIDs)
    - Verification of document existence without BQ query
    - Reproducible document identity

    Args:
        file_path: Relative path to document (e.g., "documents/policy/POL-002.md")
        version: Semantic version string (e.g., "1.1.0")

    Returns:
        UUID string in standard format
    """
    key = f"{file_path}:{version}"
    return str(uuid.uuid5(UUID_NAMESPACE, key))


@dataclass
class RAGConfig:
    """Configuration for RAG pipeline components."""

    # GCP settings
    project_id: str = field(
        default_factory=lambda: os.environ.get("GCP_PROJECT_ID", "")
    )
    location: str = field(
        default_factory=lambda: os.environ.get("GCP_LOCATION", "australia-southeast1")
    )

    # GCS settings for document storage
    gcs_bucket: str = field(
        default_factory=lambda: os.environ.get("RAG_GCS_BUCKET", "")
    )
    gcs_prefix: str = "kb"  # Prefix for KB documents in bucket

    # Vertex AI Search settings
    data_store_id: str = field(
        default_factory=lambda: os.environ.get("RAG_DATA_STORE_ID", "")
    )
    search_app_id: Optional[str] = field(
        default_factory=lambda: os.environ.get("RAG_SEARCH_APP_ID")
    )

    # BigQuery settings
    bq_dataset: str = field(
        default_factory=lambda: os.environ.get("BQ_DATASET", "conversation_coach")
    )
    bq_documents_table: str = "kb_documents"
    bq_retrieval_log_table: str = "kb_retrieval_log"

    # Local documents path (relative to project root)
    documents_path: Path = field(
        default_factory=lambda: Path("documents")
    )

    # Retrieval settings
    default_top_k: int = 5
    min_relevance_score: float = 0.3

    def __post_init__(self):
        """Validate configuration after initialization."""
        if isinstance(self.documents_path, str):
            self.documents_path = Path(self.documents_path)

    @property
    def gcs_documents_uri(self) -> str:
        """Full GCS URI for documents folder."""
        return f"gs://{self.gcs_bucket}/{self.gcs_prefix}"

    @property
    def bq_documents_full_table(self) -> str:
        """Fully qualified BQ table name for documents."""
        return f"{self.project_id}.{self.bq_dataset}.{self.bq_documents_table}"

    @property
    def bq_retrieval_log_full_table(self) -> str:
        """Fully qualified BQ table name for retrieval log."""
        return f"{self.project_id}.{self.bq_dataset}.{self.bq_retrieval_log_table}"

    @property
    def vertex_search_serving_config(self) -> str:
        """Vertex AI Search serving config path."""
        return (
            f"projects/{self.project_id}/locations/{self.location}"
            f"/dataStores/{self.data_store_id}/servingConfigs/default_search"
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if not self.project_id:
            errors.append("GCP_PROJECT_ID is required")
        if not self.gcs_bucket:
            errors.append("RAG_GCS_BUCKET is required")
        if not self.data_store_id:
            errors.append("RAG_DATA_STORE_ID is required")

        return errors

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Create config from environment variables."""
        return cls()


# Valid document statuses
VALID_STATUSES = {"active", "superseded", "retired", "deleted", "draft"}

# Valid document types
VALID_DOC_TYPES = {"policy", "coaching", "example", "external"}

# Required metadata fields
REQUIRED_METADATA_FIELDS = {"doc_id", "title", "version", "status", "doc_type"}
