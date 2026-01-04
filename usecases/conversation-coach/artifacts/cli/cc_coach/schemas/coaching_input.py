"""
Pydantic schema for coaching input data.

This defines the structured input for the Conversation Coach agent.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Turn(BaseModel):
    """Single conversation turn."""

    index: int = Field(description="Turn number (1-indexed)")
    speaker: str = Field(description="AGENT or CUSTOMER")
    text: str = Field(description="What was said")
    sentiment: Optional[float] = Field(None, description="Sentiment score if available")


class CIFlags(BaseModel):
    """Flags from CI phrase matchers."""

    has_compliance_violations: bool = False
    missing_required_disclosures: bool = False
    no_empathy_shown: bool = False
    customer_escalated: bool = False


class PhraseMatch(BaseModel):
    """Individual phrase match from CI."""

    matcher_name: str = Field(description="Name of phrase matcher")
    phrase: str = Field(description="Matched phrase")
    turn_index: int = Field(description="Which turn")
    speaker: str = Field(description="Who said it")


class CallMetadata(BaseModel):
    """Call context from registry."""

    agent_id: str
    business_line: str = Field(default="COLLECTIONS", description="COLLECTIONS or LOANS")
    direction: str = Field(default="OUTBOUND", description="INBOUND or OUTBOUND")
    queue: Optional[str] = None
    call_outcome: Optional[str] = None
    duration_seconds: Optional[int] = None


class CoachingInput(BaseModel):
    """Complete input for conversation coach."""

    conversation_id: str

    # Transcript
    turns: list[Turn]
    turn_count: int

    # Metadata
    metadata: CallMetadata

    # CI Enrichment
    customer_sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    customer_sentiment_start: Optional[float] = None
    customer_sentiment_end: Optional[float] = None

    # CI Flags (from phrase matchers)
    ci_flags: CIFlags = Field(default_factory=CIFlags)
    phrase_matches: list[PhraseMatch] = Field(default_factory=list)

    # CI Summary (if available)
    ci_summary: Optional[str] = None

    def to_prompt_text(self) -> str:
        """Format input as text for the LLM prompt."""
        lines = []

        # Metadata section
        lines.append("## CALL METADATA")
        lines.append(f"Conversation ID: {self.conversation_id}")
        lines.append(f"Agent ID: {self.metadata.agent_id}")
        lines.append(f"Business Line: {self.metadata.business_line}")
        lines.append(f"Direction: {self.metadata.direction}")
        if self.metadata.queue:
            lines.append(f"Queue: {self.metadata.queue}")
        if self.metadata.duration_seconds:
            lines.append(f"Duration: {self.metadata.duration_seconds}s")

        # CI signals
        if self.customer_sentiment_score is not None:
            lines.append(f"\nCustomer Sentiment: {self.customer_sentiment_score:.2f}")

        # CI flags
        if any([
            self.ci_flags.has_compliance_violations,
            self.ci_flags.missing_required_disclosures,
            self.ci_flags.no_empathy_shown,
            self.ci_flags.customer_escalated,
        ]):
            lines.append("\n## CI PHRASE MATCHER FLAGS")
            if self.ci_flags.has_compliance_violations:
                lines.append("- HAS_COMPLIANCE_VIOLATIONS: Check for threats/harassment")
            if self.ci_flags.missing_required_disclosures:
                lines.append("- MISSING_REQUIRED_DISCLOSURES: Verify disclosures made")
            if self.ci_flags.no_empathy_shown:
                lines.append("- NO_EMPATHY_SHOWN: Look for empathy statements")
            if self.ci_flags.customer_escalated:
                lines.append("- CUSTOMER_ESCALATED: Assess de-escalation attempts")

        # Phrase matches
        if self.phrase_matches:
            lines.append("\n## DETECTED PHRASES")
            for pm in self.phrase_matches:
                lines.append(f"- Turn {pm.turn_index} [{pm.speaker}]: \"{pm.phrase}\" ({pm.matcher_name})")

        # CI summary
        if self.ci_summary:
            lines.append(f"\n## CI SUMMARY\n{self.ci_summary}")

        # Transcript
        lines.append("\n## TRANSCRIPT")
        for turn in self.turns:
            lines.append(f"Turn {turn.index} [{turn.speaker}]: {turn.text}")

        return "\n".join(lines)
