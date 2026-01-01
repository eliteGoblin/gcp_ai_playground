"""
Conversation Registry model for BigQuery.

The registry tracks the state of each conversation through the pipeline:
GCS → CCAI Insights → BigQuery → CoachAgent
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class RegistryStatus(str, Enum):
    """Pipeline status for a conversation."""

    NEW = "NEW"  # Received in GCS, not yet processed
    SANITIZED = "SANITIZED"  # PII redacted (future)
    INGESTED = "INGESTED"  # Submitted to CCAI Insights
    ENRICHED = "ENRICHED"  # CI analysis complete, exported to BQ
    COACHED = "COACHED"  # Coaching card generated
    FAILED = "FAILED"  # Processing failed


class ConversationRegistry(BaseModel):
    """
    Registry entry for tracking conversation pipeline state.

    This table enables:
    - Idempotent processing (check status before reprocessing)
    - Pairing of transcript + metadata
    - Audit trail of processing stages
    - Retry tracking for failed items
    """

    conversation_id: str = Field(description="Primary key - conversation UUID")

    # GCS URIs
    transcript_uri_raw: Optional[str] = Field(
        default=None, description="GCS URI for raw transcript"
    )
    metadata_uri_raw: Optional[str] = Field(
        default=None, description="GCS URI for raw metadata"
    )
    audio_uri_raw: Optional[str] = Field(
        default=None, description="GCS URI for raw audio (future)"
    )

    # Sanitized URIs (future - after DLP)
    transcript_uri_sanitized: Optional[str] = Field(default=None)
    metadata_uri_sanitized: Optional[str] = Field(default=None)
    audio_uri_sanitized: Optional[str] = Field(default=None)

    # Presence flags
    has_transcript: bool = Field(default=False)
    has_metadata: bool = Field(default=False)
    has_audio: bool = Field(default=False)

    # Pipeline state
    status: RegistryStatus = Field(default=RegistryStatus.NEW)

    # DLP tracking (future)
    redaction_version: Optional[str] = Field(default=None)
    pii_types_found: Optional[list[str]] = Field(default=None)

    # CCAI Insights reference
    ci_conversation_name: Optional[str] = Field(
        default=None, description="CCAI Insights conversation resource name"
    )
    ci_analysis_id: Optional[str] = Field(
        default=None, description="CCAI Insights analysis ID"
    )

    # Error handling
    last_error: Optional[str] = Field(default=None)
    retry_count: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    ingested_at: Optional[datetime] = Field(default=None)
    enriched_at: Optional[datetime] = Field(default=None)
    coached_at: Optional[datetime] = Field(default=None)

    def to_bq_row(self) -> dict:
        """Convert to BigQuery row format."""
        row = self.model_dump()

        # Convert enums to strings
        row["status"] = self.status.value

        # Convert datetime to ISO format strings for BQ
        for field in ["created_at", "updated_at", "ingested_at", "enriched_at", "coached_at"]:
            if row[field] is not None:
                row[field] = row[field].isoformat()

        return row

    @classmethod
    def from_bq_row(cls, row: dict) -> "ConversationRegistry":
        """Create from BigQuery row."""
        # Handle status enum
        if isinstance(row.get("status"), str):
            row["status"] = RegistryStatus(row["status"])

        return cls(**row)
