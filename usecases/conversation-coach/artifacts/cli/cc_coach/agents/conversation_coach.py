"""
Conversation Coach ADK Agent.

Uses Google ADK framework to analyze contact center conversations and generate coaching feedback.
This module defines the agent using ADK's declarative Agent class and provides
a service wrapper for single-shot analysis requests.
"""

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from cc_coach.config import get_settings
from cc_coach.prompts.coach_system_prompt import (
    CITATIONS_INSTRUCTION,
    EMBEDDED_POLICY,
    MODEL_VERSION,
    PROMPT_VERSION,
    RAG_CONTEXT_TEMPLATE,
    SYSTEM_PROMPT,
)
from cc_coach.schemas.coaching_input import CoachingInput
from cc_coach.schemas.coaching_output import CoachingOutput

logger = logging.getLogger(__name__)

# Production logging configuration
LOG_FULL_PROMPT = os.getenv("CC_LOG_FULL_PROMPT", "false").lower() == "true"
LOG_LEVEL_PROMPT = os.getenv("CC_LOG_LEVEL_PROMPT", "DEBUG")
LOG_RAG_CONTEXT = os.getenv("CC_LOG_RAG_CONTEXT", "true").lower() == "true"

# Global storage for last RAG context (for debugging/verification)
_last_rag_context: Optional[str] = None
_last_full_instruction: Optional[str] = None


def get_last_rag_context() -> Optional[str]:
    """Get the last RAG context used for coaching."""
    return _last_rag_context


def get_last_full_instruction() -> Optional[str]:
    """Get the last full instruction sent to the model."""
    return _last_full_instruction


def _get_prompt_hash(prompt: str) -> str:
    """Generate a hash of the prompt for correlation without logging full content."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token average for English)."""
    return len(text) // 4


def _create_log_context(
    request_id: str,
    conversation_id: str,
    model: str,
    prompt_version: str,
    has_rag: bool,
    prompt_length: int,
    estimated_tokens: int,
) -> dict[str, Any]:
    """Create structured log context for monitoring."""
    return {
        "request_id": request_id,
        "conversation_id": conversation_id,
        "model": model,
        "prompt_version": prompt_version,
        "has_rag_context": has_rag,
        "prompt_length_chars": prompt_length,
        "estimated_input_tokens": estimated_tokens,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def create_conversation_coach_agent(
    model: Optional[str] = None,
    rag_context: Optional[str] = None,
    allow_fallback: bool = False,
) -> Agent:
    """
    Create an ADK Agent for conversation coaching.

    The agent is configured with:
    - System instruction for coaching analysis
    - Output schema (CoachingOutput) for structured responses
    - Model configuration

    Args:
        model: Optional model override (default: gemini-2.5-flash)
        rag_context: Optional RAG context to include in instruction
        allow_fallback: If True, use embedded policy when RAG not available

    Returns:
        Configured ADK Agent instance

    Note:
        When output_schema is set, the agent cannot use tools.
        RAG context is injected into the instruction instead.
    """
    model = model or MODEL_VERSION

    global _last_rag_context, _last_full_instruction

    # Build the full instruction with policy section
    if rag_context:
        policy_section = RAG_CONTEXT_TEMPLATE.format(context=rag_context)
        citations_section = CITATIONS_INSTRUCTION
        logger.info(f"Creating agent with RAG context ({len(rag_context)} chars)")
        _last_rag_context = rag_context
        if LOG_RAG_CONTEXT:
            logger.debug(f"RAG Context:\n{rag_context[:2000]}{'...' if len(rag_context) > 2000 else ''}")
    elif allow_fallback:
        logger.warning("RAG context not available, using embedded policy fallback")
        policy_section = EMBEDDED_POLICY
        citations_section = ""
        _last_rag_context = "[FALLBACK: Embedded policy used - no RAG context available]"
    else:
        raise ValueError(
            "RAG context is required for coaching. "
            "Set allow_fallback=True to use embedded policy, "
            "or configure RAG_DATA_STORE_ID environment variable."
        )

    # Combine system prompt with policy
    full_instruction = f"""{SYSTEM_PROMPT}

{policy_section}

{citations_section}

---

# YOUR TASK

Analyze the conversation provided by the user and provide coaching feedback.
Return your analysis as a JSON object matching the required schema.

Key requirements:
1. Provide scores for all 6 dimensions (1-10 scale)
2. Calculate overall_score as weighted average: (empathy*0.25 + compliance*0.25 + resolution*0.2 + professionalism*0.1 + de_escalation*0.1 + efficiency*0.1)
3. Provide at least 3 dimension assessments with evidence
4. Include at least 1 coaching point
5. Identify the key moment (most notable turn)
6. Classify the call type (hardship, complaint, payment, dispute, inquiry, etc.)
{"7. Include citations for any policy documents referenced" if rag_context else ""}
"""

    # Store for debugging/verification
    _last_full_instruction = full_instruction
    if LOG_FULL_PROMPT:
        logger.info(f"Full instruction:\n{full_instruction[:3000]}...")

    # Create the ADK Agent with output schema
    agent = Agent(
        name="conversation_coach",
        model=model,
        instruction=full_instruction,
        output_schema=CoachingOutput,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.2,  # Lower temperature for more consistent analysis
        ),
    )

    return agent


class CoachingService:
    """
    Service to run conversation coaching using ADK framework.

    This service wraps the ADK Agent and Runner to provide a simple interface
    for single-shot conversation analysis. It handles:
    - Agent creation with RAG context injection
    - Session management for single-shot requests
    - Token counting and cost calculation
    - Structured output parsing

    Architecture:
        CLI/Orchestrator
            └── CoachingService.analyze_conversation()
                    └── ADK Runner.run()
                            └── ADK Agent (instruction + output_schema)
                                    └── Gemini API
    """

    def __init__(self, model: Optional[str] = None):
        """Initialize the coaching service.

        Args:
            model: Optional model override (default from config)
        """
        self.settings = get_settings()
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
        Analyze a conversation and return coaching output using ADK framework.

        This method:
        1. Creates an ADK Agent with the appropriate instruction (including RAG context)
        2. Creates an ADK Runner with in-memory session
        3. Runs the agent once with the conversation as input
        4. Extracts and returns the structured output

        Args:
            input_data: CoachingInput with transcript and metadata
            rag_context: RAG context from knowledge base retrieval
            allow_fallback: If True, use embedded policy when RAG is not available.
                          If False (default), raise error when RAG context is missing.

        Returns:
            CoachingOutput with scores, evidence, and coaching points

        Raises:
            ValueError: If rag_context is None and allow_fallback is False
        """
        # Generate request ID for correlation
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Create the ADK agent with RAG context
        agent = create_conversation_coach_agent(
            model=self.model,
            rag_context=rag_context,
            allow_fallback=allow_fallback,
        )

        # Format input as text
        prompt_text = input_data.to_prompt_text()
        user_message = f"""# CONVERSATION TO ANALYZE

{prompt_text}
"""

        # Estimate tokens for logging
        full_prompt = agent.instruction + user_message
        prompt_hash = _get_prompt_hash(full_prompt)
        estimated_tokens = _estimate_tokens(full_prompt)

        # Create structured log context
        log_ctx = _create_log_context(
            request_id=request_id,
            conversation_id=input_data.conversation_id,
            model=self.model,
            prompt_version=self.prompt_version,
            has_rag=rag_context is not None,
            prompt_length=len(full_prompt),
            estimated_tokens=estimated_tokens,
        )

        # Log request info
        logger.info(
            f"[{request_id}] ADK coaching request: conversation={input_data.conversation_id} "
            f"model={self.model} has_rag={rag_context is not None} "
            f"prompt_hash={prompt_hash} est_tokens={estimated_tokens}"
        )

        # Log full prompt if enabled (DEBUG level by default for security)
        if LOG_FULL_PROMPT and LOG_LEVEL_PROMPT != "OFF":
            if LOG_LEVEL_PROMPT == "INFO":
                logger.info(f"[{request_id}] Full prompt:\n{full_prompt}")
            else:
                logger.debug(f"[{request_id}] Full prompt:\n{full_prompt}")

        # Log RAG context separately for debugging
        if rag_context:
            logger.debug(
                f"[{request_id}] RAG context ({len(rag_context)} chars):\n{rag_context}"
            )

        try:
            # Create ADK Runner with in-memory session service
            # The Runner handles the Gemini API call via the agent
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
            # The agent will return structured output matching CoachingOutput
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

            latency_ms = int((time.time() - start_time) * 1000)

            # Calculate token usage from result
            input_tokens = estimated_tokens
            output_tokens = _estimate_tokens(result_text) if result_text else 0

            # Calculate cost (Gemini Flash pricing)
            from cc_coach.monitoring.cost import CostCalculator
            cost_calc = CostCalculator(self.model)
            cost_breakdown = cost_calc.calculate_total_cost(input_tokens, output_tokens)

            # Store metrics for caller to access
            self.last_input_tokens = input_tokens
            self.last_output_tokens = output_tokens
            self.last_latency_ms = latency_ms
            self.last_cost_usd = cost_breakdown.gemini_total_cost

            # Log response metrics
            logger.info(
                f"[{request_id}] ADK coaching response: latency_ms={latency_ms} "
                f"input_tokens={input_tokens} output_tokens={output_tokens} "
                f"cost_usd={self.last_cost_usd:.6f} conversation={input_data.conversation_id}"
            )

            # Parse response - ADK should return JSON matching output_schema
            try:
                result_json = json.loads(result_text)
                coaching_output = CoachingOutput.model_validate(result_json)

                # Log coaching results summary
                logger.info(
                    f"[{request_id}] Coaching result: overall_score={coaching_output.overall_score:.1f} "
                    f"compliance={coaching_output.compliance_score} "
                    f"coaching_points={len(coaching_output.coaching_points)} "
                    f"call_type={coaching_output.call_type} "
                    f"conversation={input_data.conversation_id}"
                )

                # Log full response at DEBUG level
                logger.debug(f"[{request_id}] Full response JSON:\n{result_text}")

                return coaching_output

            except (json.JSONDecodeError, ValidationError) as e:
                logger.error(
                    f"[{request_id}] Failed to parse coaching output: {e} "
                    f"conversation={input_data.conversation_id}"
                )
                logger.debug(f"[{request_id}] Raw response: {result_text}")
                raise ValueError(f"Invalid coaching output from ADK agent: {e}")

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"[{request_id}] ADK agent error: {e} "
                f"latency_ms={latency_ms} conversation={input_data.conversation_id}"
            )
            raise

    def get_metadata(self) -> dict:
        """Return version info for tracking."""
        return {
            "model_version": self.model,
            "prompt_version": self.prompt_version,
            "agent_name": "conversation_coach",
            "framework": "google-adk",  # New: indicate ADK usage
        }


# Convenience function to create agent metadata
def create_conversation_coach() -> dict:
    """
    Create the conversation coaching agent configuration.

    Returns agent metadata for reference.
    """
    return {
        "name": "conversation_coach",
        "model": MODEL_VERSION,
        "prompt_version": PROMPT_VERSION,
        "description": "Analyzes contact center conversations and provides coaching feedback",
        "framework": "google-adk",
    }
