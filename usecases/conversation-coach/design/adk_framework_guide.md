# Google ADK Framework Guide

> This guide explains Google ADK (Agent Development Kit) features based on [official documentation](https://google.github.io/adk-docs/), with concrete examples from the Conversation Coach implementation.

**Structure**: Each section covers an ADK concept with:
1. **ADK Feature** - What it is (from Google docs)
2. **Coach Implementation** - How we use it
3. **Code Reference** - Actual code from this project

---

## 1. What is ADK?

### 1.1 Official Definition

From [ADK Documentation](https://google.github.io/adk-docs/get-started/about/):

> ADK is Google's framework for building, evaluating, and deploying AI-powered agents. It provides a robust and flexible environment for creating both conversational and non-conversational agents, capable of handling complex tasks and workflows.

Key characteristics:
- **Model-agnostic**: Optimized for Gemini but works with other models
- **Deployment-agnostic**: Run locally, Cloud Run, or Vertex AI Agent Engine
- **Multi-agent capable**: Agents can delegate to other agents

### 1.2 Coach Use Case

We use ADK for **single-shot, non-conversational analysis**:
- Input: Contact center conversation transcript
- Output: Structured coaching feedback (scores, evidence, recommendations)
- Pattern: One request → one response → exit

This is simpler than ADK's full multi-turn conversation capabilities, but we benefit from:
- Structured output enforcement via `output_schema`
- Session tracking for traceability
- Standard agent patterns for future expansion

---

## 2. Core Components

### 2.1 Component Overview

From [ADK Runtime docs](https://google.github.io/adk-docs/runtime/):

| Component | ADK Definition | Coach Usage |
|-----------|---------------|-------------|
| **Agent** | "Fundamental execution unit designed for specific tasks" | `conversation_coach` agent with scoring logic |
| **Runner** | "Execution engine that orchestrates agent interactions" | Executes single analysis request |
| **Session** | "Single, ongoing interaction between user and agent system" | One session per conversation analyzed |
| **Event** | "Basic communication unit representing occurrences" | Model response events with JSON output |
| **State** | "Persistent data associated with a conversation" | Not used (single-shot pattern) |

### 2.2 How They Work Together

From ADK docs:
> The Runner manages agent execution for a particular app session. The framework uses a layered approach: Runners execute agents within Sessions, which generate Events forming the conversation history.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ADK COMPONENT FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CoachingService.analyze_conversation()                                     │
│       │                                                                     │
│       ├─1─► Agent created with instruction + output_schema                  │
│       │                                                                     │
│       ├─2─► SessionService.create_session_sync()                            │
│       │         └── app_name="conversation_coach"                           │
│       │         └── user_id=agent_id                                        │
│       │         └── session_id=conversation_id                              │
│       │                                                                     │
│       ├─3─► Runner created with agent + session_service                     │
│       │                                                                     │
│       ├─4─► Runner.run() with user message (transcript)                     │
│       │         │                                                           │
│       │         └── yields Event objects with model response                │
│       │                                                                     │
│       └─5─► Parse JSON from Events → CoachingOutput                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Agent

### 3.1 ADK Feature

From [LLM Agent docs](https://google.github.io/adk-docs/agents/llm-agents/):

> An LlmAgent is the "thinking" component of ADK applications, leveraging LLMs for reasoning, decision-making, and tool interaction.

**Key Parameters:**

| Parameter | Purpose |
|-----------|---------|
| `name` | Unique identifier (critical for multi-agent systems) |
| `model` | LLM to use (e.g., `"gemini-2.5-flash"`) |
| `instruction` | Core task/goal, personality, constraints, output format |
| `output_schema` | Pydantic model for structured JSON responses |
| `tools` | Functions the agent can invoke |
| `generate_content_config` | LLM parameters (temperature, etc.) |

**Critical Constraint** from docs:
> Tools cannot be effectively used when `output_schema` is configured.

This means you must choose:
- **Tool-based**: Agent calls functions for dynamic data
- **Schema-based**: Agent returns structured JSON (our pattern)

### 3.2 Coach Implementation

We use the **schema-based pattern** because:
1. Coaching analysis is self-contained (no external lookups needed)
2. We need guaranteed structured output for downstream storage
3. RAG context is injected into instruction, not via tools

**File**: `cc_coach/agents/conversation_coach.py:74-152`

```python
def create_conversation_coach_agent(
    model: Optional[str] = None,
    rag_context: Optional[str] = None,
    allow_fallback: bool = False,
) -> Agent:
    """
    Create an ADK Agent for conversation coaching.

    Note:
        When output_schema is set, the agent cannot use tools.
        RAG context is injected into the instruction instead.
    """
    model = model or MODEL_VERSION  # "gemini-2.5-flash"

    # Build instruction dynamically based on RAG availability
    if rag_context:
        policy_section = RAG_CONTEXT_TEMPLATE.format(context=rag_context)
        citations_section = CITATIONS_INSTRUCTION
    elif allow_fallback:
        policy_section = EMBEDDED_POLICY
        citations_section = ""
    else:
        raise ValueError("RAG context is required for coaching.")

    # Compose full instruction from components
    full_instruction = f"""{SYSTEM_PROMPT}

{policy_section}

{citations_section}

---

# YOUR TASK

Analyze the conversation provided by the user and provide coaching feedback.
Return your analysis as a JSON object matching the required schema.

Key requirements:
1. Provide scores for all 6 dimensions (1-10 scale)
2. Calculate overall_score as weighted average
3. Provide at least 3 dimension assessments with evidence
4. Include at least 1 coaching point
5. Identify the key moment (most notable turn)
6. Classify the call type
"""

    # Create Agent with structured output schema
    agent = Agent(
        name="conversation_coach",
        model=model,
        instruction=full_instruction,
        output_schema=CoachingOutput,  # Pydantic model - enforces JSON structure
        generate_content_config=types.GenerateContentConfig(
            temperature=0.2,  # Low temperature for consistent scoring
        ),
    )

    return agent
```

### 3.3 Instruction Composition

The `instruction` parameter is where we define agent behavior. From ADK docs:
> The instruction parameter is arguably the most impactful configuration element. It tells the agent its core task, personality, behavioral constraints, tool usage guidance, and desired output format.

Our instruction is composed from modular components:

**File**: `cc_coach/prompts/coach_system_prompt.py`

| Component | Purpose | Lines |
|-----------|---------|-------|
| `SYSTEM_PROMPT` | Role definition, scoring rubric, evidence requirements | 1-115 |
| `RAG_CONTEXT_TEMPLATE` | Dynamic policy documents from knowledge base | 149-158 |
| `EMBEDDED_POLICY` | Fallback policy when RAG unavailable | 118-146 |
| `CITATIONS_INSTRUCTION` | How to cite policy references | 161-172 |

```python
# Example of SYSTEM_PROMPT structure (cc_coach/prompts/coach_system_prompt.py:11-115)
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
...

## COMPLIANCE REQUIREMENTS
### Prohibited Language:
- Threats of legal action (unless debt is actually in legal)
- Threats to garnish wages (without court order)
...

## EVIDENCE REQUIREMENTS
For every issue identified:
1. Cite the EXACT turn number
2. Quote the EXACT text (max 150 chars)
3. Explain WHY it's an issue
4. Assign severity: CRITICAL, HIGH, MEDIUM, or LOW
"""
```

### 3.4 Output Schema

The `output_schema` parameter enforces structured JSON output. From ADK docs:
> When set, the agent's final response must conform to that schema structure.

**File**: `cc_coach/schemas/coaching_output.py`

```python
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

    # === COACHING OUTPUT ===
    coaching_summary: str = Field(description="2-3 sentence summary of key coaching needs")
    coaching_points: list[CoachingPoint] = Field(description="1-5 actionable recommendations")
    strengths: list[str] = Field(description="What the agent did well")

    # === CONTEXT ===
    key_moment: KeyMoment
    call_type: str = Field(description="hardship, complaint, payment, dispute, inquiry, etc.")

    # === RAG CITATIONS ===
    citations: list[str] = Field(default_factory=list)
    rag_context_used: bool = Field(default=False)
```

When ADK sends this schema to Gemini, the model is constrained to return JSON matching this exact structure. This eliminates parsing errors and ensures consistent output.

---

## 4. Runner

### 4.1 ADK Feature

From [ADK Runtime docs](https://google.github.io/adk-docs/runtime/):

> The Runner is the central orchestrator; manages event loop, coordinates Services, forwards events upstream.

**Runner's Operational Loop:**
1. Receives user query, appends to session history
2. Calls `agent.run_async(context)`
3. Waits for yielded Event, commits changes via Services
4. Forwards processed event to application/UI
5. Signals agent to resume; repeats until complete

**Execution Methods:**

| Method | Type | Use Case |
|--------|------|----------|
| `run()` | Synchronous | CLI tools, batch jobs, simpler use cases |
| `run_async()` | Asynchronous | Web servers, concurrent requests, production apps |

From docs:
> `run()` is a synchronous wrapper that internally manages the async event loop. Suitable for scripts, testing, and simpler use cases.

### 4.2 Coach Implementation

We use `run()` (sync) because:
1. CLI is naturally synchronous
2. We process one conversation at a time
3. No need for concurrent request handling

**File**: `cc_coach/agents/conversation_coach.py:271-307`

```python
# Create ADK Runner with in-memory session service
session_service = InMemorySessionService()
runner = Runner(
    agent=agent,
    app_name="conversation_coach",
    session_service=session_service,
)

# Use conversation_id as session_id for traceability
user_id = input_data.metadata.agent_id if input_data.metadata else "system"
session_id = input_data.conversation_id

# Create a new session for this analysis (using sync version)
session_service.create_session_sync(
    app_name="conversation_coach",
    user_id=user_id,
    session_id=session_id,
)

# Run the agent with the conversation input
# runner.run() is SYNC - blocks until complete
result_text = ""
for event in runner.run(
    user_id=user_id,
    session_id=session_id,
    new_message=types.Content(
        role="user",
        parts=[types.Part(text=user_message)],
    ),
):
    # Collect text from model response events
    if event.content and event.content.parts:
        for part in event.content.parts:
            if hasattr(part, 'text') and part.text:
                result_text += part.text
```

---

## 5. Session & SessionService

### 5.1 ADK Feature

From [ADK Session docs](https://google.github.io/adk-docs/sessions/):

> Session represents a single, ongoing interaction between a user and your agent system that contains chronological message and action sequences.

**SessionService** manages session lifecycle:
- Creating, retrieving, updating, deleting sessions
- Appending Events to history
- Modifying State

**Available Implementations:**

| Service | Persistence | Use Case |
|---------|-------------|----------|
| `InMemorySessionService` | None (memory only) | Local testing, fast development |
| Database implementations | SQL/NoSQL | Production persistence |
| Vertex AI Session | Managed | Cloud-native deployment |

**Sync vs Async Methods:**
- `create_session()` - async (requires `await`)
- `create_session_sync()` - sync (blocking)

### 5.2 Coach Implementation

We use `InMemorySessionService` because:
1. Single-shot pattern - no need to persist across requests
2. Session exists only for traceability during the request
3. Simplest option for CLI usage

**File**: `cc_coach/agents/conversation_coach.py:274-290`

```python
from google.adk.sessions import InMemorySessionService

# Create in-memory session service
session_service = InMemorySessionService()

# Create session with traceability IDs
# - app_name: groups sessions by application
# - user_id: the contact center agent being coached
# - session_id: the conversation being analyzed (enables correlation)
session_service.create_session_sync(
    app_name="conversation_coach",
    user_id=input_data.metadata.agent_id,  # e.g., "agent-001"
    session_id=input_data.conversation_id,  # e.g., "conv-12345"
)
```

**Why `create_session_sync()` not `create_session()`?**

Our code is synchronous (CLI, not async web server). Using async `create_session()` would require:
```python
# Would need async context
await session_service.create_session(...)
```

Instead, ADK provides sync alternatives with `_sync` suffix for non-async code.

---

## 6. Event & Event Loop

### 6.1 ADK Feature

From [ADK Runtime docs](https://google.github.io/adk-docs/runtime/):

> The ADK Runtime operates on an Event Loop. This loop facilitates back-and-forth communication between the Runner component and your defined Execution Logic.

**Event Loop Pattern:**
```
User Query → Runner → Agent (yields Event) → Runner Processes →
Yield Upstream → Resume Agent → [Repeat until complete]
```

**Event Properties:**
- `content`: Model response content
- `content.parts`: List of parts (text, function calls, etc.)
- `author`: Who generated the event ("model" or agent name)
- `actions`: Side effects (state_delta, artifact_delta)

**Pause/Resume Pattern** (from docs):
> Execution of the agent logic pauses immediately after the yield statement. It waits for the Runner to complete processing.

### 6.2 Coach Implementation

For structured output (our pattern), events are simpler - we just collect text parts:

**File**: `cc_coach/agents/conversation_coach.py:294-307`

```python
# Run the agent - yields Event objects
result_text = ""
for event in runner.run(
    user_id=user_id,
    session_id=session_id,
    new_message=types.Content(
        role="user",
        parts=[types.Part(text=user_message)],
    ),
):
    # Events contain model response in content.parts
    if event.content and event.content.parts:
        for part in event.content.parts:
            # Extract text from each part
            if hasattr(part, 'text') and part.text:
                result_text += part.text

# result_text is now complete JSON matching CoachingOutput schema
```

**Note**: With `output_schema` set, there's no tool calling, so we don't need to handle function call events. The model generates JSON directly.

---

## 7. Input Message Format

### 7.1 ADK Feature

Messages sent to the agent use `google.genai.types.Content`:

```python
from google.genai import types

message = types.Content(
    role="user",  # or "model" for assistant messages
    parts=[types.Part(text="Your message here")],
)
```

### 7.2 Coach Implementation

We format the conversation transcript into a structured text message:

**File**: `cc_coach/agents/conversation_coach.py:228-233`

```python
# Format input as text
prompt_text = input_data.to_prompt_text()  # CoachingInput → formatted string
user_message = f"""# CONVERSATION TO ANALYZE

{prompt_text}
"""

# Send to runner
for event in runner.run(
    ...
    new_message=types.Content(
        role="user",
        parts=[types.Part(text=user_message)],
    ),
):
```

**CoachingInput.to_prompt_text()** produces structured text:

**File**: `cc_coach/schemas/coaching_input.py:74-125`

```python
def to_prompt_text(self) -> str:
    """Format input as text for the LLM prompt."""
    lines = []

    # Metadata section
    lines.append("## CALL METADATA")
    lines.append(f"Conversation ID: {self.conversation_id}")
    lines.append(f"Agent ID: {self.metadata.agent_id}")
    lines.append(f"Business Line: {self.metadata.business_line}")
    lines.append(f"Direction: {self.metadata.direction}")

    # CI signals
    if self.customer_sentiment_score is not None:
        lines.append(f"\nCustomer Sentiment: {self.customer_sentiment_score:.2f}")

    # Detected phrases from CI
    if self.phrase_matches:
        lines.append("\n## DETECTED PHRASES")
        for pm in self.phrase_matches:
            lines.append(f"- Turn {pm.turn_index} [{pm.speaker}]: \"{pm.phrase}\"")

    # Transcript
    lines.append("\n## TRANSCRIPT")
    for turn in self.turns:
        lines.append(f"Turn {turn.index} [{turn.speaker}]: {turn.text}")

    return "\n".join(lines)
```

**Example Output:**
```
## CALL METADATA
Conversation ID: conv-12345
Agent ID: agent-001
Business Line: COLLECTIONS
Direction: OUTBOUND

Customer Sentiment: -0.45

## TRANSCRIPT
Turn 1 [AGENT]: Hello, this is Collections calling about your account.
Turn 2 [CUSTOMER]: I can't pay right now, I lost my job.
Turn 3 [AGENT]: I understand. Let me tell you about our hardship program...
```

---

## 8. Response Parsing

### 8.1 ADK Feature

When `output_schema` is set, the model returns JSON matching the schema. However, we still need to:
1. Collect the JSON text from events
2. Parse the JSON string
3. Validate against the Pydantic model

### 8.2 Coach Implementation

**File**: `cc_coach/agents/conversation_coach.py:333-358`

```python
# After collecting result_text from events...

try:
    # Parse JSON string to dict
    result_json = json.loads(result_text)

    # Validate against Pydantic schema
    coaching_output = CoachingOutput.model_validate(result_json)

    # Log success
    logger.info(
        f"[{request_id}] Coaching result: overall_score={coaching_output.overall_score:.1f} "
        f"compliance={coaching_output.compliance_score} "
        f"coaching_points={len(coaching_output.coaching_points)}"
    )

    return coaching_output

except (json.JSONDecodeError, ValidationError) as e:
    # Handle malformed responses
    logger.error(f"[{request_id}] Failed to parse coaching output: {e}")
    logger.debug(f"[{request_id}] Raw response: {result_text}")
    raise ValueError(f"Invalid coaching output from ADK agent: {e}")
```

---

## 9. Environment Configuration

### 9.1 Required Environment Variables

ADK with Vertex AI requires specific environment variables:

```bash
# Required for Vertex AI backend
export GOOGLE_GENAI_USE_VERTEXAI=1
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=us-central1

# Authentication (one of these)
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
# OR
gcloud auth application-default login
```

### 9.2 Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Runner.__init__() missing 'session_service'` | Runner requires session service | Add `session_service=InMemorySessionService()` |
| `coroutine 'create_session' was never awaited` | Using async method in sync code | Use `create_session_sync()` |
| `AttributeError: 'str' not in 'NoneType'` | Missing Vertex AI env vars | Set `GOOGLE_GENAI_USE_VERTEXAI=1` etc. |

---

## 10. Service Wrapper Pattern

### 10.1 Pattern Description

We wrap ADK in a service class to:
1. Encapsulate agent creation and execution
2. Provide a simple interface for the orchestrator
3. Track metrics (tokens, latency, cost)

### 10.2 Coach Implementation

**File**: `cc_coach/agents/conversation_coach.py:155-376`

```python
class CoachingService:
    """
    Service to run conversation coaching using ADK framework.

    This service wraps the ADK Agent and Runner to provide a simple interface
    for single-shot conversation analysis.

    Architecture:
        CLI/Orchestrator
            └── CoachingService.analyze_conversation()
                    └── ADK Runner.run()
                            └── ADK Agent (instruction + output_schema)
                                    └── Gemini API
    """

    def __init__(self, model: Optional[str] = None):
        self.model = model or MODEL_VERSION
        self.prompt_version = PROMPT_VERSION

        # Metrics from last call (for monitoring)
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0
        self.last_latency_ms: int = 0
        self.last_cost_usd: float = 0.0

    def analyze_conversation(
        self,
        input_data: CoachingInput,
        rag_context: Optional[str] = None,
        allow_fallback: bool = False,
    ) -> CoachingOutput:
        """
        Analyze a conversation and return coaching output.

        This method:
        1. Creates an ADK Agent with instruction (including RAG context)
        2. Creates an ADK Runner with in-memory session
        3. Runs the agent once with the conversation
        4. Returns the structured output
        """
        # ... implementation shown in previous sections ...

    def get_metadata(self) -> dict:
        """Return version info for tracking."""
        return {
            "model_version": self.model,
            "prompt_version": self.prompt_version,
            "agent_name": "conversation_coach",
            "framework": "google-adk",
        }
```

---

## 11. Complete Flow Example

### End-to-End Execution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ $ cc-coach coach generate conv-12345                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. CLI (cli.py)                                                            │
│     └── Creates CoachingOrchestrator                                        │
│         └── Creates CoachingService (with ADK)                              │
│                                                                             │
│  2. Orchestrator fetches data                                               │
│     └── BQ: ci_enrichment → transcript, sentiment                           │
│     └── BQ: conversation_registry → metadata                                │
│     └── RAG: Vertex AI Search → policy documents                            │
│                                                                             │
│  3. Orchestrator builds CoachingInput                                       │
│     └── Parses transcript into turns                                        │
│     └── Extracts CI flags                                                   │
│     └── Formats as prompt text                                              │
│                                                                             │
│  4. CoachingService.analyze_conversation()                                  │
│     │                                                                       │
│     ├── create_conversation_coach_agent()                                   │
│     │   └── Agent(name, model, instruction + RAG, output_schema)            │
│     │                                                                       │
│     ├── InMemorySessionService.create_session_sync()                        │
│     │   └── app_name="conversation_coach"                                   │
│     │   └── user_id="agent-001"                                             │
│     │   └── session_id="conv-12345"                                         │
│     │                                                                       │
│     ├── Runner(agent, app_name, session_service)                            │
│     │                                                                       │
│     ├── runner.run() ─────────────────────────────────────────────────┐     │
│     │                                                                 │     │
│     │   ┌─────────────────────────────────────────────────────────────┤     │
│     │   │ POST https://us-central1-aiplatform.googleapis.com          │     │
│     │   │                                                             │     │
│     │   │ System: {SYSTEM_PROMPT + RAG_CONTEXT + CITATIONS}           │     │
│     │   │ User: {## CALL METADATA... ## TRANSCRIPT...}                │     │
│     │   │ Response Schema: CoachingOutput                             │     │
│     │   │ Temperature: 0.2                                            │     │
│     │   └─────────────────────────────────────────────────────────────┤     │
│     │                                                                 │     │
│     │   Gemini returns JSON: {                                        │     │
│     │     "empathy_score": 8,                                         │     │
│     │     "compliance_score": 9,                                      │     │
│     │     "overall_score": 8.3,                                       │     │
│     │     "coaching_points": [...],                                   │     │
│     │     "citations": ["POL-002 v1.1"]                               │     │
│     │   }                                                             │     │
│     │ ◄───────────────────────────────────────────────────────────────┘     │
│     │                                                                       │
│     └── json.loads() → CoachingOutput.model_validate()                      │
│                                                                             │
│  5. Orchestrator stores result                                              │
│     └── BQ: coach_analysis table                                            │
│     └── BQ: conversation_registry status → COACHED                          │
│                                                                             │
│  6. CLI displays result                                                     │
│     └── Rich console output                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Key ADK Patterns Summary

### What We Use

| ADK Feature | Coach Usage | Why |
|-------------|-------------|-----|
| `Agent` with `output_schema` | Structured coaching output | Guaranteed JSON format |
| `Runner.run()` (sync) | CLI execution | Simpler than async for batch |
| `InMemorySessionService` | Single-shot sessions | No persistence needed |
| `create_session_sync()` | Session creation | Sync code compatibility |
| `instruction` composition | Dynamic RAG injection | Policy context varies |

### What We Don't Use (Yet)

| ADK Feature | Why Not |
|-------------|---------|
| `tools` | Incompatible with `output_schema`; RAG via instruction instead |
| `State` | Single-shot pattern; no cross-turn memory needed |
| `Memory` | No cross-session context needed |
| `run_async()` | CLI is synchronous; no concurrent requests |
| Multi-agent | Single agent sufficient for coaching |
| Workflow agents | Not a multi-step workflow |

---

## 13. Deployment Options

See separate sections for deployment patterns:
- **CLI (current)**: Manual execution for dev/testing
- **Cloud Run Job + Scheduler**: Recommended for production batch processing
- **Pub/Sub + Cloud Run Service**: For near real-time event-driven processing

The ADK code remains identical across deployment options - only the trigger mechanism changes.

---

## References

### Official Documentation
- [ADK Overview](https://google.github.io/adk-docs/get-started/about/)
- [ADK Runtime](https://google.github.io/adk-docs/runtime/)
- [LLM Agents](https://google.github.io/adk-docs/agents/llm-agents/)
- [Sessions](https://google.github.io/adk-docs/sessions/)
- [API Reference](https://google.github.io/adk-docs/api-reference/python/)

### Project Files
- `cc_coach/agents/conversation_coach.py` - ADK Agent + Service implementation
- `cc_coach/schemas/coaching_input.py` - Input schema
- `cc_coach/schemas/coaching_output.py` - Output schema (ADK output_schema)
- `cc_coach/prompts/coach_system_prompt.py` - Instruction components
- `cc_coach/services/coaching.py` - Orchestrator that uses CoachingService
