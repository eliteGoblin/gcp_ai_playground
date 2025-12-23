"""
Test script to demonstrate all Langfuse features.

This script generates multiple traces with:
- Different characters (for comparison)
- Sessions (grouped conversations)
- Scores (quality metrics)
- Evaluations (LLM-as-judge)
- Spans (custom sub-operations)
- Metadata (custom attributes)

Run this to populate your Langfuse dashboard with sample data.
"""

import os
import time
import json
import random
from datetime import datetime

from storyteller import (
    tell_story,
    add_score,
    create_evaluation_trace,
    langfuse,
    CHARACTER_TONES,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_BASE_URL,
    CallbackHandler
)

# Test questions about famous people (will be reinterpreted as wizards)
TEST_QUESTIONS = [
    "Tell me about Albert Einstein",
    "Who was Leonardo da Vinci?",
    "What made Nikola Tesla famous?",
    "Tell me about Cleopatra",
    "Who is Merlin?",
    "What do you know about the founders of Hogwarts?",
    "Tell me about Shakespeare",
    "Who was Marie Curie?",
]


def run_feature_demo():
    """Run comprehensive demo of all Langfuse features."""
    print("\n" + "="*70)
    print("LANGFUSE FEATURE DEMONSTRATION")
    print("="*70)

    results = []

    # =========================================================================
    # Feature 1: Basic Tracing with Multiple Characters
    # =========================================================================
    print("\n Feature 1: Basic Tracing with Different Characters")
    print("-"*50)

    characters = ["snape", "harry", "hermione"]
    question = "Tell me about Albert Einstein"

    for char in characters:
        print(f"\n  Testing with {char}...")
        result = tell_story(
            question=question,
            character=char,
            user_id="feature_demo_user"
        )
        results.append(result)
        print(f"  Trace ID: {result['trace_id']}")
        # Brief pause to avoid rate limiting
        time.sleep(1)

    # =========================================================================
    # Feature 2: Sessions - Grouped Conversations
    # =========================================================================
    print("\n\n Feature 2: Sessions - Grouped Conversations")
    print("-"*50)
    print("  Creating a multi-turn conversation session...")

    session_id = f"demo_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    conversation = [
        "Who was Merlin?",
        "What were his greatest achievements?",
        "Did he have any rivals?",
    ]

    for i, q in enumerate(conversation):
        print(f"\n  Turn {i+1}: {q[:40]}...")
        result = tell_story(
            question=q,
            character="dumbledore",
            session_id=session_id,  # Same session groups these traces
            user_id="session_demo_user"
        )
        print(f"  Trace ID: {result['trace_id']} (Session: {session_id})")
        time.sleep(1)

    print(f"\n  All 3 traces are grouped under session: {session_id}")

    # =========================================================================
    # Feature 3: Scores - Quality Metrics
    # =========================================================================
    print("\n\n Feature 3: Scores - Quality Metrics")
    print("-"*50)

    # Use the first result for scoring demo
    if results:
        trace_to_score = results[0]
        print(f"  Adding scores to trace: {trace_to_score['trace_id']}")

        # Add multiple score types
        scores_to_add = [
            ("user_satisfaction", 4.5, "Simulated user rating"),
            ("character_authenticity", 4.0, "How well it matches character voice"),
            ("informativeness", 3.5, "Quality of information provided"),
            ("response_quality", 4.2, "Overall response quality"),
        ]

        for name, value, comment in scores_to_add:
            add_score(
                trace_id=trace_to_score['trace_id'],
                name=name,
                value=value,
                comment=comment
            )
            print(f"  Added score: {name} = {value}")

    # =========================================================================
    # Feature 4: LLM-as-Judge Evaluation
    # =========================================================================
    print("\n\n Feature 4: LLM-as-Judge Evaluation")
    print("-"*50)

    if results:
        print("  Running automated evaluation on a response...")
        eval_result = create_evaluation_trace(
            original_response=results[0]["response"],
            question="Tell me about Albert Einstein",
            character="snape",
            session_id=session_id,
            user_id="eval_demo_user"
        )
        print(f"  Evaluation trace: {eval_result['trace_id']}")
        print(f"  Evaluation result: {eval_result['evaluation'][:200]}...")

    # =========================================================================
    # Feature 5: Automatic Span Tracking
    # =========================================================================
    print("\n\n Feature 5: Automatic Span Tracking via @observe decorator")
    print("-"*50)
    print("  The @observe decorator automatically creates spans for:")
    print("    - Function execution time")
    print("    - Input parameters")
    print("    - Return values")
    print("  Check the trace detail view to see nested spans!")

    # =========================================================================
    # Feature 6: Cost & Token Tracking
    # =========================================================================
    print("\n\n Feature 6: Cost & Token Tracking")
    print("-"*50)
    print("  Token and cost tracking happens automatically with LangChain integration!")
    print("  Check your Langfuse dashboard to see:")
    print("    - Input tokens per request")
    print("    - Output tokens per request")
    print("    - Total cost per trace")
    print("    - Cost breakdown by model")

    # =========================================================================
    # Feature 7: Bulk Testing for Dashboard Population
    # =========================================================================
    print("\n\n Feature 7: Generating Additional Traces for Dashboard")
    print("-"*50)

    additional_tests = 3
    print(f"  Generating {additional_tests} more traces with random characters...")

    for i in range(additional_tests):
        char = random.choice(list(CHARACTER_TONES.keys()))
        q = random.choice(TEST_QUESTIONS)

        result = tell_story(
            question=q,
            character=char,
            user_id=f"batch_user_{i}"
        )

        # Add random score
        add_score(
            trace_id=result['trace_id'],
            name="user_satisfaction",
            value=random.uniform(3.0, 5.0),
            comment="Simulated user feedback"
        )

        print(f"  {i+1}/{additional_tests}: {char} - {q[:30]}...")
        time.sleep(1)

    # =========================================================================
    # Flush and Summary
    # =========================================================================
    print("\n\n" + "="*70)
    print("FLUSHING ALL TRACES TO LANGFUSE...")
    langfuse.flush()
    print("All traces sent!")

    print("\n" + "="*70)
    print("DEMO COMPLETE!")
    print("="*70)
    print(f"""
Now open your Langfuse dashboard to explore:

  https://cloud.langfuse.com

What you'll see:

  1. TRACES TAB:
     - All traces with names like "story_snape", "story_harry", etc.
     - Click any trace to see detailed execution flow
     - See latency, tokens, and cost per trace

  2. SESSIONS TAB:
     - Find session: {session_id}
     - See all 3 conversation turns grouped together

  3. SCORES:
     - Filter traces by score values
     - See quality distribution across traces

  4. ANALYTICS:
     - Cost tracking over time
     - Token usage statistics
     - Latency distributions

  5. FILTERS:
     - Filter by tags: "storyteller", "character:snape", etc.
     - Filter by user_id
     - Filter by metadata fields

Project: {LANGFUSE_PUBLIC_KEY[:20]}...
""")


def quick_test():
    """Quick test to verify connection works."""
    print("\n Quick Connection Test")
    print("-"*40)

    try:
        result = tell_story(
            question="Tell me briefly about Merlin the wizard",
            character="snape",
            user_id="quick_test"
        )
        print(f" Response received ({len(result['response'])} chars)")
        print(f" Trace ID: {result['trace_id']}")

        langfuse.flush()
        print(" Trace sent to Langfuse!")
        print(f"\n View at: https://cloud.langfuse.com")

        return True
    except Exception as e:
        print(f" Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        quick_test()
    else:
        run_feature_demo()
