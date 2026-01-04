"""
Conversation Coach ADK Agent.

Uses Google ADK to analyze contact center conversations and generate coaching feedback.
"""

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from google import genai
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
LOG_LEVEL_PROMPT = os.getenv("CC_LOG_LEVEL_PROMPT", "DEBUG")  # DEBUG, INFO, or OFF


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


def create_conversation_coach():
    """
    Create the conversation coaching agent configuration.

    Returns agent metadata for reference.
    """
    return {
        "name": "conversation_coach",
        "model": MODEL_VERSION,
        "prompt_version": PROMPT_VERSION,
        "description": "Analyzes contact center conversations and provides coaching feedback",
    }


class CoachingService:
    """
    Service to run conversation coaching using Gemini.

    Uses the Gemini API directly with structured output for reliable JSON responses.
    """

    def __init__(self, model: Optional[str] = None):
        """Initialize the coaching service."""
        settings = get_settings()
        self.model = model or MODEL_VERSION
        self.prompt_version = PROMPT_VERSION

        # Initialize the Gemini client
        self.client = genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.region,
        )

        # System instruction (policy content added dynamically based on RAG)
        self.instruction = SYSTEM_PROMPT

    def analyze_conversation(
        self,
        input_data: CoachingInput,
        rag_context: Optional[str] = None,
        allow_fallback: bool = False,
    ) -> CoachingOutput:
        """
        Analyze a conversation and return coaching output.

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
        # Format input as text
        prompt_text = input_data.to_prompt_text()

        # Build policy section - require RAG context unless fallback is explicitly allowed
        if rag_context:
            policy_section = RAG_CONTEXT_TEMPLATE.format(context=rag_context)
            citations_section = CITATIONS_INSTRUCTION
            logger.info(f"Using RAG context ({len(rag_context)} chars)")
        elif allow_fallback:
            logger.warning(
                "RAG context not available, using embedded policy fallback "
                f"(conversation={input_data.conversation_id})"
            )
            policy_section = EMBEDDED_POLICY
            citations_section = ""
        else:
            raise ValueError(
                f"RAG context is required for coaching. "
                f"Set allow_fallback=True to use embedded policy, "
                f"or configure RAG_DATA_STORE_ID environment variable. "
                f"(conversation={input_data.conversation_id})"
            )

        # Create the full prompt
        full_prompt = f"""
{self.instruction}

{policy_section}

{citations_section}

---

# CONVERSATION TO ANALYZE

{prompt_text}

---

# YOUR TASK

Analyze this conversation and provide coaching feedback. Return your analysis as a JSON object matching the required schema.

Key requirements:
1. Provide scores for all 6 dimensions (1-10 scale)
2. Calculate overall_score as weighted average: (empathy*0.25 + compliance*0.25 + resolution*0.2 + professionalism*0.1 + de_escalation*0.1 + efficiency*0.1)
3. Provide at least 3 dimension assessments with evidence
4. Include at least 1 coaching point
5. Identify the key moment (most notable turn)
6. Classify the call type (hardship, complaint, payment, dispute, inquiry, etc.)
{"7. Include citations for any policy documents referenced" if rag_context else ""}
"""

        # Generate request ID for correlation
        request_id = str(uuid.uuid4())[:8]
        prompt_hash = _get_prompt_hash(full_prompt)
        estimated_tokens = _estimate_tokens(full_prompt)
        start_time = time.time()

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
            f"[{request_id}] Coaching request: conversation={input_data.conversation_id} "
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

        # Call Gemini with structured output
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CoachingOutput,
                    temperature=0.2,  # Lower temperature for more consistent analysis
                ),
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[{request_id}] Gemini API error: {e} "
                f"latency_ms={latency_ms:.0f} conversation={input_data.conversation_id}"
            )
            raise

        latency_ms = (time.time() - start_time) * 1000
        response_length = len(response.text) if response.text else 0
        estimated_output_tokens = _estimate_tokens(response.text) if response.text else 0

        # Log response metrics
        logger.info(
            f"[{request_id}] Coaching response: latency_ms={latency_ms:.0f} "
            f"response_chars={response_length} est_output_tokens={estimated_output_tokens} "
            f"conversation={input_data.conversation_id}"
        )

        # Parse response
        try:
            result_json = json.loads(response.text)
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
            logger.debug(f"[{request_id}] Full response JSON:\n{response.text}")

            return coaching_output
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                f"[{request_id}] Failed to parse coaching output: {e} "
                f"conversation={input_data.conversation_id}"
            )
            logger.debug(f"[{request_id}] Raw response: {response.text}")
            raise ValueError(f"Invalid coaching output from model: {e}")

    def get_metadata(self) -> dict:
        """Return version info for tracking."""
        return {
            "model_version": self.model,
            "prompt_version": self.prompt_version,
            "agent_name": "conversation_coach",
        }
