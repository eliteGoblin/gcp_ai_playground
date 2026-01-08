#!/usr/bin/env python3
"""
Dump per-component outputs for diagnostic purposes.

Shows what each stage of the pipeline produces for a single conversation.
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

from google.cloud import bigquery

from cc_coach.config import get_settings
from cc_coach.rag.config import RAGConfig
from cc_coach.rag.retriever import RAGRetriever
from cc_coach.rag.topic_extractor import TopicExtractor
from cc_coach.schemas.coaching_input import CoachingInput, CallMetadata, CIFlags, Turn, PhraseMatch
from cc_coach.agents.conversation_coach import (
    create_conversation_coach_agent,
    get_last_rag_context,
    get_last_full_instruction,
    EMBEDDED_POLICY,
)
from cc_coach.prompts.coach_system_prompt import SYSTEM_PROMPT

# Use one of the test conversations
CONVERSATION_ID = "a1b2c3d4-toxic-agent-test-0001"  # Toxic agent - interesting case

OUTPUT_DIR = Path(__file__).parent.parent / "verification" / "per_component"


def dump_json(data: dict, filename: str, title: str):
    """Save data to JSON file with header."""
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w") as f:
        f.write(f"# {title}\n")
        f.write(f"# Conversation: {CONVERSATION_ID}\n")
        f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write("# " + "=" * 70 + "\n\n")
        json.dump(data, f, indent=2, default=str)
    print(f"  -> Saved: {filepath.name}")


def dump_text(content: str, filename: str, title: str):
    """Save text content to file with header."""
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w") as f:
        f.write(f"# {title}\n")
        f.write(f"# Conversation: {CONVERSATION_ID}\n")
        f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write("# " + "=" * 70 + "\n\n")
        f.write(content)
    print(f"  -> Saved: {filepath.name}")


def main():
    print(f"\n{'='*70}")
    print(f"PER-COMPONENT DIAGNOSTIC DUMP")
    print(f"Conversation: {CONVERSATION_ID}")
    print(f"{'='*70}\n")

    settings = get_settings()
    bq_client = bigquery.Client(project=settings.project_id)

    # =========================================================================
    # STAGE 1: Raw CI Enrichment Data (from BigQuery)
    # =========================================================================
    print("\n[1/7] Fetching CI Enrichment Data from BigQuery...")

    table_id = f"{settings.project_id}.{settings.bq_dataset}.ci_enrichment"
    query = f"""
        SELECT *
        FROM `{table_id}`
        WHERE conversation_id = @conversation_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("conversation_id", "STRING", CONVERSATION_ID)
        ]
    )
    results = list(bq_client.query(query, job_config=job_config))
    ci_data = dict(results[0]) if results else {}

    dump_json(ci_data, "01_ci_enrichment_raw.json", "CI Enrichment - Raw BigQuery Data")

    # Extract key fields for readability
    ci_summary = {
        "conversation_id": ci_data.get("conversation_id"),
        "ci_summary_text": ci_data.get("ci_summary_text"),
        "customer_sentiment_score": ci_data.get("customer_sentiment_score"),
        "turn_count": ci_data.get("turn_count"),
        "duration_sec": ci_data.get("duration_sec"),
        "ci_flags": ci_data.get("ci_flags"),
        "labels": ci_data.get("labels"),
    }
    dump_json(ci_summary, "01b_ci_summary.json", "CI Enrichment - Key Summary Fields")

    # =========================================================================
    # STAGE 2: Phrase Matches (from CI data)
    # =========================================================================
    print("\n[2/7] Extracting Phrase Matches...")

    phrase_matches = ci_data.get("phrase_matches", [])
    dump_json({"phrase_matches": phrase_matches}, "02_phrase_matches.json", "Phrase Matcher Results")

    # =========================================================================
    # STAGE 3: Conversation Registry Data
    # =========================================================================
    print("\n[3/7] Fetching Registry Data from BigQuery...")

    registry_table = f"{settings.project_id}.{settings.bq_dataset}.conversation_registry"
    registry_query = f"""
        SELECT *
        FROM `{registry_table}`
        WHERE conversation_id = @conversation_id
    """
    registry_results = list(bq_client.query(registry_query, job_config=job_config))
    registry_data = dict(registry_results[0]) if registry_results else {}

    dump_json(registry_data, "03_registry_data.json", "Conversation Registry Data")

    # =========================================================================
    # STAGE 4: Parsed Transcript (Turns)
    # =========================================================================
    print("\n[4/7] Parsing Transcript into Turns...")

    transcript = ci_data.get("transcript", "")
    turns = []
    lines = transcript.strip().split("\n") if transcript else []

    for i, line in enumerate(lines):
        if ": " in line:
            speaker_part, text = line.split(": ", 1)
            speaker_part = speaker_part.strip().upper()
            if "AGENT" in speaker_part:
                speaker = "AGENT"
            elif "CUSTOMER" in speaker_part:
                speaker = "CUSTOMER"
            else:
                continue
            turns.append({
                "index": i + 1,
                "speaker": speaker,
                "text": text.strip()[:200],  # Truncate for readability
            })

    dump_json({
        "turn_count": len(turns),
        "turns": turns
    }, "04_parsed_transcript.json", "Parsed Transcript (Turns)")

    # Also save raw transcript
    dump_text(transcript, "04b_raw_transcript.txt", "Raw Transcript Text")

    # =========================================================================
    # STAGE 5: CoachingInput (Model Input Preparation)
    # =========================================================================
    print("\n[5/7] Building CoachingInput...")

    # Build CI flags
    ci_flags_list = ci_data.get("ci_flags", []) or []
    flags_str = str(ci_flags_list).lower()
    ci_flags = {
        "has_compliance_violations": "compliance_violations" in flags_str,
        "missing_required_disclosures": "required_disclosures" in flags_str,
        "no_empathy_shown": "no_empathy" in flags_str,
        "customer_escalated": "escalation_triggers" in flags_str,
    }

    # Build metadata
    labels = ci_data.get("labels", {})
    if isinstance(labels, str):
        labels = json.loads(labels) if labels else {}

    metadata = {
        "agent_id": labels.get("agent_id", "UNKNOWN"),
        "business_line": labels.get("business_line", "COLLECTIONS"),
        "direction": labels.get("direction", "OUTBOUND"),
        "queue": labels.get("queue"),
        "call_outcome": labels.get("call_outcome"),
        "duration_seconds": ci_data.get("duration_sec"),
    }

    coaching_input = {
        "conversation_id": CONVERSATION_ID,
        "turn_count": len(turns),
        "metadata": metadata,
        "ci_flags": ci_flags,
        "customer_sentiment_score": ci_data.get("customer_sentiment_score"),
        "ci_summary": ci_data.get("ci_summary_text"),
        "phrase_match_count": len(phrase_matches),
    }

    dump_json(coaching_input, "05_coaching_input.json", "CoachingInput (Model Input Metadata)")

    # =========================================================================
    # STAGE 6: RAG Context / Topic Extraction
    # =========================================================================
    print("\n[6/7] Attempting RAG Retrieval...")

    rag_config = RAGConfig.from_env()
    rag_errors = rag_config.validate()

    rag_output = {
        "rag_config_valid": len(rag_errors) == 0,
        "rag_config_errors": rag_errors,
        "data_store_id": rag_config.data_store_id,
        "search_app_id": rag_config.search_app_id,
    }

    if not rag_errors:
        try:
            topic_extractor = TopicExtractor()
            topics = topic_extractor.extract_topics(
                ci_enrichment=ci_data,
                transcript=[{"text": t["text"], "speaker": t["speaker"]} for t in turns],
                metadata=registry_data,
            )
            rag_output["extracted_topics"] = topics

            retriever = RAGRetriever(rag_config)
            business_line = labels.get("business_line")
            context, docs = retriever.get_context_for_coaching(
                conversation_topics=topics,
                conversation_id=CONVERSATION_ID,
                business_line=business_line,
            )

            rag_output["docs_retrieved"] = len(docs)
            rag_output["retrieved_docs"] = [
                {"doc_id": d.doc_id, "title": d.title, "relevance_score": d.relevance_score}
                for d in docs
            ]
            rag_output["rag_context"] = context if context else "[No context returned - RAG empty]"

        except Exception as e:
            rag_output["rag_error"] = str(e)

    dump_json(rag_output, "06_rag_retrieval.json", "RAG Retrieval Results")

    # =========================================================================
    # STAGE 7: Full Model Instruction (System Prompt + Policy)
    # =========================================================================
    print("\n[7/7] Building Full Model Instruction...")

    # Show what the embedded fallback policy contains
    dump_text(EMBEDDED_POLICY, "07a_embedded_policy_fallback.txt", "Embedded Policy (Fallback Mode)")

    # Show the full system prompt
    dump_text(SYSTEM_PROMPT, "07b_system_prompt.txt", "System Prompt (Base)")

    # Show combined instruction (what actually gets sent to model)
    # This would be: SYSTEM_PROMPT + policy_section + citations_section + task instructions
    full_instruction_preview = f"""{SYSTEM_PROMPT}

{EMBEDDED_POLICY}



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
"""

    dump_text(full_instruction_preview, "07c_full_instruction_fallback.txt", "Full Model Instruction (With Fallback Policy)")

    # =========================================================================
    # STAGE 8: Previous Coaching Output (if exists)
    # =========================================================================
    print("\n[8/8] Fetching Previous Coaching Output...")

    coach_table = f"{settings.project_id}.{settings.bq_dataset}.coach_analysis"
    coach_query = f"""
        SELECT *
        FROM `{coach_table}`
        WHERE conversation_id = @conversation_id
        ORDER BY analyzed_at DESC
        LIMIT 1
    """
    coach_results = list(bq_client.query(coach_query, job_config=job_config))
    if coach_results:
        coach_output = dict(coach_results[0])
        dump_json(coach_output, "08_coaching_output.json", "Coaching Output (From BQ)")

        # Extract key scores for summary
        score_summary = {
            "overall_score": coach_output.get("overall_score"),
            "empathy_score": coach_output.get("empathy_score"),
            "compliance_score": coach_output.get("compliance_score"),
            "resolution_score": coach_output.get("resolution_score"),
            "professionalism_score": coach_output.get("professionalism_score"),
            "de_escalation_score": coach_output.get("de_escalation_score"),
            "efficiency_score": coach_output.get("efficiency_score"),
            "call_type": coach_output.get("call_type"),
            "coaching_summary": coach_output.get("coaching_summary"),
            "coaching_points": coach_output.get("coaching_points"),
            "strengths": coach_output.get("strengths"),
            "critical_issues": coach_output.get("critical_issues"),
        }
        dump_json(score_summary, "08b_coaching_scores_summary.json", "Coaching Scores Summary")
    else:
        print("  -> No previous coaching output found")

    # =========================================================================
    # Summary
    # =========================================================================
    print(f"\n{'='*70}")
    print(f"DUMP COMPLETE")
    print(f"{'='*70}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"\nFiles created:")
    for f in sorted(OUTPUT_DIR.glob("*.json")) + sorted(OUTPUT_DIR.glob("*.txt")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
