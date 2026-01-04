"""BigQuery metadata store for RAG document management.

Provides operations for:
- Document metadata storage and retrieval
- Version history tracking
- Retrieval audit logging
"""

import uuid as uuid_lib
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional

from google.cloud import bigquery

from cc_coach.rag.config import RAGConfig
from cc_coach.rag.parser import DocumentMetadata


class MetadataStore:
    """BigQuery metadata store for knowledge base documents."""

    def __init__(self, config: RAGConfig):
        """Initialize metadata store.

        Args:
            config: RAG configuration
        """
        self.config = config
        self._client: Optional[bigquery.Client] = None

    @property
    def client(self) -> bigquery.Client:
        """Lazy-load BigQuery client."""
        if self._client is None:
            self._client = bigquery.Client(project=self.config.project_id)
        return self._client

    def get_document(self, uuid: str) -> Optional[dict[str, Any]]:
        """Get document by UUID.

        Args:
            uuid: Document UUID

        Returns:
            Document metadata dict or None if not found
        """
        query = f"""
            SELECT *
            FROM `{self.config.bq_documents_full_table}`
            WHERE uuid = @uuid
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("uuid", "STRING", uuid)
            ]
        )
        result = self.client.query(query, job_config=job_config).result()
        rows = list(result)
        return dict(rows[0]) if rows else None

    def get_document_by_id_version(
        self, doc_id: str, version: str
    ) -> Optional[dict[str, Any]]:
        """Get document by doc_id and version.

        Args:
            doc_id: Human-readable document ID (e.g., POL-002)
            version: Semantic version (e.g., 1.1.0)

        Returns:
            Document metadata dict or None if not found
        """
        query = f"""
            SELECT *
            FROM `{self.config.bq_documents_full_table}`
            WHERE doc_id = @doc_id AND version = @version
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("doc_id", "STRING", doc_id),
                bigquery.ScalarQueryParameter("version", "STRING", version),
            ]
        )
        result = self.client.query(query, job_config=job_config).result()
        rows = list(result)
        return dict(rows[0]) if rows else None

    def get_active_documents(self) -> list[dict[str, Any]]:
        """Get all active documents.

        Returns:
            List of document metadata dicts with status='active'
        """
        query = f"""
            SELECT *
            FROM `{self.config.bq_documents_full_table}`
            WHERE status = 'active'
            ORDER BY doc_type, doc_id
        """
        result = self.client.query(query).result()
        return [dict(row) for row in result]

    def get_all_checksums(self) -> dict[str, str]:
        """Get checksums for all documents.

        Returns:
            Dict mapping UUID to checksum for change detection
        """
        query = f"""
            SELECT uuid, checksum
            FROM `{self.config.bq_documents_full_table}`
        """
        result = self.client.query(query).result()
        return {row["uuid"]: row["checksum"] for row in result}

    def get_active_uuids(self) -> set[str]:
        """Get UUIDs of all active documents.

        Returns:
            Set of UUIDs for documents with status='active'
        """
        query = f"""
            SELECT uuid
            FROM `{self.config.bq_documents_full_table}`
            WHERE status = 'active'
        """
        result = self.client.query(query).result()
        return {row["uuid"] for row in result}

    def upsert_document(
        self, metadata: DocumentMetadata, raw_content: str
    ) -> bool:
        """Insert or update document in BQ.

        Uses MERGE to handle upsert logic:
        - If UUID exists with same checksum: skip (no change)
        - If UUID exists with different checksum: update
        - If UUID doesn't exist: insert

        Args:
            metadata: Parsed document metadata
            raw_content: Full document content including frontmatter

        Returns:
            True if document was inserted/updated, False if skipped
        """
        # Helper to convert date to string
        def date_to_str(val):
            """Convert date/datetime to string, handling if already string."""
            if val is None:
                return None
            if isinstance(val, str):
                return val
            if hasattr(val, 'isoformat'):
                return val.isoformat()
            return str(val)

        # Convert metadata to dict for BQ
        doc_dict = {
            "uuid": metadata.uuid,
            "doc_id": metadata.doc_id,
            "doc_type": metadata.doc_type,
            "title": metadata.title,
            "version": metadata.version,
            "file_path": metadata.file_path,
            "status": metadata.status,
            "status_reason": metadata.status_reason,
            "superseded_by": metadata.superseded_by,
            "status_changed_at": datetime.utcnow().isoformat() if metadata.status else None,
            "business_lines": metadata.business_lines or [],
            "queues": metadata.queues or [],
            "regions": metadata.regions or [],
            "raw_content": raw_content,
            "checksum": metadata.checksum,
            "author": metadata.author,
            "approved_by": metadata.approved_by,
            "effective_date": date_to_str(metadata.effective_date),
            "expiry_date": date_to_str(metadata.expiry_date),
            "last_reviewed": date_to_str(metadata.last_reviewed),
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Check if document exists
        existing = self.get_document(metadata.uuid)

        if existing:
            if existing["checksum"] == metadata.checksum:
                # No change, skip
                return False

            # Update existing document
            query = f"""
                UPDATE `{self.config.bq_documents_full_table}`
                SET
                    title = @title,
                    status = @status,
                    status_reason = @status_reason,
                    superseded_by = @superseded_by,
                    status_changed_at = @status_changed_at,
                    business_lines = @business_lines,
                    queues = @queues,
                    regions = @regions,
                    raw_content = @raw_content,
                    checksum = @checksum,
                    author = @author,
                    approved_by = @approved_by,
                    effective_date = @effective_date,
                    expiry_date = @expiry_date,
                    last_reviewed = @last_reviewed,
                    updated_at = @updated_at
                WHERE uuid = @uuid
            """
        else:
            # Insert new document
            doc_dict["created_at"] = datetime.utcnow().isoformat()

            query = f"""
                INSERT INTO `{self.config.bq_documents_full_table}`
                (uuid, doc_id, doc_type, title, version, file_path, status,
                 status_reason, superseded_by, status_changed_at,
                 business_lines, queues, regions, raw_content, checksum,
                 author, approved_by, effective_date, expiry_date, last_reviewed,
                 created_at, updated_at)
                VALUES
                (@uuid, @doc_id, @doc_type, @title, @version, @file_path, @status,
                 @status_reason, @superseded_by, @status_changed_at,
                 @business_lines, @queues, @regions, @raw_content, @checksum,
                 @author, @approved_by, @effective_date, @expiry_date, @last_reviewed,
                 @created_at, @updated_at)
            """

        # Build query parameters
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("uuid", "STRING", doc_dict["uuid"]),
                bigquery.ScalarQueryParameter("doc_id", "STRING", doc_dict["doc_id"]),
                bigquery.ScalarQueryParameter("doc_type", "STRING", doc_dict["doc_type"]),
                bigquery.ScalarQueryParameter("title", "STRING", doc_dict["title"]),
                bigquery.ScalarQueryParameter("version", "STRING", doc_dict["version"]),
                bigquery.ScalarQueryParameter("file_path", "STRING", doc_dict["file_path"]),
                bigquery.ScalarQueryParameter("status", "STRING", doc_dict["status"]),
                bigquery.ScalarQueryParameter("status_reason", "STRING", doc_dict.get("status_reason")),
                bigquery.ScalarQueryParameter("superseded_by", "STRING", doc_dict.get("superseded_by")),
                bigquery.ScalarQueryParameter("status_changed_at", "TIMESTAMP", doc_dict.get("status_changed_at")),
                bigquery.ArrayQueryParameter("business_lines", "STRING", doc_dict["business_lines"]),
                bigquery.ArrayQueryParameter("queues", "STRING", doc_dict["queues"]),
                bigquery.ArrayQueryParameter("regions", "STRING", doc_dict["regions"]),
                bigquery.ScalarQueryParameter("raw_content", "STRING", doc_dict["raw_content"]),
                bigquery.ScalarQueryParameter("checksum", "STRING", doc_dict["checksum"]),
                bigquery.ScalarQueryParameter("author", "STRING", doc_dict.get("author")),
                bigquery.ScalarQueryParameter("approved_by", "STRING", doc_dict.get("approved_by")),
                bigquery.ScalarQueryParameter("effective_date", "DATE", doc_dict.get("effective_date")),
                bigquery.ScalarQueryParameter("expiry_date", "DATE", doc_dict.get("expiry_date")),
                bigquery.ScalarQueryParameter("last_reviewed", "DATE", doc_dict.get("last_reviewed")),
                bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", doc_dict.get("created_at")),
                bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", doc_dict["updated_at"]),
            ]
        )

        self.client.query(query, job_config=job_config).result()
        return True

    def log_retrieval(
        self,
        conversation_id: str,
        query_text: str,
        retrieved_docs: list[dict[str, Any]],
        coach_model_version: Optional[str] = None,
        prompt_version: Optional[str] = None,
        business_line: Optional[str] = None,
    ) -> str:
        """Log a RAG retrieval for audit purposes.

        Args:
            conversation_id: ID of the coaching conversation
            query_text: The query sent to Vertex AI Search
            retrieved_docs: List of retrieved document info
            coach_model_version: Model used for coaching
            prompt_version: Version of coaching prompt
            business_line: Business context

        Returns:
            Generated retrieval_id
        """
        retrieval_id = str(uuid_lib.uuid4())

        # Format retrieved_docs for BQ ARRAY<STRUCT>
        docs_struct = [
            {
                "uuid": doc.get("uuid", ""),
                "doc_id": doc.get("doc_id", ""),
                "version": doc.get("version", ""),
                "section": doc.get("section", ""),
                "snippet": (doc.get("snippet", "") or "")[:1000],  # Truncate snippet
                "relevance_score": float(doc.get("relevance_score", 0.0)),
            }
            for doc in retrieved_docs
        ]

        # Use insert_rows_json for complex nested structures (more reliable)
        row = {
            "retrieval_id": retrieval_id,
            "conversation_id": conversation_id,
            "query_text": query_text,
            "retrieved_docs": docs_struct,
            "coach_model_version": coach_model_version,
            "prompt_version": prompt_version,
            "business_line": business_line,
            "retrieved_at": datetime.utcnow().isoformat(),
        }

        errors = self.client.insert_rows_json(
            self.config.bq_retrieval_log_full_table, [row]
        )
        if errors:
            raise RuntimeError(f"Failed to log retrieval: {errors}")

        return retrieval_id

    def get_kb_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics.

        Returns:
            Dict with document counts by status and type
        """
        query = f"""
            SELECT
                COUNT(*) as total_docs,
                COUNTIF(status = 'active') as active_docs,
                COUNTIF(status = 'superseded') as superseded_docs,
                COUNTIF(status = 'draft') as draft_docs,
                COUNTIF(status = 'retired') as retired_docs,
                COUNTIF(status = 'deleted') as deleted_docs
            FROM `{self.config.bq_documents_full_table}`
        """
        result = self.client.query(query).result()
        row = list(result)[0]
        return dict(row)

    def get_docs_by_type(self) -> dict[str, int]:
        """Get document counts grouped by doc_type.

        Returns:
            Dict mapping doc_type to count
        """
        query = f"""
            SELECT doc_type, COUNT(*) as count
            FROM `{self.config.bq_documents_full_table}`
            WHERE status = 'active'
            GROUP BY doc_type
            ORDER BY count DESC
        """
        result = self.client.query(query).result()
        return {row["doc_type"]: row["count"] for row in result}
