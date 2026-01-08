#!/usr/bin/env python3
"""
Batch analysis script for all dev conversations.

Runs coaching on all conversations and saves detailed outputs including RAG context
to the verification folder.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from cc_coach.agents.conversation_coach import get_last_rag_context, get_last_full_instruction
from cc_coach.services.coaching import CoachingOrchestrator


# All 9 dev conversations
DEV_CONVERSATIONS = [
    "2b6f5c61-9e3a-4e47-8b8c-3f0c5f6c2d0e",
    "3f2d9e4b-1a74-4f35-8bb2-9d8f8df0b6a7",
    "6a4a8f17-6c6f-4a2a-9b1b-5c0d8e2e42c9",
    "9c8f3c2a-4fd2-4e7b-9b41-2fb2b4e6a2d1",
    "a1b2c3d4-toxic-agent-test-0001",
    "a7c3d1e8-5b2f-4a9d-8c6e-1f4b7a3d9e5c",
    "b8d4e2f9-6c3a-4b8e-9d7f-2a5c8b4e0f6d",
    "c9e5f3a0-7d4b-4c9f-0e8a-3b6d9c5f1a7e",
    "e5f6g7h8-exemplary-agent-test-0001",
]


def run_batch_analysis():
    """Run analysis on all dev conversations and save outputs."""
    # Output paths
    verification_dir = Path(__file__).parent.parent / "verification"
    verification_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Summary file
    summary_path = verification_dir / "batch_analysis_summary.txt"

    # Initialize orchestrator with fallback enabled (RAG still indexing)
    print("Initializing orchestrator with allow_fallback=True...")
    orchestrator = CoachingOrchestrator(enable_rag=True, allow_fallback=True)

    results = []
    errors = []

    print(f"\n{'='*80}")
    print(f"BATCH ANALYSIS - {len(DEV_CONVERSATIONS)} conversations")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*80}\n")

    for i, conv_id in enumerate(DEV_CONVERSATIONS, 1):
        short_id = conv_id[:8]
        print(f"\n[{i}/{len(DEV_CONVERSATIONS)}] Analyzing {conv_id}...")

        try:
            # Run coaching
            output = orchestrator.generate_coaching(conv_id)

            # Capture RAG context and instruction
            rag_context = get_last_rag_context()
            full_instruction = get_last_full_instruction()

            # Save individual output
            output_path = verification_dir / f"coaching_{short_id}.json"
            output_data = {
                "conversation_id": conv_id,
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "output": output.model_dump(),
                "rag_context": rag_context,
                "metrics": {
                    "input_tokens": orchestrator.coach.last_input_tokens,
                    "output_tokens": orchestrator.coach.last_output_tokens,
                    "latency_ms": orchestrator.coach.last_latency_ms,
                    "cost_usd": orchestrator.coach.last_cost_usd,
                },
            }
            with open(output_path, "w") as f:
                json.dump(output_data, f, indent=2)

            # Save full instruction to separate file (large)
            instruction_path = verification_dir / f"instruction_{short_id}.txt"
            with open(instruction_path, "w") as f:
                f.write(f"# Full Instruction for {conv_id}\n")
                f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
                f.write(f"# RAG Context Used: {bool(rag_context and 'FALLBACK' not in rag_context)}\n")
                f.write(f"{'='*80}\n\n")
                f.write(full_instruction or "[No instruction captured]")

            result = {
                "conversation_id": conv_id,
                "overall_score": output.overall_score,
                "call_type": output.call_type,
                "coaching_points": len(output.coaching_points),
                "rag_context_used": output.rag_context_used,
                "rag_fallback": rag_context and "FALLBACK" in rag_context,
                "cost_usd": orchestrator.coach.last_cost_usd,
                "latency_ms": orchestrator.coach.last_latency_ms,
            }
            results.append(result)

            print(f"    ✓ Score: {output.overall_score:.1f} | Type: {output.call_type} | Points: {len(output.coaching_points)}")
            print(f"    ✓ RAG: {'Fallback' if result['rag_fallback'] else 'Active'} | Cost: ${orchestrator.coach.last_cost_usd:.4f}")

        except Exception as e:
            print(f"    ✗ ERROR: {e}")
            errors.append({
                "conversation_id": conv_id,
                "error": str(e),
                "error_type": type(e).__name__,
            })

    # Write summary
    with open(summary_path, "w") as f:
        f.write(f"BATCH ANALYSIS SUMMARY\n")
        f.write(f"{'='*80}\n")
        f.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Total Conversations: {len(DEV_CONVERSATIONS)}\n")
        f.write(f"Successful: {len(results)}\n")
        f.write(f"Failed: {len(errors)}\n\n")

        if results:
            f.write(f"\nSUCCESSFUL ANALYSES\n")
            f.write(f"{'-'*80}\n")
            total_cost = 0
            for r in results:
                f.write(f"\n{r['conversation_id'][:36]}\n")
                f.write(f"  Score: {r['overall_score']:.1f} | Type: {r['call_type']}\n")
                f.write(f"  Coaching Points: {r['coaching_points']}\n")
                f.write(f"  RAG: {'Fallback' if r['rag_fallback'] else 'Active'}\n")
                f.write(f"  Cost: ${r['cost_usd']:.6f} | Latency: {r['latency_ms']}ms\n")
                total_cost += r['cost_usd']

            avg_score = sum(r['overall_score'] for r in results) / len(results)
            f.write(f"\n\nAGGREGATE METRICS\n")
            f.write(f"{'-'*80}\n")
            f.write(f"Average Score: {avg_score:.2f}\n")
            f.write(f"Total Cost: ${total_cost:.6f}\n")
            f.write(f"RAG Fallback Rate: {sum(1 for r in results if r['rag_fallback'])/len(results)*100:.1f}%\n")

        if errors:
            f.write(f"\n\nFAILED ANALYSES\n")
            f.write(f"{'-'*80}\n")
            for e in errors:
                f.write(f"\n{e['conversation_id']}\n")
                f.write(f"  Error: {e['error_type']}: {e['error']}\n")

    # Print final summary
    print(f"\n{'='*80}")
    print(f"BATCH ANALYSIS COMPLETE")
    print(f"{'='*80}")
    print(f"Successful: {len(results)}/{len(DEV_CONVERSATIONS)}")
    print(f"Failed: {len(errors)}/{len(DEV_CONVERSATIONS)}")
    if results:
        avg_score = sum(r['overall_score'] for r in results) / len(results)
        total_cost = sum(r['cost_usd'] for r in results)
        print(f"Average Score: {avg_score:.2f}")
        print(f"Total Cost: ${total_cost:.6f}")
    print(f"\nOutputs saved to: {verification_dir}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    run_batch_analysis()
