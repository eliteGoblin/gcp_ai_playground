# Phase 1: ADK Conversation Coach - Low-Level Design

> Implementation-ready design for per-conversation coaching using Google ADK + Gemini.
> MVP approach: Manual CLI invocation, no automated triggers.

---

## 1. Executive Summary

### What We're Building
A conversation coaching agent that:
1. Takes transcript + CI enrichment + metadata as input
2. Uses Gemini to analyze agent behavior
3. Outputs structured coaching (scores, evidence, recommendations)
4. Stores results in BigQuery `coach_analysis` table

### MVP Scope (Phase 1)
- **Manual trigger**: CLI command `cc-coach coach generate <conversation-id>`
- **No automation**: No Cloud Scheduler, no event triggers
- **No RAG yet**: Policy knowledge embedded in prompt (RAG added later)
- **Single agent**: Simple architecture, no multi-agent orchestration

---

## 2. ADK Fundamentals

### 2.1 What is ADK?

**ADK (Agent Development Kit)** is Google's open-source framework for building AI agents. Released at Google Cloud NEXT 2025, it provides:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ADK ARCHITECTURE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         YOUR CODE                                    │    │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │    │
│  │  │   Agents      │  │    Tools      │  │   Prompts     │           │    │
│  │  │  (Python)     │  │  (Functions)  │  │  (Templates)  │           │    │
│  │  └───────────────┘  └───────────────┘  └───────────────┘           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         ADK FRAMEWORK                                │    │
│  │                                                                       │    │
│  │  • Agent orchestration          • Session management                 │    │
│  │  • Tool execution               • Input/Output schemas (Pydantic)   │    │
│  │  • Model abstraction            • Streaming support                  │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         LLM BACKEND                                  │    │
│  │                                                                       │    │
│  │  Gemini (native) │ GPT-4 │ Claude │ Mistral (via LiteLLM)           │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      DEPLOYMENT OPTIONS                              │    │
│  │                                                                       │    │
│  │  Local │ Cloud Run │ GKE │ Vertex AI Agent Engine (managed)         │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Key ADK Concepts

| Concept | Description | Our Usage |
|---------|-------------|-----------|
| **Agent** | LLM-powered unit with instructions + tools | ConversationCoach agent |
| **Tool** | Function the agent can call | None for MVP (stateless analysis) |
| **Session** | Conversation state across turns | Single-turn (no session needed) |
| **Runner** | Executes agent with input | CLI runner |
| **Input Schema** | Pydantic model for input validation | `CoachingInput` |
| **Output Schema** | Pydantic model for structured output | `CoachingOutput` |

### 2.3 Why ADK for This Use Case?

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| **Raw Gemini API** | Simpler, fewer deps | No schema validation, manual JSON parsing | Not chosen |
| **LangChain** | Popular, many integrations | Overkill, Google prefers ADK | Not chosen |
| **ADK** | Native Gemini support, Pydantic schemas, path to Agent Engine | Newer framework | **Chosen** |

### 2.4 Model Selection

| Model | Speed | Quality | Cost | Structured Output | Recommendation |
|-------|-------|---------|------|-------------------|----------------|
| `gemini-2.0-flash` | Fast | Good | Low | Yes | Dev/testing |
| `gemini-2.5-flash` | Fast | Very Good | Medium | Yes | **Production** |
| `gemini-2.5-pro` | Slower | Excellent | High | Yes | Complex cases |

**Our choice**: `gemini-2.5-flash` for production quality with reasonable cost.

For dev with small dataset where quality matters: Use `gemini-2.5-flash` (not the cheaper lite version).

---

## 3. Architecture

### 3.1 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PHASE 1: PER-CONVERSATION COACH                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐                                                         │
│  │ CLI Command     │                                                         │
│  │ cc-coach coach  │                                                         │
│  │ generate <id>   │                                                         │
│  └────────┬────────┘                                                         │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 1. FETCH DATA (BigQuery)                                             │    │
│  │                                                                       │    │
│  │    ┌─────────────────┐    ┌─────────────────┐                        │    │
│  │    │ ci_enrichment   │    │ conversation_   │                        │    │
│  │    │ ─────────────── │    │ registry        │                        │    │
│  │    │ • transcript    │    │ ─────────────── │                        │    │
│  │    │ • sentiment     │    │ • agent_id      │                        │    │
│  │    │ • phrase_matches│    │ • metadata      │                        │    │
│  │    │ • ci_flags      │    │                 │                        │    │
│  │    └────────┬────────┘    └────────┬────────┘                        │    │
│  │             │                      │                                  │    │
│  │             └──────────┬───────────┘                                  │    │
│  │                        │                                              │    │
│  └────────────────────────┼──────────────────────────────────────────────┘    │
│                           │                                                  │
│                           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 2. BUILD PROMPT                                                       │    │
│  │                                                                       │    │
│  │    ┌─────────────────────────────────────────────────────────────┐   │    │
│  │    │ System Prompt (instruction)                                  │   │    │
│  │    │ ─────────────────────────────                                │   │    │
│  │    │ • Scoring rubric (empathy, compliance, resolution...)       │   │    │
│  │    │ • Issue taxonomy                                             │   │    │
│  │    │ • Evidence requirements                                      │   │    │
│  │    │ • Output format                                              │   │    │
│  │    │                                                              │   │    │
│  │    │ + Embedded Policy Knowledge (Phase 1)                        │   │    │
│  │    │   └── Key compliance rules, disclosure requirements         │   │    │
│  │    │       (Will move to RAG in Phase 1.5)                        │   │    │
│  │    └─────────────────────────────────────────────────────────────┘   │    │
│  │                                                                       │    │
│  │    ┌─────────────────────────────────────────────────────────────┐   │    │
│  │    │ User Prompt (CoachingInput)                                  │   │    │
│  │    │ ─────────────────────────────                                │   │    │
│  │    │ • transcript (full)                                          │   │    │
│  │    │ • metadata (agent_id, call_type, outcome)                   │   │    │
│  │    │ • ci_signals (sentiment, phrase_matches, flags)             │   │    │
│  │    └─────────────────────────────────────────────────────────────┘   │    │
│  │                                                                       │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                           │                                                  │
│                           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 3. INVOKE ADK AGENT                                                   │    │
│  │                                                                       │    │
│  │    ┌─────────────────────────────────────────────────────────────┐   │    │
│  │    │ ConversationCoach Agent                                      │   │    │
│  │    │ ───────────────────────────                                  │   │    │
│  │    │ model: gemini-2.5-flash                                      │   │    │
│  │    │ input_schema: CoachingInput                                  │   │    │
│  │    │ output_schema: CoachingOutput                                │   │    │
│  │    │ tools: [] (none for MVP)                                     │   │    │
│  │    └─────────────────────────────────────────────────────────────┘   │    │
│  │                                                                       │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                           │                                                  │
│                           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 4. VALIDATE & STORE                                                   │    │
│  │                                                                       │    │
│  │    CoachingOutput (Pydantic validated)                               │    │
│  │           │                                                           │    │
│  │           ▼                                                           │    │
│  │    ┌─────────────────┐                                               │    │
│  │    │ coach_analysis  │                                               │    │
│  │    │ (BigQuery)      │                                               │    │
│  │    └─────────────────┘                                               │    │
│  │                                                                       │    │
│  │    + Update conversation_registry.status = 'COACHED'                 │    │
│  │                                                                       │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Diagram

```
cc_coach/
├── agents/
│   ├── __init__.py
│   └── conversation_coach.py    # ADK Agent definition
├── prompts/
│   ├── __init__.py
│   └── coach_system_prompt.py   # System prompt + rubric
├── schemas/
│   ├── coaching_input.py        # Pydantic input schema
│   └── coaching_output.py       # Pydantic output schema
├── services/
│   ├── gemini.py                # Vertex AI / Gemini client
│   └── coaching.py              # Orchestration logic
└── commands/
    └── coach.py                 # CLI commands (Typer)
```

---

## 4. Data Schemas

### 4.1 Input Schema: CoachingInput

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

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
    business_line: str = Field(description="COLLECTIONS or LOANS")
    direction: str = Field(description="INBOUND or OUTBOUND")
    queue: Optional[str] = None
    call_outcome: Optional[str] = None
    duration_seconds: Optional[int] = None

class CoachingInput(BaseModel):
    """Complete input for conversation coach."""
    conversation_id: str

    # Transcript
    turns: List[Turn]
    turn_count: int

    # Metadata
    metadata: CallMetadata

    # CI Enrichment
    customer_sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    customer_sentiment_start: Optional[float] = None
    customer_sentiment_end: Optional[float] = None

    # CI Flags (from phrase matchers)
    ci_flags: CIFlags = Field(default_factory=CIFlags)
    phrase_matches: List[PhraseMatch] = Field(default_factory=list)

    # CI Summary (if available)
    ci_summary: Optional[str] = None
```

### 4.2 Output Schema: CoachingOutput

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class Severity(str, Enum):
    CRITICAL = "CRITICAL"  # Compliance violation, must address
    HIGH = "HIGH"          # Significant issue
    MEDIUM = "MEDIUM"      # Notable concern
    LOW = "LOW"            # Minor improvement area

class IssueType(str, Enum):
    """Categorical issue types for aggregation."""
    # Empathy issues
    DISMISSIVE_LANGUAGE = "DISMISSIVE_LANGUAGE"
    NO_ACKNOWLEDGMENT = "NO_ACKNOWLEDGMENT"
    RUSHING_CUSTOMER = "RUSHING_CUSTOMER"
    BLAME_SHIFTING = "BLAME_SHIFTING"
    LACK_OF_PATIENCE = "LACK_OF_PATIENCE"

    # Compliance issues
    THREAT_LEGAL_ACTION = "THREAT_LEGAL_ACTION"
    THREAT_GARNISHMENT = "THREAT_GARNISHMENT"
    HARASSMENT = "HARASSMENT"
    MISSING_DISCLOSURE = "MISSING_DISCLOSURE"
    MISSING_HARDSHIP_OFFER = "MISSING_HARDSHIP_OFFER"
    PRIVACY_VIOLATION = "PRIVACY_VIOLATION"

    # Resolution issues
    NO_PAYMENT_OPTIONS = "NO_PAYMENT_OPTIONS"
    UNREALISTIC_DEMANDS = "UNREALISTIC_DEMANDS"
    FAILED_DE_ESCALATION = "FAILED_DE_ESCALATION"
    UNRESOLVED_WITHOUT_ACTION = "UNRESOLVED_WITHOUT_ACTION"

    # Positive (for tracking strengths)
    EXCELLENT_EMPATHY = "EXCELLENT_EMPATHY"
    PERFECT_COMPLIANCE = "PERFECT_COMPLIANCE"
    EFFECTIVE_RESOLUTION = "EFFECTIVE_RESOLUTION"

class Evidence(BaseModel):
    """Specific quote from transcript as evidence."""
    turn_index: int = Field(description="Turn number where this occurred")
    speaker: str = Field(description="AGENT or CUSTOMER")
    quote: str = Field(description="Exact quote (max 150 chars)", max_length=200)
    issue_type: IssueType
    severity: Severity
    explanation: str = Field(description="Why this is an issue", max_length=300)

class DimensionAssessment(BaseModel):
    """Assessment for one scoring dimension."""
    dimension: str = Field(description="empathy, compliance, resolution, etc.")
    score: int = Field(ge=1, le=10, description="Score 1-10")
    issue_types: List[IssueType] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    coaching_point: str = Field(description="Specific actionable advice", max_length=500)

class CoachingPoint(BaseModel):
    """Actionable coaching recommendation."""
    priority: int = Field(ge=1, le=5, description="1=highest priority")
    title: str = Field(max_length=100)
    description: str = Field(max_length=500)
    example_turn: Optional[int] = Field(None, description="Reference turn if applicable")
    suggested_alternative: Optional[str] = Field(None, max_length=300)

class KeyMoment(BaseModel):
    """Most notable moment in the conversation."""
    turn_index: int
    quote: str = Field(max_length=200)
    why_notable: str = Field(max_length=300)
    is_positive: bool = Field(description="True if this is a strength, False if needs work")

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
    assessments: List[DimensionAssessment] = Field(min_length=3, max_length=6)

    # === ISSUE SUMMARY ===
    issue_types: List[IssueType] = Field(description="All issues identified")
    critical_issues: List[IssueType] = Field(description="CRITICAL severity only")
    issue_count: int = Field(ge=0)
    compliance_breach_count: int = Field(ge=0)

    # === BINARY FLAGS ===
    resolution_achieved: bool
    escalation_required: bool
    customer_started_negative: bool

    # === COACHING OUTPUT ===
    coaching_summary: str = Field(max_length=500, description="2-3 sentence summary")
    coaching_points: List[CoachingPoint] = Field(min_length=1, max_length=5)
    strengths: List[str] = Field(max_length=5, description="What agent did well")

    # === CONTEXT ===
    situation_summary: str = Field(max_length=300, description="What was the call about")
    behavior_summary: str = Field(max_length=300, description="How agent handled it")
    key_moment: KeyMoment

    # === CALL CLASSIFICATION ===
    call_type: str = Field(description="hardship, complaint, payment, dispute, etc.")

    # === EXAMPLE TYPE (for aggregation) ===
    example_type: Optional[str] = Field(
        None,
        description="GOOD_EXAMPLE, NEEDS_WORK, or null for average"
    )
```

---

## 5. System Prompt Design

### 5.1 Prompt Structure

```python
# cc_coach/prompts/coach_system_prompt.py

SYSTEM_PROMPT = """
You are an expert contact center quality analyst and coach. Your role is to:
1. Analyze agent-customer conversations
2. Score agent performance across multiple dimensions
3. Identify specific issues with evidence
4. Provide actionable coaching recommendations

## SCORING RUBRIC

### Empathy (1-10)
- 9-10: Exceptional - Acknowledges feelings, uses empathetic language consistently
- 7-8: Good - Shows understanding, some acknowledgment of customer situation
- 5-6: Adequate - Basic politeness, misses emotional cues
- 3-4: Poor - Dismissive, rushes through customer concerns
- 1-2: Critical - Hostile, blaming, or completely ignores customer distress

### Compliance (1-10)
- 9-10: Perfect - All required disclosures made, no prohibited language
- 7-8: Good - Minor omissions, no serious violations
- 5-6: Adequate - Some missing disclosures, borderline language
- 3-4: Poor - Missing key disclosures, inappropriate pressure
- 1-2: Critical - Threats, harassment, or major violations

### Resolution (1-10)
- 9-10: Excellent - Clear next steps, customer satisfied, issue resolved
- 7-8: Good - Progress made, customer understands situation
- 5-6: Adequate - Some progress, unclear next steps
- 3-4: Poor - Little progress, customer more confused
- 1-2: Critical - No resolution, customer worse off than before

### Professionalism (1-10)
- 9-10: Exemplary - Clear, respectful, appropriate language throughout
- 7-8: Good - Professional with minor lapses
- 5-6: Adequate - Generally acceptable, some informal language
- 3-4: Poor - Unprofessional tone or language
- 1-2: Critical - Rude, inappropriate, or offensive

### De-escalation (1-10)
(Only score if customer showed negative sentiment at any point)
- 9-10: Masterful - Transformed angry customer to satisfied
- 7-8: Effective - Calmed customer, reduced tension
- 5-6: Partial - Some effort, mixed results
- 3-4: Ineffective - Failed to calm, neutral at best
- 1-2: Escalated - Made situation worse

### Efficiency (1-10)
- 9-10: Optimal - Focused, no unnecessary repetition
- 7-8: Good - Mostly efficient, minor tangents
- 5-6: Adequate - Some redundancy
- 3-4: Poor - Excessive repetition, unclear communication
- 1-2: Critical - Wasted significant time, confusing

## COMPLIANCE REQUIREMENTS

### Required Disclosures (must mention if applicable):
- Right to dispute the debt
- Hardship program availability (if customer mentions financial difficulty)
- Payment plan options

### Prohibited Language:
- Threats of legal action (unless debt is actually in legal)
- Threats to garnish wages (without court order)
- Threatening to contact employer
- Harassment or repeated pressure
- Disclosure of debt to third parties

## EVIDENCE REQUIREMENTS

For every issue identified:
1. Cite the EXACT turn number
2. Quote the EXACT text (max 150 chars)
3. Explain WHY it's an issue
4. Assign severity: CRITICAL, HIGH, MEDIUM, or LOW

## OUTPUT REQUIREMENTS

1. All scores must be justified with evidence
2. Coaching points must be SPECIFIC (cite turns, suggest alternatives)
3. If no issues found in a dimension, score 8+ and note strengths
4. Always identify at least one strength
5. Always provide at least one coaching point (even for excellent calls)

## CI FLAGS INTERPRETATION

You will receive CI phrase matcher flags. Use them as hints but make your own judgment:
- has_compliance_violations: Check these turns carefully
- missing_required_disclosures: Verify disclosures were made
- no_empathy_shown: Look for empathy statements
- customer_escalated: Assess de-escalation attempts
"""

# Version tracking for reproducibility
PROMPT_VERSION = "1.0.0"
MODEL_VERSION = "gemini-2.5-flash"
```

### 5.2 Embedded Policy Knowledge (Phase 1 - No RAG)

```python
# Appended to system prompt for Phase 1
EMBEDDED_POLICY = """
## POLICY REFERENCE (Collections - v2025.1)

### Identity Verification
Before discussing account details, agent must:
- Confirm they are speaking to the account holder
- If wrong party, immediately end discussion of account

### Hardship Handling
If customer mentions ANY of these, agent must offer hardship program:
- Job loss / unemployment
- Medical issues / illness
- Divorce / separation
- Death in family
- Natural disaster impact

### Payment Arrangements
Agent should always:
- Offer multiple payment options
- Explain consequences of non-payment clearly (without threats)
- Document any promises to pay

### Escalation Triggers
Immediately escalate if customer:
- Mentions suicide or self-harm
- Threatens violence
- Claims identity theft
- Requests supervisor 3+ times
"""
```

---

## 6. Implementation

### 6.1 Agent Definition

```python
# cc_coach/agents/conversation_coach.py

from google.adk import Agent
from google.adk.runners import LocalRunner
from pydantic import BaseModel
import json

from cc_coach.schemas.coaching_input import CoachingInput
from cc_coach.schemas.coaching_output import CoachingOutput
from cc_coach.prompts.coach_system_prompt import SYSTEM_PROMPT, EMBEDDED_POLICY, PROMPT_VERSION, MODEL_VERSION


def create_conversation_coach() -> Agent:
    """Create the conversation coaching agent."""

    full_instruction = SYSTEM_PROMPT + "\n\n" + EMBEDDED_POLICY

    agent = Agent(
        name="conversation_coach",
        model=MODEL_VERSION,
        description="Analyzes contact center conversations and provides coaching feedback",
        instruction=full_instruction,
        input_schema=CoachingInput,
        output_schema=CoachingOutput,
        output_key="coaching_result",
        # No tools for Phase 1 - pure analysis
        tools=[],
    )

    return agent


class CoachingService:
    """Service to run conversation coaching."""

    def __init__(self):
        self.agent = create_conversation_coach()
        self.runner = LocalRunner(agent=self.agent)

    def analyze_conversation(self, input_data: CoachingInput) -> CoachingOutput:
        """
        Analyze a conversation and return coaching output.

        Args:
            input_data: CoachingInput with transcript and metadata

        Returns:
            CoachingOutput with scores, evidence, and coaching points
        """
        # Run the agent
        result = self.runner.run(
            input_data=input_data.model_dump(),
            session_id=input_data.conversation_id,
        )

        # Extract the output (stored in output_key)
        coaching_result = result.get("coaching_result")

        if not coaching_result:
            raise ValueError("Agent did not produce coaching result")

        # Validate against output schema
        return CoachingOutput.model_validate(coaching_result)

    def get_metadata(self) -> dict:
        """Return version info for tracking."""
        return {
            "model_version": MODEL_VERSION,
            "prompt_version": PROMPT_VERSION,
            "agent_name": self.agent.name,
        }
```

### 6.2 Orchestration Service

```python
# cc_coach/services/coaching.py

from datetime import datetime, timezone
from typing import Optional

from google.cloud import bigquery

from cc_coach.agents.conversation_coach import CoachingService
from cc_coach.schemas.coaching_input import CoachingInput, Turn, CIFlags, PhraseMatch, CallMetadata
from cc_coach.schemas.coaching_output import CoachingOutput
from cc_coach.services.bigquery import BigQueryService


class CoachingOrchestrator:
    """Orchestrates the coaching workflow."""

    def __init__(self):
        self.bq = BigQueryService()
        self.coach = CoachingService()

    def generate_coaching(self, conversation_id: str) -> CoachingOutput:
        """
        Generate coaching for a conversation.

        Args:
            conversation_id: ID of the conversation to coach

        Returns:
            CoachingOutput with scores and recommendations
        """
        # 1. Fetch data from BQ
        ci_data = self._fetch_ci_enrichment(conversation_id)
        registry_data = self._fetch_registry(conversation_id)

        if not ci_data:
            raise ValueError(f"No CI enrichment found for {conversation_id}")

        # 2. Build input
        input_data = self._build_coaching_input(conversation_id, ci_data, registry_data)

        # 3. Run coach
        output = self.coach.analyze_conversation(input_data)

        # 4. Store result
        self._store_coaching_result(conversation_id, output, registry_data)

        # 5. Update registry status
        self._update_registry_status(conversation_id, "COACHED")

        return output

    def _fetch_ci_enrichment(self, conversation_id: str) -> Optional[dict]:
        """Fetch CI enrichment data from BigQuery."""
        query = """
            SELECT *
            FROM `{project}.{dataset}.ci_enrichment`
            WHERE conversation_id = @conversation_id
        """.format(
            project=self.bq.project_id,
            dataset=self.bq.dataset_id,
        )

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("conversation_id", "STRING", conversation_id)
            ]
        )

        results = list(self.bq.client.query(query, job_config=job_config))
        return dict(results[0]) if results else None

    def _fetch_registry(self, conversation_id: str) -> Optional[dict]:
        """Fetch conversation registry data."""
        query = """
            SELECT *
            FROM `{project}.{dataset}.conversation_registry`
            WHERE conversation_id = @conversation_id
        """.format(
            project=self.bq.project_id,
            dataset=self.bq.dataset_id,
        )

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("conversation_id", "STRING", conversation_id)
            ]
        )

        results = list(self.bq.client.query(query, job_config=job_config))
        return dict(results[0]) if results else None

    def _build_coaching_input(
        self,
        conversation_id: str,
        ci_data: dict,
        registry_data: Optional[dict]
    ) -> CoachingInput:
        """Build CoachingInput from BQ data."""

        # Parse transcript into turns
        transcript = ci_data.get("transcript", "")
        turns = self._parse_transcript(transcript)

        # Build CI flags from phrase matches
        phrase_matches_raw = ci_data.get("phrase_matches", [])
        ci_flags = self._build_ci_flags(ci_data.get("ci_flags", []))
        phrase_matches = self._parse_phrase_matches(phrase_matches_raw)

        # Build metadata
        labels = ci_data.get("labels", {})
        if isinstance(labels, str):
            import json
            labels = json.loads(labels) if labels else {}

        metadata = CallMetadata(
            agent_id=labels.get("agent_id", "UNKNOWN"),
            business_line=labels.get("business_line", "COLLECTIONS"),
            direction=labels.get("direction", "UNKNOWN"),
            queue=labels.get("queue"),
            call_outcome=labels.get("call_outcome"),
            duration_seconds=ci_data.get("duration_seconds"),
        )

        return CoachingInput(
            conversation_id=conversation_id,
            turns=turns,
            turn_count=len(turns),
            metadata=metadata,
            customer_sentiment_score=ci_data.get("customer_sentiment_score"),
            customer_sentiment_start=None,  # Calculate if needed
            customer_sentiment_end=None,
            ci_flags=ci_flags,
            phrase_matches=phrase_matches,
            ci_summary=ci_data.get("ci_summary"),
        )

    def _parse_transcript(self, transcript: str) -> list[Turn]:
        """Parse transcript string into Turn objects."""
        # Transcript format: "SPEAKER: text\n..."
        turns = []
        lines = transcript.strip().split("\n")

        for i, line in enumerate(lines):
            if ": " in line:
                speaker, text = line.split(": ", 1)
                speaker = speaker.strip().upper()
                if speaker in ("AGENT", "CUSTOMER"):
                    turns.append(Turn(
                        index=i + 1,
                        speaker=speaker,
                        text=text.strip(),
                        sentiment=None,  # Could populate from per_turn_sentiments
                    ))

        return turns

    def _build_ci_flags(self, flags: list) -> CIFlags:
        """Build CIFlags from list of flag strings."""
        return CIFlags(
            has_compliance_violations="compliance_violations" in str(flags).lower(),
            missing_required_disclosures="required_disclosures" in str(flags).lower(),
            no_empathy_shown="empathy_indicators" not in str(flags).lower(),
            customer_escalated="escalation_triggers" in str(flags).lower(),
        )

    def _parse_phrase_matches(self, matches: list) -> list[PhraseMatch]:
        """Parse phrase matches from BQ format."""
        result = []
        for match in matches or []:
            if isinstance(match, dict):
                for m in match.get("matches", []):
                    result.append(PhraseMatch(
                        matcher_name=match.get("display_name", ""),
                        phrase=m.get("text", ""),
                        turn_index=m.get("turn_index", 0),
                        speaker=m.get("participant_role", "UNKNOWN"),
                    ))
        return result

    def _store_coaching_result(
        self,
        conversation_id: str,
        output: CoachingOutput,
        registry_data: Optional[dict]
    ) -> None:
        """Store coaching result in BigQuery."""
        # Get metadata
        meta = self.coach.get_metadata()
        labels = registry_data.get("labels", {}) if registry_data else {}
        if isinstance(labels, str):
            import json
            labels = json.loads(labels) if labels else {}

        row = {
            "conversation_id": conversation_id,
            "agent_id": labels.get("agent_id", "UNKNOWN"),
            "business_line": labels.get("business_line"),
            "team": labels.get("team"),
            "queue": labels.get("queue"),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),

            # Scores
            "empathy_score": output.empathy_score,
            "compliance_score": output.compliance_score,
            "resolution_score": output.resolution_score,
            "professionalism_score": output.professionalism_score,
            "de_escalation_score": output.de_escalation_score,
            "efficiency_score": output.efficiency_score,
            "overall_score": output.overall_score,

            # Issues
            "issue_types": [it.value for it in output.issue_types],
            "critical_issues": [it.value for it in output.critical_issues],
            "issue_count": output.issue_count,
            "compliance_breach_count": output.compliance_breach_count,

            # Flags
            "resolution_achieved": output.resolution_achieved,
            "escalation_required": output.escalation_required,
            "customer_started_negative": output.customer_started_negative,

            # Coaching
            "coaching_summary": output.coaching_summary,
            "coaching_points": [cp.model_dump() for cp in output.coaching_points],
            "strengths": output.strengths,

            # Context
            "situation_summary": output.situation_summary,
            "behavior_summary": output.behavior_summary,
            "call_type": output.call_type,
            "example_type": output.example_type,

            # Metadata
            "model_version": meta["model_version"],
            "prompt_version": meta["prompt_version"],
        }

        # Insert into coach_analysis table
        table_ref = f"{self.bq.project_id}.{self.bq.dataset_id}.coach_analysis"
        errors = self.bq.client.insert_rows_json(table_ref, [row])

        if errors:
            raise RuntimeError(f"Failed to insert coaching result: {errors}")

    def _update_registry_status(self, conversation_id: str, status: str) -> None:
        """Update conversation status in registry."""
        query = """
            UPDATE `{project}.{dataset}.conversation_registry`
            SET status = @status,
                coached_at = CURRENT_TIMESTAMP(),
                updated_at = CURRENT_TIMESTAMP()
            WHERE conversation_id = @conversation_id
        """.format(
            project=self.bq.project_id,
            dataset=self.bq.dataset_id,
        )

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("status", "STRING", status),
                bigquery.ScalarQueryParameter("conversation_id", "STRING", conversation_id),
            ]
        )

        self.bq.client.query(query, job_config=job_config).result()
```

### 6.3 CLI Commands

```python
# cc_coach/commands/coach.py

import typer
from rich.console import Console
from rich.table import Table
import json

from cc_coach.services.coaching import CoachingOrchestrator

app = typer.Typer(help="Coaching commands")
console = Console()


@app.command("generate")
def generate_coaching(
    conversation_id: str = typer.Argument(..., help="Conversation ID to coach"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Generate coaching for a single conversation."""
    console.print(f"[bold blue]Generating coaching for {conversation_id}...[/bold blue]")

    try:
        orchestrator = CoachingOrchestrator()
        result = orchestrator.generate_coaching(conversation_id)

        if output_json:
            console.print_json(result.model_dump_json(indent=2))
        else:
            _display_coaching_result(result)

        console.print(f"\n[bold green]Coaching saved to BigQuery[/bold green]")

    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)


@app.command("generate-pending")
def generate_pending(
    limit: int = typer.Option(10, "--limit", "-l", help="Max conversations to process"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be processed"),
):
    """Generate coaching for all pending (ENRICHED) conversations."""
    orchestrator = CoachingOrchestrator()

    # Query for pending conversations
    pending = orchestrator.bq.get_pending_coaching(limit=limit)

    if not pending:
        console.print("[yellow]No pending conversations found[/yellow]")
        return

    console.print(f"[bold]Found {len(pending)} pending conversations[/bold]")

    if dry_run:
        for conv_id in pending:
            console.print(f"  Would process: {conv_id}")
        return

    # Process each
    success = 0
    failed = 0

    for conv_id in pending:
        try:
            console.print(f"Processing {conv_id}...", end=" ")
            orchestrator.generate_coaching(conv_id)
            console.print("[green]OK[/green]")
            success += 1
        except Exception as e:
            console.print(f"[red]FAILED: {e}[/red]")
            failed += 1

    console.print(f"\n[bold]Complete: {success} success, {failed} failed[/bold]")


@app.command("get")
def get_coaching(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get existing coaching for a conversation."""
    orchestrator = CoachingOrchestrator()

    result = orchestrator.bq.get_coaching_result(conversation_id)

    if not result:
        console.print(f"[yellow]No coaching found for {conversation_id}[/yellow]")
        raise typer.Exit(1)

    if output_json:
        console.print_json(json.dumps(result, default=str))
    else:
        _display_coaching_from_bq(result)


def _display_coaching_result(result):
    """Display coaching result in rich format."""
    # Scores table
    scores_table = Table(title="Scores")
    scores_table.add_column("Dimension")
    scores_table.add_column("Score", justify="right")

    scores_table.add_row("Empathy", f"{result.empathy_score}/10")
    scores_table.add_row("Compliance", f"{result.compliance_score}/10")
    scores_table.add_row("Resolution", f"{result.resolution_score}/10")
    scores_table.add_row("Professionalism", f"{result.professionalism_score}/10")
    scores_table.add_row("De-escalation", f"{result.de_escalation_score}/10")
    scores_table.add_row("Efficiency", f"{result.efficiency_score}/10")
    scores_table.add_row("[bold]Overall[/bold]", f"[bold]{result.overall_score:.1f}/10[/bold]")

    console.print(scores_table)

    # Summary
    console.print(f"\n[bold]Summary:[/bold] {result.coaching_summary}")
    console.print(f"[bold]Situation:[/bold] {result.situation_summary}")

    # Issues
    if result.critical_issues:
        console.print(f"\n[bold red]Critical Issues:[/bold red]")
        for issue in result.critical_issues:
            console.print(f"  - {issue.value}")

    # Coaching points
    console.print(f"\n[bold]Coaching Points:[/bold]")
    for cp in result.coaching_points:
        console.print(f"  {cp.priority}. [bold]{cp.title}[/bold]")
        console.print(f"     {cp.description}")
        if cp.suggested_alternative:
            console.print(f"     [green]Try: {cp.suggested_alternative}[/green]")

    # Strengths
    console.print(f"\n[bold green]Strengths:[/bold green]")
    for s in result.strengths:
        console.print(f"  + {s}")
```

---

## 7. RAG Preparation (Phase 1.5)

### 7.1 Why RAG Later?

| Approach | Phase 1 (Embedded) | Phase 1.5 (RAG) |
|----------|-------------------|-----------------|
| Policy updates | Redeploy code | Update RAG corpus |
| Version control | Git (prompts) | Corpus metadata |
| Complexity | Low | Medium |
| Auditability | Limited | Full citations |

### 7.2 RAG Architecture (Future)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PHASE 1.5: ADD RAG                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Document Sources:                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  GCS: gs://bucket/policies/                                          │    │
│  │  ├── compliance/                                                     │    │
│  │  │   ├── asic_guidelines_2024.md                                    │    │
│  │  │   └── corporate_compliance_v2025.1.md                            │    │
│  │  ├── playbooks/                                                      │    │
│  │  │   ├── de_escalation_v2.md                                        │    │
│  │  │   └── hardship_handling_v3.md                                    │    │
│  │  └── manifest.json  (version metadata)                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                           │                                                  │
│                           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Vertex AI RAG Engine                                                │    │
│  │  ─────────────────────                                               │    │
│  │  • Corpus: policy_corpus                                             │    │
│  │  • Chunking: 500 tokens, 100 overlap                                │    │
│  │  • Metadata: doc_id, version, effective_date, section_id            │    │
│  │  • Filters: business_line, doc_type                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                           │                                                  │
│                           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Multi-Agent Pattern (ADK limitation workaround)                     │    │
│  │                                                                       │    │
│  │  ┌─────────────────┐      ┌─────────────────┐                       │    │
│  │  │ PolicyRetriever │      │ ConversationCoach│                       │    │
│  │  │ (RAG tool only) │◀─────│ (main agent)     │                       │    │
│  │  └─────────────────┘      └─────────────────┘                       │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.3 Versioning Strategy

```python
# Policy document metadata structure
{
    "doc_id": "CORP_COMPLIANCE_2025",
    "version": "2025.1",
    "effective_from": "2025-01-01",
    "effective_to": null,  # Current version
    "business_line": ["COLLECTIONS", "LOANS"],
    "doc_type": "compliance",
    "supersedes": "CORP_COMPLIANCE_2024",
    "sections": [
        {"section_id": "SEC_001", "title": "Required Disclosures"},
        {"section_id": "SEC_002", "title": "Prohibited Language"},
    ]
}
```

**No retraining required**: RAG is retrieval-based, not model training. Update corpus = immediate effect.

---

## 8. Operability Considerations

### 8.1 Version Tracking

Every coaching output includes:
```python
{
    "model_version": "gemini-2.5-flash",
    "prompt_version": "1.0.0",
    "rag_corpus_version": "2025.1",  # Future
    "analyzed_at": "2025-01-15T10:30:00Z"
}
```

### 8.2 Prompt Version Management

```
cc_coach/prompts/
├── __init__.py
├── coach_system_prompt.py      # Current version
└── versions/
    ├── v1_0_0.py               # Initial release
    ├── v1_1_0.py               # Added de-escalation rubric
    └── v1_2_0.py               # Improved compliance detection
```

### 8.3 Re-coaching Strategy

When prompt/model changes:
1. **Don't auto-re-coach** - Keep historical data for comparison
2. **Add version filter** - Query by prompt_version in reports
3. **Manual re-run** - `cc-coach coach regenerate --version 1.2.0`

### 8.4 Cost Estimation

| Component | Per Conversation | 1000 Convos/Day |
|-----------|-----------------|-----------------|
| Input tokens (~3K) | ~$0.0015 | $1.50 |
| Output tokens (~800) | ~$0.002 | $2.00 |
| **Total** | ~$0.004 | **$4/day** |

(Based on Gemini 2.5 Flash pricing as of 2025)

---

## 9. Definition of Done (Phase 1)

### 9.1 Functional Requirements

- [ ] `cc-coach coach generate <id>` works end-to-end
- [ ] Coaching output matches CoachingOutput schema
- [ ] All 6 score dimensions populated (1-10)
- [ ] Evidence includes turn numbers and quotes
- [ ] Coaching points are specific (not generic)
- [ ] Results stored in BigQuery coach_analysis table
- [ ] Registry status updated to COACHED

### 9.2 Quality Requirements

- [ ] Run on all 9 dev conversations successfully
- [ ] Manual review: scores are reasonable
- [ ] Manual review: evidence is accurate (quotes match transcript)
- [ ] Manual review: coaching is actionable
- [ ] No JSON parsing errors

### 9.3 Technical Requirements

- [ ] ADK agent defined with Pydantic schemas
- [ ] Error handling for missing data
- [ ] Version tracking in outputs
- [ ] CLI help text complete

---

## 10. Next Steps After Phase 1

| Phase | Focus | Key Addition |
|-------|-------|--------------|
| **1.5** | Add RAG | Policy retrieval + citations |
| **2** | Daily Summary | SQL aggregation + Daily Coach |
| **3** | Weekly Report | Dashboard visualization |
| **4** | Evaluation | Human calibration, auto-evals |
| **5** | Monitoring | Cost tracking, quality alerts, FinOps |

---

## Appendix A: Dependencies

```txt
# requirements.txt additions for Phase 1
google-adk>=0.1.0
google-cloud-aiplatform>=1.50.0
pydantic>=2.0.0
```

## Appendix B: Environment Setup

```bash
# Set up ADK with Vertex AI
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_REGION=us-central1
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/vertex-ai-demo-key.json

# Install ADK
pip install google-adk

# Verify
python -c "from google.adk import Agent; print('ADK OK')"
```
