"""Pytest fixtures for Conversation Coach CLI tests."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from cc_coach.config import Settings
from cc_coach.models.conversation import (
    BusinessLine,
    CallOutcome,
    Channel,
    Conversation,
    ConversationMetadata,
    ConversationTurn,
    Direction,
    Queue,
    Speaker,
    Transcription,
)
from cc_coach.models.registry import ConversationRegistry, RegistryStatus


@pytest.fixture
def mock_settings():
    """Provide test settings."""
    return Settings(
        project_id="test-project",
        region="us-central1",
        gcs_bucket_dev="test-bucket",
        bq_dataset="test_dataset",
        bq_location="US",
        insights_location="us-central1",
    )


@pytest.fixture
def sample_transcription():
    """Provide a sample transcription."""
    return Transcription(
        conversation_id="test-uuid-1234-5678-abcd-efgh12345678",
        channel=Channel.VOICE,
        language="en-AU",
        started_at=datetime(2025, 12, 28, 10, 0, 0),
        ended_at=datetime(2025, 12, 28, 10, 5, 30),
        duration_sec=330,
        turns=[
            ConversationTurn(turn_index=0, speaker=Speaker.AGENT, text="Hello, how can I help?", ts_offset_sec=0),
            ConversationTurn(turn_index=1, speaker=Speaker.CUSTOMER, text="I have an issue with my account.", ts_offset_sec=3),
            ConversationTurn(turn_index=2, speaker=Speaker.AGENT, text="I can help with that. Let me check.", ts_offset_sec=8),
        ],
    )


@pytest.fixture
def sample_metadata():
    """Provide sample metadata."""
    return ConversationMetadata(
        conversation_id="test-uuid-1234-5678-abcd-efgh12345678",
        direction=Direction.INBOUND,
        business_line=BusinessLine.COLLECTIONS,
        queue=Queue.STANDARD,
        agent_id="A1234",
        agent_name="Test Agent",
        team="TEAM_1",
        site="SYD",
        call_outcome=CallOutcome.RESOLVED_WITH_ACTION,
    )


@pytest.fixture
def sample_conversation(sample_transcription, sample_metadata):
    """Provide a sample conversation."""
    return Conversation(
        transcription=sample_transcription,
        metadata=sample_metadata,
    )


@pytest.fixture
def sample_registry():
    """Provide a sample registry entry."""
    return ConversationRegistry(
        conversation_id="test-uuid-1234-5678-abcd-efgh12345678",
        transcript_uri_raw="gs://test-bucket/2025-12-28/test-uuid/transcription.json",
        metadata_uri_raw="gs://test-bucket/2025-12-28/test-uuid/metadata.json",
        has_transcript=True,
        has_metadata=True,
        status=RegistryStatus.NEW,
        created_at=datetime(2025, 12, 28, 10, 0, 0),
        updated_at=datetime(2025, 12, 28, 10, 0, 0),
    )


@pytest.fixture
def mock_bigquery_client():
    """Mock BigQuery client."""
    with patch("cc_coach.services.bigquery.bigquery.Client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_insights_client():
    """Mock CCAI Insights client."""
    with patch("cc_coach.services.insights.insights.ContactCenterInsightsClient") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_storage_client():
    """Mock GCS client."""
    with patch("cc_coach.services.gcs.storage.Client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client
