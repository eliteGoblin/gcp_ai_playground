"""
Famous Person Story Teller - Langfuse Demo App

This app demonstrates Langfuse's core observability features:
1. Traces - Full execution flow tracking
2. Generations - LLM call tracking with input/output
3. Cost Tracking - Token usage and cost monitoring
4. Sessions - Group related conversations
5. Scores - Quality evaluation of responses
6. Metadata - Custom data attached to traces
7. Spans - Track sub-operations within a trace
"""

import os
import uuid
from datetime import datetime
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langfuse import Langfuse, observe
from langfuse.langchain import CallbackHandler

# Configuration
LANGFUSE_SECRET_KEY = "sk-lf-8af0f1aa-9a5f-45af-96e8-c70b381fefcc"
LANGFUSE_PUBLIC_KEY = "pk-lf-265642b1-07da-44b6-bde2-5201df7bb77a"
LANGFUSE_BASE_URL = "https://cloud.langfuse.com"

# Set environment variables for Langfuse (required for the new SDK)
os.environ["LANGFUSE_SECRET_KEY"] = LANGFUSE_SECRET_KEY
os.environ["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_PUBLIC_KEY
os.environ["LANGFUSE_HOST"] = LANGFUSE_BASE_URL

# OpenAI API Key (from environment)
OPENAI_API_KEY = os.environ.get("GPT_API_KEY") or os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Please set GPT_API_KEY or OPENAI_API_KEY environment variable")

os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# Initialize Langfuse client for direct API access (scores, etc.)
langfuse = Langfuse()


# Character Tone Definitions
CHARACTER_TONES = {
    "snape": {
        "name": "Professor Severus Snape",
        "world": "wizarding",
        "system_prompt": """You are Professor Severus Snape from Harry Potter.
You speak in a cold, drawling, sarcastic manner. You are dismissive and condescending,
often expressing disappointment. Use phrases like "Obviously...", "Clearly you haven't
been paying attention...", "How... disappointing.", "I expected better, even from you."
You pause dramatically and speak with barely concealed contempt.
When telling stories about famous witches and wizards, you do so reluctantly,
as if the questioner's ignorance is an inconvenience.
Occasionally reference potions or your expertise. Never be warm or encouraging.""",
    },
    "harry": {
        "name": "Harry Potter",
        "world": "wizarding",
        "system_prompt": """You are Harry Potter, the Boy Who Lived.
You speak in a friendly, humble, and sometimes awkward manner. You're brave but modest.
Use phrases like "Blimey!", "Brilliant!", "I reckon...", "To be honest..."
You often relate stories to your own experiences at Hogwarts or your adventures.
You're enthusiastic about magic and the wizarding world.
When telling stories about famous witches and wizards, share them like you're
talking to a friend, sometimes expressing surprise at what you've learned.""",
    },
    "dumbledore": {
        "name": "Albus Dumbledore",
        "world": "wizarding",
        "system_prompt": """You are Albus Dumbledore, Headmaster of Hogwarts.
You speak with wisdom, warmth, and a twinkle in your eye. You use metaphors and
gentle guidance. Use phrases like "Ah, my dear child...", "It does not do to dwell...",
"Happiness can be found even in the darkest of times...", "Curiously..."
You often pause thoughtfully and share profound insights.
When telling stories, you weave in life lessons and moral wisdom.
Occasionally offer a lemon drop. Be mysterious yet kind.""",
    },
    "hermione": {
        "name": "Hermione Granger",
        "world": "wizarding",
        "system_prompt": """You are Hermione Granger, the brightest witch of your age.
You speak with precision, enthusiasm for knowledge, and sometimes exasperation at
others' lack of study. Use phrases like "Honestly!", "I read about this in...",
"It's clearly stated in...", "Don't you ever read?"
You cite sources (often books) and provide thorough, well-researched answers.
When telling stories, you include detailed historical context and facts.
You're eager to share knowledge but can be a bit bossy about it.""",
    },
    "hagrid": {
        "name": "Rubeus Hagrid",
        "world": "wizarding",
        "system_prompt": """You are Rubeus Hagrid, Keeper of Keys and Grounds at Hogwarts.
You speak with a thick accent, warmth, and enthusiasm. You sometimes say too much.
Use phrases like "Blimey!", "I shouldn'ta said that...", "Yeh know...",
"Great man, Dumbledore...", drop your 'g's and 'h's sometimes.
You have a soft spot for magical creatures and often mention them.
When telling stories, you share them like gossip, excited and perhaps revealing
more than you should. You're kind-hearted and sometimes emotional.""",
    },
}


def get_llm(temperature: float = 0.7) -> ChatOpenAI:
    """Create ChatOpenAI instance configured for GPT-4o."""
    return ChatOpenAI(
        model="gpt-4o",
        temperature=temperature,
        api_key=OPENAI_API_KEY
    )


@observe(name="tell_story")
def tell_story(
    question: str,
    character: str = "snape",
    session_id: Optional[str] = None,
    user_id: str = "demo_user"
) -> dict:
    """
    Tell a story about a famous person in the selected character's style.

    The @observe decorator automatically:
    - Creates a trace for this function
    - Tracks execution time (latency)
    - Captures input/output
    - Enables nested spans for child operations
    """
    # Validate character
    if character not in CHARACTER_TONES:
        character = "snape"

    char_config = CHARACTER_TONES[character]

    # Generate session ID if not provided (for conversation continuity)
    if not session_id:
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    # Update the current trace with metadata
    # This enriches the trace created by @observe
    langfuse.update_current_trace(
        name=f"story_{character}",
        session_id=session_id,
        user_id=user_id,
        metadata={
            "character": character,
            "character_name": char_config["name"],
            "world_type": char_config["world"],
            "question_length": len(question),
            "timestamp": datetime.now().isoformat()
        },
        tags=["storyteller", f"character:{character}", "demo"]
    )

    # Get trace ID for later scoring
    trace_id = langfuse.get_current_trace_id()

    # Create LLM with callback handler for automatic tracking
    # The CallbackHandler will track tokens, cost, latency
    handler = CallbackHandler()
    llm = get_llm(temperature=0.8)

    # Build the prompt
    system_prompt = char_config["system_prompt"]

    if char_config["world"] == "wizarding":
        context = """
You are telling stories about famous witches and wizards from the magical world.
This includes historical figures like Merlin, Morgana, the Hogwarts founders,
and characters from the Harry Potter universe.
When asked about real-world famous people, creatively reinterpret them as
magical figures (e.g., Einstein becomes a famous arithmancer, Shakespeare
was actually a wizard playwright, etc.)."""
    else:
        context = "You are telling stories about famous historical figures."

    full_system = f"{system_prompt}\n\n{context}"

    # Create messages
    messages = [
        SystemMessage(content=full_system),
        HumanMessage(content=question)
    ]

    # Invoke LLM with Langfuse tracking
    response = llm.invoke(messages, config={"callbacks": [handler]})

    return {
        "response": response.content,
        "character": char_config["name"],
        "trace_id": trace_id,
        "session_id": session_id
    }


def add_score(
    trace_id: str,
    name: str,
    value: float,
    comment: Optional[str] = None
):
    """
    Add a score to a trace for evaluation tracking.

    Langfuse Feature: Scores
    - Track quality metrics on traces
    - Can be used for:
      - User feedback (thumbs up/down)
      - Automated quality scores
      - Human evaluation
      - LLM-as-judge scores
    """
    langfuse.create_score(
        trace_id=trace_id,
        name=name,
        value=value,
        comment=comment
    )


@observe(name="evaluation")
def create_evaluation_trace(
    original_response: str,
    question: str,
    character: str,
    session_id: str,
    user_id: str
) -> dict:
    """
    Demonstrate LLM-as-a-judge evaluation.

    This creates a separate trace for the evaluation,
    showing how to track meta-level quality assessment.
    """
    # Update trace with evaluation metadata
    langfuse.update_current_trace(
        session_id=session_id,
        user_id=user_id,
        metadata={"type": "evaluation", "original_question": question},
        tags=["evaluation", "llm-as-judge"]
    )

    trace_id = langfuse.get_current_trace_id()

    handler = CallbackHandler()
    llm = get_llm(temperature=0.0)  # Low temperature for consistent evaluation

    eval_prompt = f"""Evaluate the following response for quality.

Question: {question}
Character Style: {character}
Response: {original_response}

Rate on a scale of 1-10 for:
1. Character authenticity (does it match the character's speaking style?)
2. Informativeness (is the story interesting and informative?)
3. Creativity (is the magical reinterpretation creative?)

Provide a brief JSON response:
{{"authenticity": <1-10>, "informativeness": <1-10>, "creativity": <1-10>, "overall": <1-10>, "brief_comment": "<one sentence>"}}
"""

    messages = [
        SystemMessage(content="You are a quality evaluator. Respond only with valid JSON."),
        HumanMessage(content=eval_prompt)
    ]

    response = llm.invoke(messages, config={"callbacks": [handler]})

    return {
        "evaluation": response.content,
        "trace_id": trace_id
    }


def interactive_session():
    """Run an interactive storytelling session."""
    print("\n" + "="*60)
    print("  MAGICAL STORY TELLER - Langfuse Demo")
    print("="*60)
    print("\nAvailable Characters:")
    for key, char in CHARACTER_TONES.items():
        print(f"  - {key}: {char['name']}")
    print("\nCommands:")
    print("  - Type a question about a famous person")
    print("  - 'switch <character>' to change narrator")
    print("  - 'eval' to evaluate the last response")
    print("  - 'quit' to exit")
    print("="*60)

    session_id = f"interactive_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    user_id = "interactive_user"
    current_character = "snape"
    last_result = None

    print(f"\n[Current narrator: {CHARACTER_TONES[current_character]['name']}]")

    while True:
        try:
            user_input = input("\n Ask about someone: ").strip()

            if not user_input:
                continue

            if user_input.lower() == 'quit':
                print("\n Goodbye! Check your Langfuse dashboard for traces.")
                break

            if user_input.lower().startswith('switch '):
                new_char = user_input.split(' ', 1)[1].lower()
                if new_char in CHARACTER_TONES:
                    current_character = new_char
                    print(f"[Switched to: {CHARACTER_TONES[current_character]['name']}]")
                else:
                    print(f"[Unknown character. Available: {', '.join(CHARACTER_TONES.keys())}]")
                continue

            if user_input.lower() == 'eval' and last_result:
                print("\n[Running evaluation...]")
                eval_result = create_evaluation_trace(
                    original_response=last_result["response"],
                    question=last_result.get("question", ""),
                    character=current_character,
                    session_id=session_id,
                    user_id=user_id
                )
                print(f"\n Evaluation: {eval_result['evaluation']}")
                print(f"[Evaluation trace: {eval_result['trace_id']}]")
                continue

            # Tell the story
            print(f"\n[{CHARACTER_TONES[current_character]['name']} speaks...]")
            result = tell_story(
                question=user_input,
                character=current_character,
                session_id=session_id,
                user_id=user_id
            )
            result["question"] = user_input
            last_result = result

            print(f"\n{result['response']}")
            print(f"\n[Trace ID: {result['trace_id']}]")

            # Add a user satisfaction score prompt
            satisfaction = input("\nRate response (1-5, or skip): ").strip()
            if satisfaction.isdigit() and 1 <= int(satisfaction) <= 5:
                add_score(
                    trace_id=result["trace_id"],
                    name="user_satisfaction",
                    value=float(satisfaction),
                    comment="User rating from interactive session"
                )
                print("[Score recorded!]")

        except KeyboardInterrupt:
            print("\n\n Goodbye!")
            break
        except Exception as e:
            print(f"\n[Error: {e}]")

    # Flush all pending traces
    langfuse.flush()


if __name__ == "__main__":
    interactive_session()
