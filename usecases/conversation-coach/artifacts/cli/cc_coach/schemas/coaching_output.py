"""
Pydantic schema for coaching output data.

This defines the structured output from the Conversation Coach agent.
Simplified for Gemini structured output compatibility.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """Specific quote from transcript as evidence."""

    turn_index: int = Field(description="Turn number where this occurred")
    speaker: str = Field(description="AGENT or CUSTOMER")
    quote: str = Field(description="Exact quote from transcript")
    issue_type: str = Field(description="Issue category like DISMISSIVE_LANGUAGE, THREAT_LEGAL_ACTION, etc.")
    severity: str = Field(description="CRITICAL, HIGH, MEDIUM, or LOW")
    explanation: str = Field(description="Why this is an issue")


class DimensionAssessment(BaseModel):
    """Assessment for one scoring dimension."""

    dimension: str = Field(description="empathy, compliance, resolution, professionalism, de_escalation, or efficiency")
    score: int = Field(ge=1, le=10, description="Score 1-10")
    issue_types: list[str] = Field(default_factory=list, description="List of issue type codes")
    evidence: list[Evidence] = Field(default_factory=list)
    coaching_point: str = Field(description="Specific actionable advice")


class CoachingPoint(BaseModel):
    """Actionable coaching recommendation."""

    priority: int = Field(ge=1, le=5, description="1=highest priority")
    title: str = Field(description="Short title for the coaching point")
    description: str = Field(description="Detailed coaching advice")
    example_turn: Optional[int] = Field(None, description="Reference turn if applicable")
    suggested_alternative: Optional[str] = Field(None, description="Better phrasing to use")


class KeyMoment(BaseModel):
    """Most notable moment in the conversation."""

    turn_index: int
    quote: str = Field(description="Quote from that turn")
    why_notable: str = Field(description="Why this moment matters")
    is_positive: bool = Field(description="True if strength, False if needs work")


class CoachingOutput(BaseModel):
    """Complete coaching output for a conversation."""

    # === OVERALL SCORES (1-10) ===
    empathy_score: int = Field(ge=1, le=10)
    compliance_score: int = Field(ge=1, le=10)
    resolution_score: int = Field(ge=1, le=10)
    professionalism_score: int = Field(ge=1, le=10)
    de_escalation_score: int = Field(ge=1, le=10)
    efficiency_score: int = Field(ge=1, le=10)
    overall_score: float = Field(ge=1.0, le=10.0, description="Weighted average")

    # === DETAILED ASSESSMENTS ===
    assessments: list[DimensionAssessment] = Field(description="Assessments for 3-6 dimensions")

    # === ISSUE SUMMARY ===
    issue_types: list[str] = Field(description="All issue type codes identified")
    critical_issues: list[str] = Field(description="Only CRITICAL severity issues")
    issue_count: int = Field(ge=0)
    compliance_breach_count: int = Field(ge=0)

    # === BINARY FLAGS ===
    resolution_achieved: bool
    escalation_required: bool
    customer_started_negative: bool

    # === COACHING OUTPUT ===
    coaching_summary: str = Field(description="2-3 sentence summary of key coaching needs")
    coaching_points: list[CoachingPoint] = Field(description="1-5 actionable coaching recommendations")
    strengths: list[str] = Field(description="What the agent did well")

    # === CONTEXT ===
    situation_summary: str = Field(description="Brief description of what the call was about")
    behavior_summary: str = Field(description="How the agent handled the situation")
    key_moment: KeyMoment

    # === CALL CLASSIFICATION ===
    call_type: str = Field(description="hardship, complaint, payment, dispute, inquiry, escalation, etc.")

    # === EXAMPLE TYPE (for aggregation) ===
    example_type: Optional[str] = Field(
        None,
        description="GOOD_EXAMPLE, NEEDS_WORK, or null for average performance",
    )

    # === RAG CITATIONS (added post-generation) ===
    citations: list[str] = Field(
        default_factory=list,
        description="Document citations used for coaching feedback (e.g., 'POL-002 v1.1 (Prohibited Language)')",
    )
    rag_context_used: bool = Field(
        default=False,
        description="Whether RAG context was included in generation",
    )
