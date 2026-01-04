"""
Coaching orchestration service.

Coordinates data fetching, RAG retrieval, analysis, and storage for conversation coaching.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from google.cloud import bigquery

from cc_coach.agents.conversation_coach import CoachingService
from cc_coach.config import Settings, get_settings
from cc_coach.rag.config import RAGConfig
from cc_coach.rag.retriever import RAGRetriever, RetrievedDocument
from cc_coach.rag.topic_extractor import TopicExtractor
from cc_coach.schemas.coaching_input import (
    CallMetadata,
    CIFlags,
    CoachingInput,
    PhraseMatch,
    Turn,
)
from cc_coach.schemas.coaching_output import CoachingOutput
from cc_coach.services.bigquery import BigQueryService

logger = logging.getLogger(__name__)


class CoachingOrchestrator:
    """Orchestrates the coaching workflow with optional RAG integration."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        model: Optional[str] = None,
        enable_rag: bool = True,
        allow_fallback: bool = False,
    ):
        """Initialize the orchestrator.

        Args:
            settings: Application settings
            model: Optional model override
            enable_rag: Whether to enable RAG retrieval (default: True)
            allow_fallback: If True, use embedded policy when RAG fails.
                          If False (default), raise error when RAG context is missing.
        """
        self.settings = settings or get_settings()
        self.bq = BigQueryService(self.settings)
        self.coach = CoachingService(model=model)
        self.allow_fallback = allow_fallback

        # Initialize RAG components if enabled and configured
        self.rag_enabled = False
        self.rag_retriever: Optional[RAGRetriever] = None
        self.topic_extractor: Optional[TopicExtractor] = None
        self.rag_config_errors: list[str] = []

        if enable_rag:
            rag_config = RAGConfig.from_env()
            self.rag_config_errors = rag_config.validate()
            if not self.rag_config_errors:
                self.rag_retriever = RAGRetriever(rag_config)
                self.topic_extractor = TopicExtractor()
                self.rag_enabled = True
                logger.info("RAG integration enabled")
            else:
                logger.warning(f"RAG not enabled: {self.rag_config_errors}")
                if not allow_fallback:
                    raise ValueError(
                        f"RAG is required but not configured: {self.rag_config_errors}. "
                        f"Set allow_fallback=True to use embedded policy."
                    )

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

        # 3. Get RAG context if enabled
        rag_context: Optional[str] = None
        retrieved_docs: list[RetrievedDocument] = []

        if self.rag_enabled and self.topic_extractor and self.rag_retriever:
            # Merge metadata from registry and ci_data labels
            merged_metadata = {}
            if registry_data:
                merged_metadata.update(registry_data)
            # CI data labels contain business_line, queue, etc. - important for topic extraction
            labels = ci_data.get("labels", {})
            if isinstance(labels, str):
                labels = json.loads(labels) if labels else {}
            if isinstance(labels, dict):
                merged_metadata.update(labels)

            rag_context, retrieved_docs = self._get_rag_context(
                conversation_id=conversation_id,
                ci_data=ci_data,
                transcript=input_data.turns,
                metadata=merged_metadata,
            )
            if rag_context:
                logger.info(f"Retrieved {len(retrieved_docs)} RAG documents for {conversation_id}")

        # 4. Run coach with RAG context
        output = self.coach.analyze_conversation(
            input_data,
            rag_context=rag_context,
            allow_fallback=self.allow_fallback,
        )

        # 5. Add citations from retrieved docs
        if retrieved_docs:
            output.citations = [doc.to_citation() for doc in retrieved_docs]
            output.rag_context_used = True

        # 6. Store result
        self._store_coaching_result(
            conversation_id, output, registry_data, ci_data, retrieved_docs
        )

        # 7. Update registry status
        self._update_registry_status(conversation_id, "COACHED")

        return output

    def _get_rag_context(
        self,
        conversation_id: str,
        ci_data: dict,
        transcript: list[Turn],
        metadata: Optional[dict],
    ) -> tuple[Optional[str], list[RetrievedDocument]]:
        """Extract topics and retrieve RAG context.

        Args:
            conversation_id: Conversation ID for audit logging
            ci_data: CI enrichment data
            transcript: Parsed transcript turns
            metadata: Conversation metadata

        Returns:
            Tuple of (context string, list of retrieved documents)
        """
        if not self.topic_extractor or not self.rag_retriever:
            return None, []

        try:
            # Extract topics from conversation
            topics = self.topic_extractor.extract_topics(
                ci_enrichment=ci_data,
                transcript=[{"text": t.text, "speaker": t.speaker} for t in transcript],
                metadata=metadata,
            )

            if not topics:
                logger.debug(f"No topics extracted for {conversation_id}")
                return None, []

            logger.debug(f"Extracted topics for {conversation_id}: {topics}")

            # Get business line from metadata
            business_line = None
            if metadata:
                labels = metadata.get("labels", {})
                if isinstance(labels, str):
                    labels = json.loads(labels) if labels else {}
                business_line = labels.get("business_line")

            # Retrieve relevant documents
            context, docs = self.rag_retriever.get_context_for_coaching(
                conversation_topics=topics,
                conversation_id=conversation_id,
                business_line=business_line,
            )

            return context if context else None, docs

        except Exception as e:
            logger.warning(f"RAG retrieval failed for {conversation_id}: {e}")
            return None, []

    def _fetch_ci_enrichment(self, conversation_id: str) -> Optional[dict]:
        """Fetch CI enrichment data from BigQuery."""
        table_id = f"{self.settings.project_id}.{self.settings.bq_dataset}.ci_enrichment"
        query = f"""
            SELECT *
            FROM `{table_id}`
            WHERE conversation_id = @conversation_id
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("conversation_id", "STRING", conversation_id)
            ]
        )

        results = list(self.bq.client.query(query, job_config=job_config))
        return dict(results[0]) if results else None

    def _fetch_registry(self, conversation_id: str) -> Optional[dict]:
        """Fetch conversation registry data."""
        table_id = f"{self.settings.project_id}.{self.settings.bq_dataset}.conversation_registry"
        query = f"""
            SELECT *
            FROM `{table_id}`
            WHERE conversation_id = @conversation_id
        """

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
        registry_data: Optional[dict],
    ) -> CoachingInput:
        """Build CoachingInput from BQ data."""
        # Parse transcript into turns
        transcript = ci_data.get("transcript", "")
        turns = self._parse_transcript(transcript)

        # Build CI flags from phrase matches
        ci_flags_list = ci_data.get("ci_flags", []) or []
        ci_flags = self._build_ci_flags(ci_flags_list)
        phrase_matches = self._parse_phrase_matches(ci_data.get("phrase_matches", []))

        # Build metadata from labels
        labels = ci_data.get("labels", {})
        if isinstance(labels, str):
            labels = json.loads(labels) if labels else {}

        metadata = CallMetadata(
            agent_id=labels.get("agent_id", "UNKNOWN"),
            business_line=labels.get("business_line", "COLLECTIONS"),
            direction=labels.get("direction", "OUTBOUND"),
            queue=labels.get("queue"),
            call_outcome=labels.get("call_outcome"),
            duration_seconds=ci_data.get("duration_sec"),
        )

        return CoachingInput(
            conversation_id=conversation_id,
            turns=turns,
            turn_count=len(turns),
            metadata=metadata,
            customer_sentiment_score=ci_data.get("customer_sentiment_score"),
            customer_sentiment_start=None,
            customer_sentiment_end=None,
            ci_flags=ci_flags,
            phrase_matches=phrase_matches,
            ci_summary=ci_data.get("ci_summary_text"),
        )

    def _parse_transcript(self, transcript: str) -> list[Turn]:
        """Parse transcript string into Turn objects."""
        turns = []
        lines = transcript.strip().split("\n") if transcript else []

        for i, line in enumerate(lines):
            if ": " in line:
                speaker_part, text = line.split(": ", 1)
                speaker_part = speaker_part.strip().upper()

                # Handle formats: "Speaker.AGENT", "AGENT", "Agent"
                if "AGENT" in speaker_part:
                    speaker = "AGENT"
                elif "CUSTOMER" in speaker_part:
                    speaker = "CUSTOMER"
                else:
                    continue

                turns.append(
                    Turn(
                        index=i + 1,
                        speaker=speaker,
                        text=text.strip(),
                        sentiment=None,
                    )
                )

        return turns

    def _build_ci_flags(self, flags: list) -> CIFlags:
        """Build CIFlags from list of flag strings."""
        flags_str = str(flags).lower()
        return CIFlags(
            has_compliance_violations="compliance_violations" in flags_str,
            missing_required_disclosures="required_disclosures" in flags_str,
            no_empathy_shown="no_empathy" in flags_str or (
                "empathy_indicators" not in flags_str and len(flags) > 0
            ),
            customer_escalated="escalation_triggers" in flags_str,
        )

    def _parse_phrase_matches(self, matches: list) -> list[PhraseMatch]:
        """Parse phrase matches from BQ format."""
        result = []
        for match in matches or []:
            if isinstance(match, dict):
                for m in match.get("matches", []):
                    result.append(
                        PhraseMatch(
                            matcher_name=match.get("display_name", ""),
                            phrase=m.get("phrase", ""),
                            turn_index=m.get("turn_index", 0),
                            speaker=m.get("speaker", "UNKNOWN"),
                        )
                    )
        return result

    def _store_coaching_result(
        self,
        conversation_id: str,
        output: CoachingOutput,
        registry_data: Optional[dict],
        ci_data: Optional[dict],
        retrieved_docs: Optional[list[RetrievedDocument]] = None,
    ) -> None:
        """Store coaching result in BigQuery.

        Args:
            conversation_id: Conversation ID
            output: Coaching output from agent
            registry_data: Registry metadata
            ci_data: CI enrichment data
            retrieved_docs: Optional list of RAG-retrieved documents
        """
        meta = self.coach.get_metadata()

        # Get labels from ci_data
        labels = {}
        if ci_data:
            labels = ci_data.get("labels", {})
            if isinstance(labels, str):
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
            "issue_types": output.issue_types,
            "critical_issues": output.critical_issues,
            "issue_count": output.issue_count,
            "compliance_breach_count": output.compliance_breach_count,

            # Flags
            "resolution_achieved": output.resolution_achieved,
            "escalation_required": output.escalation_required,
            "customer_started_negative": output.customer_started_negative,

            # Coaching
            "coaching_summary": output.coaching_summary,
            # BQ schema expects coaching_points as list of strings, not records
            "coaching_points": [
                f"[P{cp.priority}] {cp.title}: {cp.description}"
                for cp in output.coaching_points
            ],
            "strengths": output.strengths,

            # Context
            "situation_summary": output.situation_summary,
            "behavior_summary": output.behavior_summary,
            "call_type": output.call_type,
            "example_type": output.example_type,

            # Key moment (BQ schema doesn't have is_positive, exclude it)
            "key_moment": {
                "turn_index": output.key_moment.turn_index,
                "quote": output.key_moment.quote,
                "why_notable": output.key_moment.why_notable,
            },

            # Assessments (detailed) - map to BQ schema format
            "assessments": [
                {
                    "dimension": a.dimension,
                    "score": a.score,
                    "issue_types": a.issue_types,
                    "evidence": [
                        {
                            "turn_index": e.turn_index,
                            "speaker": e.speaker,
                            "quote": e.quote,
                            "issue_type": e.issue_type,
                            "severity": e.severity,
                            # BQ schema doesn't have explanation, omit it
                        }
                        for e in a.evidence
                    ],
                    "coaching_point": a.coaching_point,
                }
                for a in output.assessments
            ],

            # CI data
            "customer_sentiment": ci_data.get("customer_sentiment_score") if ci_data else None,
            "ci_flags": ci_data.get("ci_flags", []) if ci_data else [],
            "turn_count": ci_data.get("turn_count") if ci_data else None,
            "duration_sec": ci_data.get("duration_sec") if ci_data else None,

            # Metadata
            "model_version": meta["model_version"],
            "prompt_version": meta["prompt_version"],

            # RAG citations
            "rag_context_used": output.rag_context_used,
            "citations": output.citations,
        }

        # Insert into coach_analysis table
        table_id = f"{self.settings.project_id}.{self.settings.bq_dataset}.coach_analysis"
        errors = self.bq.client.insert_rows_json(table_id, [row])

        if errors:
            logger.error(f"Failed to insert coaching result: {errors}")
            raise RuntimeError(f"Failed to insert coaching result: {errors}")

        logger.info(f"Stored coaching result for {conversation_id}")

    def _update_registry_status(self, conversation_id: str, status: str) -> None:
        """Update conversation status in registry."""
        table_id = f"{self.settings.project_id}.{self.settings.bq_dataset}.conversation_registry"
        query = f"""
            UPDATE `{table_id}`
            SET status = @status,
                coached_at = CURRENT_TIMESTAMP(),
                updated_at = CURRENT_TIMESTAMP()
            WHERE conversation_id = @conversation_id
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("status", "STRING", status),
                bigquery.ScalarQueryParameter("conversation_id", "STRING", conversation_id),
            ]
        )

        self.bq.client.query(query, job_config=job_config).result()
        logger.debug(f"Updated registry status to {status} for {conversation_id}")

    def get_pending_conversations(self, limit: int = 50) -> list[str]:
        """Get conversation IDs pending coaching."""
        table_id = f"{self.settings.project_id}.{self.settings.bq_dataset}.conversation_registry"
        query = f"""
            SELECT conversation_id
            FROM `{table_id}`
            WHERE status = 'ENRICHED'
            ORDER BY enriched_at ASC
            LIMIT {limit}
        """

        results = self.bq.client.query(query).result()
        return [row["conversation_id"] for row in results]

    def get_coaching_result(self, conversation_id: str) -> Optional[dict]:
        """Get existing coaching result for a conversation."""
        table_id = f"{self.settings.project_id}.{self.settings.bq_dataset}.coach_analysis"
        query = f"""
            SELECT *
            FROM `{table_id}`
            WHERE conversation_id = @conversation_id
            ORDER BY analyzed_at DESC
            LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("conversation_id", "STRING", conversation_id)
            ]
        )

        results = list(self.bq.client.query(query, job_config=job_config))
        return dict(results[0]) if results else None
