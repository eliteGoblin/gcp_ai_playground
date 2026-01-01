"""
CCAI Insights service for Conversation Coach.

Handles interaction with the Contact Center AI Insights API:
- Creating conversations
- Running analysis
- Retrieving analysis results
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import contact_center_insights_v1 as insights
from google.cloud import storage
from google.protobuf import duration_pb2, timestamp_pb2

from cc_coach.config import Settings, get_settings
from cc_coach.models.conversation import Conversation

logger = logging.getLogger(__name__)


class InsightsService:
    """Service for CCAI Insights operations."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize Insights service."""
        self.settings = settings or get_settings()
        self._client: Optional[insights.ContactCenterInsightsClient] = None
        self._storage: Optional[storage.Client] = None

    @property
    def client(self) -> insights.ContactCenterInsightsClient:
        """Lazy-load Insights client."""
        if self._client is None:
            self._client = insights.ContactCenterInsightsClient()
        return self._client

    @property
    def storage_client(self) -> storage.Client:
        """Lazy-load Storage client."""
        if self._storage is None:
            self._storage = storage.Client(project=self.settings.project_id)
        return self._storage

    @property
    def parent(self) -> str:
        """Get parent resource path."""
        return self.settings.insights_parent

    def create_conversation(
        self,
        conversation: Conversation,
        conversation_id: Optional[str] = None,
        transcript_gcs_uri: Optional[str] = None,
    ) -> insights.Conversation:
        """
        Create a conversation in CCAI Insights.

        Args:
            conversation: Conversation model with transcription and metadata
            conversation_id: Optional ID (uses conversation.conversation_id if not provided)
            transcript_gcs_uri: Optional GCS URI for transcript (will upload if not provided)

        Returns:
            Created CCAI Insights Conversation resource
        """
        conv_id = conversation_id or conversation.conversation_id

        # Upload transcript to GCS in CCAI format if not provided
        if not transcript_gcs_uri:
            transcript_gcs_uri = self._upload_ccai_transcript(conversation, conv_id)

        # Build conversation request with data source
        started_at = conversation.transcription.started_at
        start_time = timestamp_pb2.Timestamp(seconds=int(started_at.timestamp()))

        duration = None
        if conversation.transcription.duration_sec:
            duration = duration_pb2.Duration(seconds=conversation.transcription.duration_sec)

        # Create GCS source
        gcs_source = insights.GcsSource(transcript_uri=transcript_gcs_uri)
        data_source = insights.ConversationDataSource(gcs_source=gcs_source)

        conv = insights.Conversation(
            medium=insights.Conversation.Medium.PHONE_CALL,
            data_source=data_source,
            labels=conversation.to_ccai_labels(),
            language_code=conversation.transcription.language,
            start_time=start_time,
            duration=duration,
            agent_id=conversation.metadata.agent_id,
        )

        # Create the conversation
        request = insights.CreateConversationRequest(
            parent=self.parent,
            conversation=conv,
            conversation_id=conv_id,
        )

        try:
            created = self.client.create_conversation(request=request)
            logger.info(f"Created conversation: {created.name}")
            return created
        except Exception as e:
            logger.error(f"Failed to create conversation {conv_id}: {e}")
            raise

    def _upload_ccai_transcript(
        self,
        conversation: Conversation,
        conversation_id: str,
    ) -> str:
        """
        Upload conversation transcript to GCS in CCAI format.

        CCAI expects JsonConversationInput format with camelCase:
        {
            "entries": [
                {
                    "text": "...",
                    "role": "AGENT" | "CUSTOMER",
                    "userId": "1",
                    "startTimestampUsec": "1234567890"
                }
            ]
        }

        Returns:
            GCS URI of the uploaded transcript
        """
        bucket_name = self.settings.gcs_bucket_dev
        blob_path = f"ccai-transcripts/{conversation_id}.json"

        # Convert to CCAI format with camelCase
        raw_entries = conversation.to_ccai_entries()
        ccai_entries = []
        for entry in raw_entries:
            # Map role to CCAI expected values
            role = entry["role"]
            if role == "HUMAN_AGENT":
                role = "AGENT"
            elif role == "END_USER":
                role = "CUSTOMER"

            ccai_entries.append({
                "text": entry["text"],
                "role": role,
                "userId": str(entry["user_id"]),
                "startTimestampUsec": str(entry["start_timestamp_usec"]),
            })

        ccai_data = {"entries": ccai_entries}

        # Upload to GCS
        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(ccai_data, indent=2),
            content_type="application/json",
        )

        gcs_uri = f"gs://{bucket_name}/{blob_path}"
        logger.info(f"Uploaded CCAI transcript to {gcs_uri}")
        return gcs_uri

    def get_conversation(self, conversation_name: str) -> Optional[insights.Conversation]:
        """
        Get a conversation by its resource name.

        Args:
            conversation_name: Full resource name like
                projects/{project}/locations/{location}/conversations/{id}

        Returns:
            Conversation resource or None if not found
        """
        try:
            request = insights.GetConversationRequest(name=conversation_name)
            return self.client.get_conversation(request=request)
        except Exception as e:
            logger.warning(f"Failed to get conversation {conversation_name}: {e}")
            return None

    def create_analysis(
        self,
        conversation_name: str,
        enable_summarization: bool = True,
        enable_phrase_matchers: bool = True,
        phrase_matcher_names: Optional[list[str]] = None,
    ) -> insights.Analysis:
        """
        Trigger analysis on a conversation.

        Args:
            conversation_name: Full resource name of the conversation
            enable_summarization: Whether to generate AI summary (default True)
            enable_phrase_matchers: Whether to run phrase matchers (default True)
            phrase_matcher_names: Specific phrase matcher resource names to use

        Returns:
            Analysis result
        """
        # Build annotator selector with all features enabled
        annotator_selector = insights.AnnotatorSelector(
            run_sentiment_annotator=True,
            run_entity_annotator=True,
            run_intent_annotator=True,
        )

        # Enable summarization
        if enable_summarization:
            annotator_selector.run_summarization_annotator = True
            annotator_selector.summarization_config = (
                insights.AnnotatorSelector.SummarizationConfig(
                    summarization_model=insights.AnnotatorSelector.SummarizationConfig.SummarizationModel.BASELINE_MODEL_V2_0
                )
            )

        # Enable phrase matchers
        if enable_phrase_matchers:
            annotator_selector.run_phrase_matcher_annotator = True
            if phrase_matcher_names:
                annotator_selector.phrase_matchers = phrase_matcher_names

        request = insights.CreateAnalysisRequest(
            parent=conversation_name,
            analysis=insights.Analysis(
                annotator_selector=annotator_selector,
            ),
        )

        operation = self.client.create_analysis(request=request)
        logger.info(f"Started analysis for {conversation_name}")

        # Wait for completion (for MVP, blocking is fine)
        result = operation.result()
        logger.info(f"Analysis complete: {result.name}")
        return result

    def get_analysis(self, analysis_name: str) -> Optional[insights.Analysis]:
        """Get analysis by name."""
        try:
            request = insights.GetAnalysisRequest(name=analysis_name)
            return self.client.get_analysis(request=request)
        except Exception as e:
            logger.warning(f"Failed to get analysis {analysis_name}: {e}")
            return None

    def list_conversations(
        self,
        filter_str: Optional[str] = None,
        page_size: int = 100,
    ) -> list[insights.Conversation]:
        """
        List conversations with optional filter.

        Args:
            filter_str: Filter string (e.g., 'labels.business_line="COLLECTIONS"')
            page_size: Number of results per page

        Returns:
            List of conversations
        """
        request = insights.ListConversationsRequest(
            parent=self.parent,
            page_size=page_size,
        )

        if filter_str:
            request.filter = filter_str

        conversations = []
        for conv in self.client.list_conversations(request=request):
            conversations.append(conv)

        return conversations

    def ingest_conversation(
        self,
        conversation: Conversation,
        run_analysis: bool = True,
    ) -> dict[str, Any]:
        """
        Complete ingestion workflow: create conversation and optionally run analysis.

        Args:
            conversation: Conversation to ingest
            run_analysis: Whether to run analysis after creation

        Returns:
            Dict with conversation_name and analysis_name (if run)
        """
        result = {
            "conversation_id": conversation.conversation_id,
            "conversation_name": None,
            "analysis_name": None,
            "status": "created",
        }

        # Create conversation
        created = self.create_conversation(conversation)
        result["conversation_name"] = created.name

        # Optionally run analysis
        if run_analysis:
            analysis = self.create_analysis(created.name)
            result["analysis_name"] = analysis.name
            result["status"] = "analyzed"

        return result

    def extract_analysis_results(self, analysis: insights.Analysis) -> dict[str, Any]:
        """
        Extract analysis results into a structured dict for BigQuery.

        Args:
            analysis: CCAI Insights Analysis resource

        Returns:
            Dict suitable for ci_enrichment table (CI analysis fields only)
        """
        result = {
            "ci_conversation_name": analysis.name.rsplit("/analyses/", 1)[0],
            "analysis_completed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Get call analysis metadata from analysis result
        call_meta = analysis.analysis_result.call_analysis_metadata

        # Extract overall sentiment from sentiments (channel 1 = customer)
        # Note: CI only analyzes customer sentiment, not agent
        if call_meta.sentiments:
            for sentiment in call_meta.sentiments:
                if sentiment.channel_tag == 1:  # Customer channel
                    result["customer_sentiment_score"] = sentiment.sentiment_data.score
                    result["customer_sentiment_magnitude"] = sentiment.sentiment_data.magnitude
                    break

        # Extract per-turn sentiment from annotations
        # These are customer turns only (channel 1), agent turns have no sentiment
        per_turn_sentiments = []
        if call_meta.annotations:
            for ann in call_meta.annotations:
                if hasattr(ann, "sentiment_data") and ann.sentiment_data.score != 0:
                    per_turn_sentiments.append(
                        {
                            "turn_index": ann.annotation_start_boundary.transcript_index,
                            "score": ann.sentiment_data.score,
                            "magnitude": ann.sentiment_data.magnitude,
                        }
                    )
        # Sort by turn index
        per_turn_sentiments.sort(key=lambda x: x["turn_index"])
        result["per_turn_sentiments"] = per_turn_sentiments

        # Extract entities (as list of dicts for REPEATED RECORD in BQ)
        entities = []
        if call_meta.entities:
            for entity_id, entity in call_meta.entities.items():
                entities.append(
                    {
                        "type": str(entity.type_) if entity.type_ else None,
                        "name": entity.display_name,
                        "salience": entity.salience,
                    }
                )
        result["entities"] = entities

        # Extract topics/intents (as list of strings for REPEATED STRING in BQ)
        topics = []
        if call_meta.intents:
            for intent_id, intent in call_meta.intents.items():
                topics.append(intent.display_name)
        result["topics"] = topics

        return result

    def extract_analysis_results_full(
        self,
        analysis: insights.Analysis,
        conversation: insights.Conversation,
        transcript_turns: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """
        Extract full analysis results including summary and phrase matches.

        Args:
            analysis: CCAI Insights Analysis resource
            conversation: CCAI Conversation with runtime annotations
            transcript_turns: Original transcript turns for context snippets

        Returns:
            Dict suitable for ci_enrichment table with all CI fields
        """
        # Start with basic extraction
        result = self.extract_analysis_results(analysis)

        # Extract summary from conversation (set after analysis)
        if conversation.latest_summary:
            summary = conversation.latest_summary
            result["ci_summary_text"] = summary.text if summary.text else None

            # Extract resolution from summary text_sections or text
            if summary.text_sections and "resolution" in summary.text_sections:
                result["ci_summary_resolution"] = summary.text_sections["resolution"]
            elif summary.text:
                # Fallback: Check if summary contains resolution indicator
                text_lower = summary.text.lower()
                if "resolution: y" in text_lower or "resolution\ny" in text_lower:
                    result["ci_summary_resolution"] = "Y"
                elif "resolution: n" in text_lower or "resolution\nn" in text_lower:
                    result["ci_summary_resolution"] = "N"
                else:
                    result["ci_summary_resolution"] = None

        # Extract phrase matches from analysis annotations (NOT runtime_annotations)
        phrase_matches = self._extract_phrase_matches_from_analysis(
            analysis, transcript_turns or []
        )
        result["phrase_matches"] = phrase_matches

        # Generate CI flags based on phrase matches
        ci_flags = self._generate_ci_flags(phrase_matches)
        result["ci_flags"] = ci_flags
        result["ci_flag_count"] = len(ci_flags)

        return result

    def _extract_phrase_matches(
        self,
        conversation: insights.Conversation,
        transcript_turns: list[dict],
    ) -> list[dict]:
        """
        Extract phrase match data from CI conversation runtime annotations.

        Args:
            conversation: CI Conversation with runtime annotations
            transcript_turns: Original transcript turns for context snippets

        Returns:
            List of matcher results for BQ insertion
        """
        matcher_results = {}

        # Get phrase match annotations from runtime annotations
        for annotation in conversation.runtime_annotations:
            if not annotation.phrase_match_data:
                continue

            pm_data = annotation.phrase_match_data
            matcher_name = pm_data.phrase_matcher
            # Extract display name from the phrase matcher data
            display_name = pm_data.display_name

            # Use display name as key since we might not have matcher_id
            if display_name not in matcher_results:
                matcher_results[display_name] = {
                    "matcher_id": matcher_name.split("/")[-1] if "/" in matcher_name else display_name.lower().replace(" ", "_"),
                    "display_name": display_name,
                    "match_count": 0,
                    "matches": [],
                }

            # Get turn info from annotation boundaries
            turn_index = 0
            if annotation.annotation_start_boundary:
                turn_index = annotation.annotation_start_boundary.transcript_index

            # Determine speaker (channel 1 = customer, channel 2 = agent)
            speaker = "CUSTOMER" if annotation.channel_tag == 1 else "AGENT"

            # Get text snippet from original transcript
            text_snippet = ""
            if transcript_turns and turn_index < len(transcript_turns):
                text_snippet = transcript_turns[turn_index].get("text", "")[:200]

            # The matched phrase/query
            matched_phrase = ""
            if pm_data.phrase_matcher_group:
                matched_phrase = pm_data.phrase_matcher_group

            matcher_results[display_name]["matches"].append(
                {
                    "phrase": matched_phrase,
                    "turn_index": turn_index,
                    "speaker": speaker,
                    "text_snippet": text_snippet,
                }
            )
            matcher_results[display_name]["match_count"] += 1

        return list(matcher_results.values())

    def _extract_phrase_matches_from_analysis(
        self,
        analysis: insights.Analysis,
        transcript_turns: list[dict],
    ) -> list[dict]:
        """
        Extract phrase match data from CI analysis annotations.

        Args:
            analysis: CI Analysis with call_analysis_metadata
            transcript_turns: Original transcript turns for context snippets

        Returns:
            List of matcher results for BQ insertion
        """
        call_meta = analysis.analysis_result.call_analysis_metadata
        matcher_results = {}

        # Process annotations with phrase_match_data
        for annotation in call_meta.annotations:
            if not annotation.phrase_match_data:
                continue

            pm_data = annotation.phrase_match_data
            if not pm_data.phrase_matcher:
                continue

            display_name = pm_data.display_name
            matcher_name = pm_data.phrase_matcher

            # Use display name as key
            if display_name not in matcher_results:
                # Extract matcher_id from the resource name
                matcher_id = matcher_name.split("/")[-1].split("@")[0] if "/" in matcher_name else display_name.lower().replace(" ", "_")
                matcher_results[display_name] = {
                    "matcher_id": matcher_id,
                    "display_name": display_name,
                    "match_count": 0,
                    "matches": [],
                }

            # Get turn info from annotation boundaries
            turn_index = 0
            if annotation.annotation_start_boundary:
                turn_index = annotation.annotation_start_boundary.transcript_index

            # Determine speaker (channel 1 = customer, channel 2 = agent)
            speaker = "CUSTOMER" if annotation.channel_tag == 1 else "AGENT"

            # Get text snippet from original transcript
            text_snippet = ""
            if transcript_turns and turn_index < len(transcript_turns):
                text_snippet = transcript_turns[turn_index].get("text", "")[:200]

            matcher_results[display_name]["matches"].append(
                {
                    "phrase": display_name,  # Use display name as phrase indicator
                    "turn_index": turn_index,
                    "speaker": speaker,
                    "text_snippet": text_snippet,
                }
            )
            matcher_results[display_name]["match_count"] += 1

        return list(matcher_results.values())

    def _generate_ci_flags(self, phrase_matches: list[dict]) -> list[str]:
        """
        Generate CI flags based on phrase match results.

        Args:
            phrase_matches: List of matcher results

        Returns:
            List of flag strings for quick filtering
        """
        flags = []

        for result in phrase_matches:
            if result["match_count"] == 0:
                continue

            display_name = result["display_name"].lower()

            # Compliance violations from agent are red flags
            if "compliance" in display_name:
                agent_matches = [
                    m for m in result["matches"] if m["speaker"] == "AGENT"
                ]
                if agent_matches:
                    flags.append("AGENT_COMPLIANCE_VIOLATION")

            # Escalation triggers from customer
            elif "escalation" in display_name:
                customer_matches = [
                    m for m in result["matches"] if m["speaker"] == "CUSTOMER"
                ]
                if customer_matches:
                    flags.append("CUSTOMER_ESCALATION")

            # Vulnerability indicators
            elif "vulnerability" in display_name:
                flags.append("VULNERABILITY_DETECTED")

        return list(set(flags))  # Deduplicate

    def delete_conversation(self, conversation_name: str) -> bool:
        """Delete a conversation."""
        try:
            request = insights.DeleteConversationRequest(name=conversation_name)
            self.client.delete_conversation(request=request)
            logger.info(f"Deleted conversation: {conversation_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete conversation {conversation_name}: {e}")
            return False
