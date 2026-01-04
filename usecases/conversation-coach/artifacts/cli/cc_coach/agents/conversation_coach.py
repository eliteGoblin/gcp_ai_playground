"""
Conversation Coach ADK Agent.

Uses Google ADK to analyze contact center conversations and generate coaching feedback.
"""

import json
import logging
from typing import Optional

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
    ) -> CoachingOutput:
        """
        Analyze a conversation and return coaching output.

        Args:
            input_data: CoachingInput with transcript and metadata
            rag_context: Optional RAG context from knowledge base retrieval

        Returns:
            CoachingOutput with scores, evidence, and coaching points
        """
        # Format input as text
        prompt_text = input_data.to_prompt_text()

        # Build policy section - use RAG context if available, otherwise embedded policy
        if rag_context:
            policy_section = RAG_CONTEXT_TEMPLATE.format(context=rag_context)
            citations_section = CITATIONS_INSTRUCTION
        else:
            policy_section = EMBEDDED_POLICY
            citations_section = ""

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

        logger.info(f"Analyzing conversation {input_data.conversation_id} with {self.model}")

        # Call Gemini with structured output
        response = self.client.models.generate_content(
            model=self.model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CoachingOutput,
                temperature=0.2,  # Lower temperature for more consistent analysis
            ),
        )

        # Parse response
        try:
            result_json = json.loads(response.text)
            return CoachingOutput.model_validate(result_json)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Failed to parse coaching output: {e}")
            logger.debug(f"Raw response: {response.text}")
            raise ValueError(f"Invalid coaching output from model: {e}")

    def get_metadata(self) -> dict:
        """Return version info for tracking."""
        return {
            "model_version": self.model,
            "prompt_version": self.prompt_version,
            "agent_name": "conversation_coach",
        }
