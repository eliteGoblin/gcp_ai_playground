"""
Conversation data models.

These models represent the input data format (from GCS) and are used
for validation and transformation before sending to CCAI Insights.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Channel(str, Enum):
    """Communication channel."""

    VOICE = "VOICE"
    CHAT = "CHAT"
    EMAIL = "EMAIL"


class Speaker(str, Enum):
    """Speaker role in conversation."""

    AGENT = "AGENT"
    CUSTOMER = "CUSTOMER"
    SYSTEM = "SYSTEM"
    IVR = "IVR"


class Direction(str, Enum):
    """Call direction."""

    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class BusinessLine(str, Enum):
    """Business line."""

    COLLECTIONS = "COLLECTIONS"
    LOANS = "LOANS"


class Queue(str, Enum):
    """Queue or skill group."""

    STANDARD = "STANDARD"
    HARDSHIP = "HARDSHIP"
    DISPUTE = "DISPUTE"
    SUPPORT = "SUPPORT"
    ESCALATION = "ESCALATION"


class CallOutcome(str, Enum):
    """Call outcome."""

    PAYMENT_PLAN_AGREED = "PAYMENT_PLAN_AGREED"
    PAYMENT_MADE = "PAYMENT_MADE"
    CALLBACK_SCHEDULED = "CALLBACK_SCHEDULED"
    TRANSFERRED = "TRANSFERRED"
    WRONG_PARTY = "WRONG_PARTY"
    NO_ANSWER = "NO_ANSWER"
    VOICEMAIL = "VOICEMAIL"
    RESOLVED_WITH_ACTION = "RESOLVED_WITH_ACTION"
    UNRESOLVED = "UNRESOLVED"
    COMPLAINT_LODGED = "COMPLAINT_LODGED"
    DISPUTE_RAISED = "DISPUTE_RAISED"


class ConversationTurn(BaseModel):
    """A single turn in the conversation."""

    turn_index: int = Field(ge=0, description="Zero-based turn index")
    speaker: Speaker = Field(description="Who spoke this turn")
    text: str = Field(min_length=1, description="Transcribed text")
    ts_offset_sec: float = Field(ge=0, description="Offset from start in seconds")


class Transcription(BaseModel):
    """Transcription data from transcription.json."""

    conversation_id: str = Field(description="UUID of the conversation")
    channel: Channel = Field(description="Communication channel")
    language: str = Field(default="en-AU", description="Language code")
    started_at: datetime = Field(description="Conversation start time")
    ended_at: datetime = Field(description="Conversation end time")
    duration_sec: Optional[int] = Field(default=None, description="Duration in seconds")
    turns: list[ConversationTurn] = Field(min_length=1, description="Conversation turns")

    @field_validator("duration_sec", mode="before")
    @classmethod
    def compute_duration(cls, v: Optional[int], info) -> int:
        """Compute duration from timestamps if not provided."""
        if v is not None:
            return v
        data = info.data
        if "started_at" in data and "ended_at" in data:
            delta = data["ended_at"] - data["started_at"]
            return int(delta.total_seconds())
        return 0


class ConversationLabels(BaseModel):
    """Labels for testing and filtering."""

    model_config = ConfigDict(extra="allow")

    priority: Optional[str] = None
    test_case: Optional[str] = None
    expected_risk_flags: Optional[list[str]] = None
    expected_next_actions: Optional[list[str]] = None
    expected_compliance_checks: Optional[dict[str, Any]] = None


class ConversationMetadata(BaseModel):
    """Metadata from metadata.json."""

    conversation_id: str = Field(description="UUID matching transcription")
    direction: Direction = Field(description="Call direction")
    business_line: BusinessLine = Field(description="Business line")
    queue: Queue = Field(description="Queue or skill group")
    agent_id: str = Field(min_length=1, description="Agent identifier")
    agent_name: Optional[str] = Field(default=None, description="Agent display name")
    team: Optional[str] = Field(default=None, description="Team identifier")
    site: Optional[str] = Field(default=None, description="Site/location code")
    portfolio_id: Optional[str] = Field(default=None, description="Portfolio ID")
    campaign_id: Optional[str] = Field(default=None, description="Campaign ID")
    call_outcome: Optional[CallOutcome] = Field(default=None, description="Call outcome")
    started_at: Optional[datetime] = Field(default=None, description="Start time")
    ended_at: Optional[datetime] = Field(default=None, description="End time")
    duration_sec: Optional[int] = Field(default=None, description="Duration in seconds")
    labels: Optional[ConversationLabels] = Field(default=None, description="Test labels")


class Conversation(BaseModel):
    """Complete conversation with transcription and metadata."""

    transcription: Transcription
    metadata: ConversationMetadata

    @property
    def conversation_id(self) -> str:
        """Get conversation ID."""
        return self.transcription.conversation_id

    def to_ccai_entries(self) -> list[dict]:
        """
        Convert to CCAI Insights conversation entries format.

        CCAI expects:
        {
            "entries": [
                {
                    "start_timestamp_usec": int,
                    "text": str,
                    "role": "AGENT" | "HUMAN_AGENT" | "AUTOMATED_AGENT" | "END_USER",
                    "user_id": int
                }
            ]
        }
        """
        base_ts = self.transcription.started_at.timestamp()
        entries = []

        for turn in self.transcription.turns:
            # Map speaker to CCAI role
            if turn.speaker == Speaker.AGENT:
                role = "HUMAN_AGENT"
                user_id = 2
            elif turn.speaker == Speaker.CUSTOMER:
                role = "END_USER"
                user_id = 1
            else:
                role = "AUTOMATED_AGENT"
                user_id = 3

            ts_usec = int((base_ts + turn.ts_offset_sec) * 1_000_000)

            entries.append({
                "start_timestamp_usec": ts_usec,
                "text": turn.text,
                "role": role,
                "user_id": user_id,
            })

        return entries

    def to_ccai_labels(self) -> dict[str, str]:
        """Convert metadata to CCAI labels (string key-value pairs)."""
        labels = {
            "direction": self.metadata.direction.value,
            "business_line": self.metadata.business_line.value,
            "queue": self.metadata.queue.value,
            "agent_id": self.metadata.agent_id,
        }

        if self.metadata.team:
            labels["team"] = self.metadata.team
        if self.metadata.site:
            labels["site"] = self.metadata.site
        if self.metadata.portfolio_id:
            labels["portfolio_id"] = self.metadata.portfolio_id
        if self.metadata.campaign_id:
            labels["campaign_id"] = self.metadata.campaign_id
        if self.metadata.call_outcome:
            labels["call_outcome"] = self.metadata.call_outcome.value

        return labels

    def to_transcript_text(self) -> str:
        """
        Convert conversation turns to readable transcript text.

        Format: "SPEAKER: text" for each turn, joined by newlines.
        """
        lines = []
        for turn in self.transcription.turns:
            lines.append(f"{turn.speaker}: {turn.text}")
        return "\n".join(lines)
