"""
Pydantic schemas for daily and weekly summaries.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class ExampleConversation(BaseModel):
    """Rich example conversation reference."""

    conversation_id: str
    example_type: str = Field(description="GOOD_EXAMPLE or NEEDS_WORK")
    headline: str = Field(description="Short description of the call")
    key_moment: Optional[dict] = Field(
        default=None, description="turn_index, quote, why_notable"
    )
    outcome: Optional[str] = None
    sentiment_journey: Optional[str] = None
    scores: Optional[dict] = None
    call_type: Optional[str] = None
    call_date: Optional[date] = None  # renamed to avoid shadowing 'date' type


class DailySummaryInput(BaseModel):
    """Input for daily summary LLM generation."""

    agent_id: str
    date: date
    business_line: Optional[str] = None
    team: Optional[str] = None

    # Metrics
    call_count: int
    avg_empathy: float
    avg_compliance: float
    avg_resolution: float
    avg_professionalism: float
    avg_efficiency: float
    avg_de_escalation: float
    avg_overall: float
    resolution_rate: float

    # Trend vs previous day
    prev_day_avg_overall: Optional[float] = None
    prev_day_call_count: Optional[int] = None
    overall_delta: Optional[float] = None
    trend_direction: Optional[str] = None  # improving, declining, stable

    # Issues and strengths
    top_issues: list[str] = Field(default_factory=list)
    top_strengths: list[str] = Field(default_factory=list)

    # Example conversations
    best_conversation: Optional[ExampleConversation] = None
    worst_conversation: Optional[ExampleConversation] = None


class DailySummaryOutput(BaseModel):
    """LLM-generated daily summary output."""

    daily_narrative: str = Field(description="2-3 sentence evidence-based summary")
    focus_area: str = Field(description="Single dimension to focus on")
    coaching_advice: Optional[str] = Field(
        None, description="Specific actionable advice"
    )
    quick_wins: list[str] = Field(default_factory=list, description="Easy improvements")


class DailySummary(BaseModel):
    """Complete daily summary record for storage."""

    # Keys
    agent_id: str
    date: date
    generated_at: datetime

    # Metadata
    business_line: Optional[str] = None
    team: Optional[str] = None

    # Metrics
    call_count: int
    avg_empathy: float
    avg_compliance: float
    avg_resolution: float
    avg_professionalism: float
    avg_efficiency: float
    avg_de_escalation: float
    resolution_rate: float

    # Issue distribution
    top_issues: list[str] = Field(default_factory=list)
    top_strengths: list[str] = Field(default_factory=list)

    # Example conversations
    example_conversations: list[ExampleConversation] = Field(default_factory=list)

    # Trend
    empathy_delta: Optional[float] = None
    compliance_delta: Optional[float] = None

    # LLM Generated
    daily_narrative: str
    focus_area: str
    quick_wins: list[str] = Field(default_factory=list)


class WeeklySummaryInput(BaseModel):
    """Input for weekly summary LLM generation."""

    agent_id: str
    week_start: date
    week_end: date
    business_line: Optional[str] = None
    team: Optional[str] = None

    # Week metrics
    total_calls: int
    days_with_calls: int

    # Scores
    week_avg_empathy: float
    week_avg_compliance: float
    week_avg_resolution: float
    week_avg_professionalism: float
    week_avg_efficiency: float
    week_avg_de_escalation: float
    week_avg_overall: float
    week_resolution_rate: float

    # Trends vs previous week
    prev_week_avg_overall: Optional[float] = None
    prev_week_total_calls: Optional[int] = None
    empathy_delta: Optional[float] = None
    compliance_delta: Optional[float] = None
    resolution_delta: Optional[float] = None
    overall_delta: Optional[float] = None

    # Daily breakdown
    daily_scores: list[dict] = Field(default_factory=list)

    # Patterns
    top_issues: list[str] = Field(default_factory=list)
    top_strengths: list[str] = Field(default_factory=list)

    # Example conversations
    exemplary_conversations: list[ExampleConversation] = Field(default_factory=list)
    needs_review_conversations: list[ExampleConversation] = Field(default_factory=list)


class WeeklySummaryOutput(BaseModel):
    """LLM-generated weekly summary output."""

    weekly_summary: str = Field(description="3-5 sentence evidence-based summary")
    trend_analysis: str = Field(description="What's improving/declining")
    action_plan: str = Field(description="2-3 specific actions for next week")
    recommended_training: list[str] = Field(
        default_factory=list, description="Suggested training modules"
    )


class WeeklySummary(BaseModel):
    """Complete weekly summary record for storage."""

    # Keys
    agent_id: str
    week_start: date
    generated_at: datetime

    # Metadata
    business_line: Optional[str] = None
    team: Optional[str] = None

    # Scores
    empathy_score: float
    compliance_score: float
    resolution_score: float
    professionalism_score: float
    efficiency_score: float
    de_escalation_score: float

    # Trends
    empathy_delta: Optional[float] = None
    compliance_delta: Optional[float] = None
    resolution_delta: Optional[float] = None

    # Metrics
    total_calls: int
    resolution_rate: float
    compliance_breach_count: int = 0

    # Patterns
    top_issues: list[str] = Field(default_factory=list)
    top_strengths: list[str] = Field(default_factory=list)
    recommended_training: list[str] = Field(default_factory=list)

    # LLM Generated
    weekly_summary: str
    trend_analysis: str
    action_plan: str

    # Example conversations
    example_conversations: list[ExampleConversation] = Field(default_factory=list)

    # Daily breakdown
    daily_scores: list[dict] = Field(default_factory=list)
