"""
BigQuery service for Conversation Coach.

Handles:
- UPSERT operations for conversation_registry
- CI export data ingestion
- Query operations for pipeline state
- Schema management using schema-as-code (JSON schemas)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from cc_coach.config import Settings, get_settings
from cc_coach.models.registry import ConversationRegistry, RegistryStatus
from cc_coach.schemas import get_bq_schema, get_schema_metadata

logger = logging.getLogger(__name__)


# BigQuery table schemas
REGISTRY_SCHEMA = [
    bigquery.SchemaField("conversation_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("transcript_uri_raw", "STRING"),
    bigquery.SchemaField("metadata_uri_raw", "STRING"),
    bigquery.SchemaField("audio_uri_raw", "STRING"),
    bigquery.SchemaField("transcript_uri_sanitized", "STRING"),
    bigquery.SchemaField("metadata_uri_sanitized", "STRING"),
    bigquery.SchemaField("audio_uri_sanitized", "STRING"),
    bigquery.SchemaField("has_transcript", "BOOLEAN"),
    bigquery.SchemaField("has_metadata", "BOOLEAN"),
    bigquery.SchemaField("has_audio", "BOOLEAN"),
    bigquery.SchemaField("status", "STRING"),
    bigquery.SchemaField("redaction_version", "STRING"),
    bigquery.SchemaField("pii_types_found", "STRING", mode="REPEATED"),
    bigquery.SchemaField("ci_conversation_name", "STRING"),
    bigquery.SchemaField("ci_analysis_id", "STRING"),
    bigquery.SchemaField("last_error", "STRING"),
    bigquery.SchemaField("retry_count", "INTEGER"),
    bigquery.SchemaField("created_at", "TIMESTAMP"),
    bigquery.SchemaField("updated_at", "TIMESTAMP"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
    bigquery.SchemaField("enriched_at", "TIMESTAMP"),
    bigquery.SchemaField("coached_at", "TIMESTAMP"),
]

CI_ENRICHMENT_SCHEMA = [
    bigquery.SchemaField("conversation_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("ci_conversation_name", "STRING"),
    # Transcript data (from original transcription.json)
    bigquery.SchemaField("transcript", "STRING"),
    bigquery.SchemaField("turn_count", "INTEGER"),
    bigquery.SchemaField("duration_sec", "INTEGER"),
    # CI Analysis - customer sentiment (overall)
    # Note: CI does not analyze agent sentiment, only customer
    bigquery.SchemaField("customer_sentiment_score", "FLOAT"),
    bigquery.SchemaField("customer_sentiment_magnitude", "FLOAT"),
    # CI Analysis - per-turn customer sentiment
    bigquery.SchemaField(
        "per_turn_sentiments",
        "RECORD",
        mode="REPEATED",
        fields=[
            bigquery.SchemaField("turn_index", "INTEGER"),
            bigquery.SchemaField("score", "FLOAT"),
            bigquery.SchemaField("magnitude", "FLOAT"),
        ],
    ),
    # CI Analysis - entities
    bigquery.SchemaField(
        "entities",
        "RECORD",
        mode="REPEATED",
        fields=[
            bigquery.SchemaField("type", "STRING"),
            bigquery.SchemaField("name", "STRING"),
            bigquery.SchemaField("salience", "FLOAT"),
            bigquery.SchemaField("speaker_tag", "INTEGER"),
        ],
    ),
    # CI Analysis - topics/intents
    bigquery.SchemaField("topics", "STRING", mode="REPEATED"),
    # CI Summary (from conversation.latest_summary)
    bigquery.SchemaField("ci_summary_text", "STRING"),
    bigquery.SchemaField("ci_summary_resolution", "STRING"),
    # CI Phrase Matches (from runtime_annotations)
    bigquery.SchemaField(
        "phrase_matches",
        "RECORD",
        mode="REPEATED",
        fields=[
            bigquery.SchemaField("matcher_id", "STRING"),
            bigquery.SchemaField("display_name", "STRING"),
            bigquery.SchemaField("match_count", "INTEGER"),
            bigquery.SchemaField(
                "matches",
                "RECORD",
                mode="REPEATED",
                fields=[
                    bigquery.SchemaField("phrase", "STRING"),
                    bigquery.SchemaField("turn_index", "INTEGER"),
                    bigquery.SchemaField("speaker", "STRING"),
                    bigquery.SchemaField("text_snippet", "STRING"),
                ],
            ),
        ],
    ),
    # CI Flags (derived from phrase matches)
    bigquery.SchemaField("ci_flags", "STRING", mode="REPEATED"),
    bigquery.SchemaField("ci_flag_count", "INTEGER"),
    # Metadata labels (from original metadata.json)
    bigquery.SchemaField("labels", "JSON"),
    bigquery.SchemaField("analysis_completed_at", "TIMESTAMP"),
    bigquery.SchemaField("exported_at", "TIMESTAMP"),
]

# Coach analysis schema - now loaded from JSON schema file
# See: cc_coach/schemas/coach_analysis.json
# Use get_bq_schema("coach_analysis") to get the schema

# Legacy schema kept for reference (deprecated)
_LEGACY_COACHING_CARDS_SCHEMA = [
    bigquery.SchemaField("conversation_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("generated_at", "TIMESTAMP"),
    bigquery.SchemaField("coach_version", "STRING"),
    bigquery.SchemaField("summary_bullets", "STRING", mode="REPEATED"),
    bigquery.SchemaField("driver_label", "STRING"),
    bigquery.SchemaField("driver_score", "FLOAT"),
    bigquery.SchemaField("compliance_checks", "JSON"),
    bigquery.SchemaField("risk_flags", "STRING", mode="REPEATED"),
    bigquery.SchemaField("next_actions", "JSON"),
    bigquery.SchemaField("confidence_score", "FLOAT"),
    bigquery.SchemaField("model_id", "STRING"),
    bigquery.SchemaField("policy_version", "STRING"),
]


class BigQueryService:
    """Service for BigQuery operations."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize BigQuery service."""
        self.settings = settings or get_settings()
        self._client: Optional[bigquery.Client] = None

    @property
    def client(self) -> bigquery.Client:
        """Lazy-load BigQuery client."""
        if self._client is None:
            self._client = bigquery.Client(
                project=self.settings.project_id,
                location=self.settings.bq_location,
            )
        return self._client

    @property
    def dataset_ref(self) -> bigquery.DatasetReference:
        """Get dataset reference."""
        return bigquery.DatasetReference(
            self.settings.project_id,
            self.settings.bq_dataset,
        )

    def _table_id(self, table_name: str) -> str:
        """Get full table ID."""
        return f"{self.settings.project_id}.{self.settings.bq_dataset}.{table_name}"

    def ensure_dataset(self) -> bigquery.Dataset:
        """Create dataset if it doesn't exist."""
        dataset = bigquery.Dataset(self.dataset_ref)
        dataset.location = self.settings.bq_location
        dataset.description = "Conversation Coach pipeline data"
        dataset.labels = {
            "environment": "dev",
            "managed_by": "cc_coach_cli",
        }

        try:
            existing = self.client.get_dataset(self.dataset_ref)
            logger.info(f"Dataset {self.settings.bq_dataset} already exists")
            return existing
        except NotFound:
            created = self.client.create_dataset(dataset)
            logger.info(f"Created dataset {self.settings.bq_dataset}")
            return created

    def ensure_table(
        self,
        table_name: str,
        schema: list[bigquery.SchemaField],
        clustering_fields: Optional[list[str]] = None,
    ) -> bigquery.Table:
        """Create table if it doesn't exist."""
        table_ref = self.dataset_ref.table(table_name)
        table = bigquery.Table(table_ref, schema=schema)

        if clustering_fields:
            table.clustering_fields = clustering_fields

        table.description = f"Conversation Coach - {table_name}"

        try:
            existing = self.client.get_table(table_ref)
            logger.info(f"Table {table_name} already exists")
            return existing
        except NotFound:
            created = self.client.create_table(table)
            logger.info(f"Created table {table_name}")
            return created

    def ensure_all_tables(self) -> dict[str, bigquery.Table]:
        """Create all required tables."""
        self.ensure_dataset()

        # Core pipeline tables (hardcoded schemas)
        tables = {
            "conversation_registry": self.ensure_table(
                "conversation_registry",
                REGISTRY_SCHEMA,
                clustering_fields=["status"],
            ),
            "ci_enrichment": self.ensure_table(
                "ci_enrichment",
                CI_ENRICHMENT_SCHEMA,
            ),
        }

        # Coach tables (loaded from JSON schemas)
        coach_tables = [
            "coach_analysis",
            "daily_agent_summary",
            "weekly_agent_report",
        ]

        for schema_name in coach_tables:
            try:
                metadata = get_schema_metadata(schema_name)
                table_name = metadata.get("table_name", schema_name)
                clustering = metadata.get("clustering_fields")

                tables[table_name] = self.ensure_table(
                    table_name,
                    get_bq_schema(schema_name),
                    clustering_fields=clustering,
                )
            except FileNotFoundError:
                logger.warning(f"Schema file not found for {schema_name}, skipping")

        return tables

    def ensure_coach_tables(self) -> dict[str, bigquery.Table]:
        """Create only the coach-related tables (from JSON schemas)."""
        self.ensure_dataset()

        tables = {}
        coach_tables = [
            "coach_analysis",
            "daily_agent_summary",
            "weekly_agent_report",
        ]

        for schema_name in coach_tables:
            metadata = get_schema_metadata(schema_name)
            table_name = metadata.get("table_name", schema_name)
            clustering = metadata.get("clustering_fields")

            tables[table_name] = self.ensure_table(
                table_name,
                get_bq_schema(schema_name),
                clustering_fields=clustering,
            )

        return tables

    def upsert_registry(self, registry: ConversationRegistry) -> None:
        """
        UPSERT a conversation registry entry.

        Uses MERGE statement for idempotent updates.
        """
        table_id = self._table_id("conversation_registry")
        registry.updated_at = datetime.now(timezone.utc)

        # Use MERGE for UPSERT
        query = f"""
        MERGE `{table_id}` T
        USING (SELECT @conversation_id as conversation_id) S
        ON T.conversation_id = S.conversation_id
        WHEN MATCHED THEN
            UPDATE SET
                transcript_uri_raw = @transcript_uri_raw,
                metadata_uri_raw = @metadata_uri_raw,
                audio_uri_raw = @audio_uri_raw,
                has_transcript = @has_transcript,
                has_metadata = @has_metadata,
                has_audio = @has_audio,
                status = @status,
                ci_conversation_name = @ci_conversation_name,
                ci_analysis_id = @ci_analysis_id,
                last_error = @last_error,
                retry_count = @retry_count,
                updated_at = @updated_at,
                ingested_at = @ingested_at,
                enriched_at = @enriched_at,
                coached_at = @coached_at
        WHEN NOT MATCHED THEN
            INSERT (
                conversation_id, transcript_uri_raw, metadata_uri_raw, audio_uri_raw,
                has_transcript, has_metadata, has_audio, status,
                ci_conversation_name, ci_analysis_id, last_error, retry_count,
                created_at, updated_at, ingested_at, enriched_at, coached_at
            )
            VALUES (
                @conversation_id, @transcript_uri_raw, @metadata_uri_raw, @audio_uri_raw,
                @has_transcript, @has_metadata, @has_audio, @status,
                @ci_conversation_name, @ci_analysis_id, @last_error, @retry_count,
                @created_at, @updated_at, @ingested_at, @enriched_at, @coached_at
            )
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("conversation_id", "STRING", registry.conversation_id),
                bigquery.ScalarQueryParameter("transcript_uri_raw", "STRING", registry.transcript_uri_raw),
                bigquery.ScalarQueryParameter("metadata_uri_raw", "STRING", registry.metadata_uri_raw),
                bigquery.ScalarQueryParameter("audio_uri_raw", "STRING", registry.audio_uri_raw),
                bigquery.ScalarQueryParameter("has_transcript", "BOOL", registry.has_transcript),
                bigquery.ScalarQueryParameter("has_metadata", "BOOL", registry.has_metadata),
                bigquery.ScalarQueryParameter("has_audio", "BOOL", registry.has_audio),
                bigquery.ScalarQueryParameter("status", "STRING", registry.status.value),
                bigquery.ScalarQueryParameter("ci_conversation_name", "STRING", registry.ci_conversation_name),
                bigquery.ScalarQueryParameter("ci_analysis_id", "STRING", registry.ci_analysis_id),
                bigquery.ScalarQueryParameter("last_error", "STRING", registry.last_error),
                bigquery.ScalarQueryParameter("retry_count", "INT64", registry.retry_count),
                bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", registry.created_at),
                bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", registry.updated_at),
                bigquery.ScalarQueryParameter("ingested_at", "TIMESTAMP", registry.ingested_at),
                bigquery.ScalarQueryParameter("enriched_at", "TIMESTAMP", registry.enriched_at),
                bigquery.ScalarQueryParameter("coached_at", "TIMESTAMP", registry.coached_at),
            ]
        )

        self.client.query(query, job_config=job_config).result()
        logger.debug(f"Upserted registry entry for {registry.conversation_id}")

    def get_registry(self, conversation_id: str) -> Optional[ConversationRegistry]:
        """Get a registry entry by conversation ID."""
        table_id = self._table_id("conversation_registry")
        query = f"""
        SELECT * FROM `{table_id}`
        WHERE conversation_id = @conversation_id
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("conversation_id", "STRING", conversation_id),
            ]
        )

        rows = list(self.client.query(query, job_config=job_config).result())
        if not rows:
            return None

        return ConversationRegistry.from_bq_row(dict(rows[0]))

    def list_registry(
        self,
        status: Optional[RegistryStatus] = None,
        limit: int = 100,
    ) -> list[ConversationRegistry]:
        """List registry entries with optional status filter."""
        table_id = self._table_id("conversation_registry")

        if status:
            query = f"""
            SELECT * FROM `{table_id}`
            WHERE status = @status
            ORDER BY updated_at DESC
            LIMIT {limit}
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("status", "STRING", status.value),
                ]
            )
        else:
            query = f"""
            SELECT * FROM `{table_id}`
            ORDER BY updated_at DESC
            LIMIT {limit}
            """
            job_config = bigquery.QueryJobConfig()

        rows = self.client.query(query, job_config=job_config).result()
        return [ConversationRegistry.from_bq_row(dict(row)) for row in rows]

    def get_pending_for_ingestion(self, limit: int = 50) -> list[ConversationRegistry]:
        """Get conversations ready for CI ingestion."""
        table_id = self._table_id("conversation_registry")
        query = f"""
        SELECT * FROM `{table_id}`
        WHERE status = 'NEW'
          AND has_transcript = TRUE
          AND has_metadata = TRUE
        ORDER BY created_at ASC
        LIMIT {limit}
        """

        rows = self.client.query(query).result()
        return [ConversationRegistry.from_bq_row(dict(row)) for row in rows]

    def get_pending_for_coaching(self, limit: int = 50) -> list[ConversationRegistry]:
        """Get conversations ready for coaching."""
        table_id = self._table_id("conversation_registry")
        query = f"""
        SELECT * FROM `{table_id}`
        WHERE status = 'ENRICHED'
        ORDER BY enriched_at ASC
        LIMIT {limit}
        """

        rows = self.client.query(query).result()
        return [ConversationRegistry.from_bq_row(dict(row)) for row in rows]

    def get_status_counts(self) -> dict[str, int]:
        """Get counts by status for monitoring."""
        table_id = self._table_id("conversation_registry")
        query = f"""
        SELECT status, COUNT(*) as count
        FROM `{table_id}`
        GROUP BY status
        ORDER BY status
        """

        rows = self.client.query(query).result()
        return {row["status"]: row["count"] for row in rows}

    def insert_ci_enrichment(self, enrichment_data: dict) -> None:
        """Insert CI enrichment data (from CI export)."""
        table_id = self._table_id("ci_enrichment")
        errors = self.client.insert_rows_json(table_id, [enrichment_data])
        if errors:
            raise RuntimeError(f"Failed to insert CI enrichment: {errors}")

    def query(self, sql: str) -> list[dict]:
        """Execute arbitrary SQL query and return results."""
        rows = self.client.query(sql).result()
        return [dict(row) for row in rows]
