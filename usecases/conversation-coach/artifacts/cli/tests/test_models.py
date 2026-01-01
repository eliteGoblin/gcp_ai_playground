"""Tests for data models."""

from datetime import datetime

import pytest

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


class TestTranscription:
    """Tests for Transcription model."""

    def test_valid_transcription(self, sample_transcription):
        """Test creating a valid transcription."""
        assert sample_transcription.conversation_id == "test-uuid-1234-5678-abcd-efgh12345678"
        assert sample_transcription.channel == Channel.VOICE
        assert len(sample_transcription.turns) == 3
        assert sample_transcription.duration_sec == 330

    def test_transcription_minimum_fields(self):
        """Test transcription with minimum required fields."""
        trans = Transcription(
            conversation_id="min-uuid-test",
            channel=Channel.VOICE,
            language="en-AU",
            started_at=datetime(2025, 1, 1, 10, 0, 0),
            ended_at=datetime(2025, 1, 1, 10, 5, 0),
            turns=[
                ConversationTurn(turn_index=0, speaker=Speaker.AGENT, text="Hello", ts_offset_sec=0),
            ],
        )
        assert trans.conversation_id == "min-uuid-test"
        assert len(trans.turns) == 1

    def test_invalid_empty_turns(self):
        """Test that empty turns list is rejected."""
        with pytest.raises(ValueError):
            Transcription(
                conversation_id="test",
                channel=Channel.VOICE,
                language="en-AU",
                started_at=datetime(2025, 1, 1),
                ended_at=datetime(2025, 1, 1),
                turns=[],  # Invalid - must have at least 1 turn
            )


class TestConversationMetadata:
    """Tests for ConversationMetadata model."""

    def test_valid_metadata(self, sample_metadata):
        """Test creating valid metadata."""
        assert sample_metadata.direction == Direction.INBOUND
        assert sample_metadata.business_line == BusinessLine.COLLECTIONS
        assert sample_metadata.queue == Queue.STANDARD
        assert sample_metadata.agent_id == "A1234"

    def test_metadata_optional_fields(self):
        """Test metadata with optional fields."""
        meta = ConversationMetadata(
            conversation_id="test-uuid",
            direction=Direction.OUTBOUND,
            business_line=BusinessLine.LOANS,
            queue=Queue.SUPPORT,
            agent_id="L5512",
        )
        assert meta.agent_name is None
        assert meta.portfolio_id is None
        assert meta.campaign_id is None


class TestConversation:
    """Tests for complete Conversation model."""

    def test_conversation_creation(self, sample_conversation):
        """Test creating a complete conversation."""
        assert sample_conversation.conversation_id == "test-uuid-1234-5678-abcd-efgh12345678"
        assert sample_conversation.transcription.channel == Channel.VOICE
        assert sample_conversation.metadata.direction == Direction.INBOUND

    def test_to_ccai_entries(self, sample_conversation):
        """Test converting to CCAI entries format."""
        entries = sample_conversation.to_ccai_entries()

        assert len(entries) == 3

        # Check first entry (agent)
        assert entries[0]["role"] == "HUMAN_AGENT"
        assert entries[0]["user_id"] == 2
        assert entries[0]["text"] == "Hello, how can I help?"
        assert entries[0]["start_timestamp_usec"] > 0

        # Check second entry (customer)
        assert entries[1]["role"] == "END_USER"
        assert entries[1]["user_id"] == 1

    def test_to_ccai_labels(self, sample_conversation):
        """Test converting metadata to CCAI labels."""
        labels = sample_conversation.to_ccai_labels()

        assert labels["direction"] == "INBOUND"
        assert labels["business_line"] == "COLLECTIONS"
        assert labels["queue"] == "STANDARD"
        assert labels["agent_id"] == "A1234"
        assert labels["team"] == "TEAM_1"
        assert labels["site"] == "SYD"


class TestConversationRegistry:
    """Tests for ConversationRegistry model."""

    def test_registry_creation(self, sample_registry):
        """Test creating a registry entry."""
        assert sample_registry.conversation_id == "test-uuid-1234-5678-abcd-efgh12345678"
        assert sample_registry.status == RegistryStatus.NEW
        assert sample_registry.has_transcript is True
        assert sample_registry.has_metadata is True

    def test_registry_to_bq_row(self, sample_registry):
        """Test converting registry to BigQuery row."""
        row = sample_registry.to_bq_row()

        assert row["conversation_id"] == "test-uuid-1234-5678-abcd-efgh12345678"
        assert row["status"] == "NEW"
        assert row["has_transcript"] is True
        assert isinstance(row["created_at"], str)

    def test_registry_from_bq_row(self):
        """Test creating registry from BigQuery row."""
        row = {
            "conversation_id": "test-uuid",
            "status": "ENRICHED",
            "has_transcript": True,
            "has_metadata": True,
            "has_audio": False,
            "transcript_uri_raw": "gs://bucket/path",
            "created_at": datetime(2025, 1, 1),
            "updated_at": datetime(2025, 1, 1),
        }

        registry = ConversationRegistry.from_bq_row(row)

        assert registry.conversation_id == "test-uuid"
        assert registry.status == RegistryStatus.ENRICHED
        assert registry.has_transcript is True

    def test_registry_status_transitions(self):
        """Test that all status values are valid."""
        for status in RegistryStatus:
            registry = ConversationRegistry(
                conversation_id="test",
                status=status,
            )
            assert registry.status == status
