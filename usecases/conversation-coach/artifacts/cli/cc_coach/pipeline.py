"""
Pipeline module - Discrete steps for conversation processing.

Each function is designed to be:
1. Idempotent - safe to retry
2. Single-purpose - one step at a time
3. Reusable - can be called from CLI or Cloud Run/Functions

Pipeline Flow:
    Step 1: register_file() - Register transcription/metadata files in BQ
    Step 2: ingest_to_ci() - Send to CCAI Insights (when both files exist)
    Step 3: run_ci_analysis() - Trigger CI analysis
    Step 4: export_ci_to_bq() - Export CI results to BigQuery
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import storage

from cc_coach.config import Settings, get_settings
from cc_coach.models.conversation import Conversation, ConversationMetadata, Transcription
from cc_coach.models.registry import ConversationRegistry, RegistryStatus
from cc_coach.services.bigquery import BigQueryService
from cc_coach.services.insights import InsightsService
from cc_coach.services.phrase_matcher import PhraseMatcherService

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Conversation Coach Pipeline.

    Provides discrete steps for processing conversations through the pipeline.
    """

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize pipeline with services."""
        self.settings = settings or get_settings()
        self._bq: Optional[BigQueryService] = None
        self._insights: Optional[InsightsService] = None
        self._phrase_matcher: Optional[PhraseMatcherService] = None
        self._storage: Optional[storage.Client] = None

    @property
    def bq(self) -> BigQueryService:
        """Lazy-load BigQuery service."""
        if self._bq is None:
            self._bq = BigQueryService(self.settings)
        return self._bq

    @property
    def insights(self) -> InsightsService:
        """Lazy-load Insights service."""
        if self._insights is None:
            self._insights = InsightsService(self.settings)
        return self._insights

    @property
    def phrase_matcher(self) -> PhraseMatcherService:
        """Lazy-load Phrase Matcher service."""
        if self._phrase_matcher is None:
            self._phrase_matcher = PhraseMatcherService(self.settings)
        return self._phrase_matcher

    @property
    def storage_client(self) -> storage.Client:
        """Lazy-load Storage client."""
        if self._storage is None:
            self._storage = storage.Client(project=self.settings.project_id)
        return self._storage

    # =========================================================================
    # Step 1: Register file in BigQuery registry
    # =========================================================================

    def register_file(
        self,
        gcs_uri: str,
        file_type: str,  # "transcription" or "metadata"
    ) -> dict[str, Any]:
        """
        Register a file (transcription or metadata) in the conversation registry.

        This is the entry point triggered when a new file lands in GCS.
        It creates/updates the registry entry for the conversation.

        Args:
            gcs_uri: GCS URI like gs://bucket/date/uuid/transcription.json
            file_type: Either "transcription" or "metadata"

        Returns:
            Dict with conversation_id, status, ready_for_ci flag
        """
        # Parse GCS URI to extract conversation_id
        # Format: gs://bucket/date/uuid/filename.json
        parts = gcs_uri.replace("gs://", "").split("/")
        bucket_name = parts[0]
        conversation_id = parts[-2]  # UUID is second-to-last part

        logger.info(f"Registering {file_type} for conversation {conversation_id}")

        # Check if registry entry exists
        registry = self.bq.get_registry(conversation_id)

        if registry is None:
            # Create new registry entry
            registry = ConversationRegistry(
                conversation_id=conversation_id,
                status=RegistryStatus.NEW,
            )

        # Update registry based on file type
        if file_type == "transcription":
            registry.transcript_uri_raw = gcs_uri
            registry.has_transcript = True
        elif file_type == "metadata":
            registry.metadata_uri_raw = gcs_uri
            registry.has_metadata = True
        else:
            raise ValueError(f"Unknown file_type: {file_type}")

        registry.updated_at = datetime.now(timezone.utc)

        # Upsert to BigQuery
        self.bq.upsert_registry(registry)

        # Check if ready for CI (both files present)
        ready_for_ci = registry.has_transcript and registry.has_metadata

        result = {
            "conversation_id": conversation_id,
            "file_type": file_type,
            "gcs_uri": gcs_uri,
            "has_transcript": registry.has_transcript,
            "has_metadata": registry.has_metadata,
            "ready_for_ci": ready_for_ci,
            "status": registry.status.value,
        }

        logger.info(f"Registered: {result}")
        return result

    def register_conversation_folder(
        self,
        bucket: str,
        prefix: str,  # e.g., "2025-12-28/uuid"
    ) -> dict[str, Any]:
        """
        Register all files in a conversation folder.

        Args:
            bucket: GCS bucket name
            prefix: Path prefix like "2025-12-28/uuid"

        Returns:
            Dict with conversation_id, files found, ready_for_ci flag
        """
        conversation_id = prefix.split("/")[-1]

        # List files in folder
        bucket_obj = self.storage_client.bucket(bucket)
        blobs = list(bucket_obj.list_blobs(prefix=prefix))

        files_found = []
        for blob in blobs:
            if blob.name.endswith("transcription.json"):
                gcs_uri = f"gs://{bucket}/{blob.name}"
                self.register_file(gcs_uri, "transcription")
                files_found.append("transcription")
            elif blob.name.endswith("metadata.json"):
                gcs_uri = f"gs://{bucket}/{blob.name}"
                self.register_file(gcs_uri, "metadata")
                files_found.append("metadata")

        # Get final registry state
        registry = self.bq.get_registry(conversation_id)

        return {
            "conversation_id": conversation_id,
            "files_found": files_found,
            "ready_for_ci": registry.has_transcript and registry.has_metadata if registry else False,
            "status": registry.status.value if registry else None,
        }

    # =========================================================================
    # Step 2: Ingest to CCAI Insights
    # =========================================================================

    def ingest_to_ci(
        self,
        conversation_id: str,
        skip_if_exists: bool = True,
    ) -> dict[str, Any]:
        """
        Ingest a conversation to CCAI Insights.

        Prerequisites:
        - Conversation must be registered in BQ with status NEW
        - Both transcription and metadata files must exist

        Args:
            conversation_id: UUID of the conversation
            skip_if_exists: Skip if already in CI (default True)

        Returns:
            Dict with ci_conversation_name and status
        """
        # Get registry entry
        registry = self.bq.get_registry(conversation_id)

        if registry is None:
            raise ValueError(f"Conversation {conversation_id} not found in registry")

        # Check prerequisites
        if not registry.has_transcript or not registry.has_metadata:
            raise ValueError(
                f"Conversation {conversation_id} missing files: "
                f"transcript={registry.has_transcript}, metadata={registry.has_metadata}"
            )

        # Skip if already ingested
        if skip_if_exists and registry.ci_conversation_name:
            logger.info(f"Conversation {conversation_id} already in CI: {registry.ci_conversation_name}")
            return {
                "conversation_id": conversation_id,
                "ci_conversation_name": registry.ci_conversation_name,
                "status": "already_exists",
                "skipped": True,
            }

        # Load transcription and metadata from GCS
        conversation = self._load_conversation_from_gcs(registry)

        # Create conversation in CCAI Insights
        ci_conv = self.insights.create_conversation(
            conversation,
            conversation_id=conversation_id,
        )

        # Update registry
        registry.ci_conversation_name = ci_conv.name
        registry.status = RegistryStatus.INGESTED
        registry.ingested_at = datetime.now(timezone.utc)
        registry.updated_at = datetime.now(timezone.utc)

        self.bq.upsert_registry(registry)

        result = {
            "conversation_id": conversation_id,
            "ci_conversation_name": ci_conv.name,
            "status": "ingested",
            "skipped": False,
        }

        logger.info(f"Ingested to CI: {result}")
        return result

    # =========================================================================
    # Step 3: Run CI Analysis
    # =========================================================================

    def run_ci_analysis(
        self,
        conversation_id: str,
        skip_if_analyzed: bool = True,
        use_phrase_matchers: bool = True,
    ) -> dict[str, Any]:
        """
        Trigger CI analysis for a conversation.

        Prerequisites:
        - Conversation must be ingested to CI (status INGESTED)

        Args:
            conversation_id: UUID of the conversation
            skip_if_analyzed: Skip if already analyzed (default True)
            use_phrase_matchers: Use configured phrase matchers (default True)

        Returns:
            Dict with analysis_name and status
        """
        # Get registry entry
        registry = self.bq.get_registry(conversation_id)

        if registry is None:
            raise ValueError(f"Conversation {conversation_id} not found in registry")

        if not registry.ci_conversation_name:
            raise ValueError(f"Conversation {conversation_id} not yet ingested to CI")

        # Skip if already analyzed
        if skip_if_analyzed and registry.ci_analysis_id:
            logger.info(f"Conversation {conversation_id} already analyzed: {registry.ci_analysis_id}")
            return {
                "conversation_id": conversation_id,
                "analysis_name": registry.ci_analysis_id,
                "status": "already_analyzed",
                "skipped": True,
            }

        # Get phrase matcher names if enabled
        phrase_matcher_names = None
        if use_phrase_matchers:
            phrase_matcher_names = self.phrase_matcher.get_matcher_names()
            logger.info(f"Using {len(phrase_matcher_names)} phrase matchers")

        # Trigger analysis with phrase matchers
        analysis = self.insights.create_analysis(
            registry.ci_conversation_name,
            enable_summarization=True,
            enable_phrase_matchers=use_phrase_matchers,
            phrase_matcher_names=phrase_matcher_names,
        )

        # Update registry
        registry.ci_analysis_id = analysis.name
        registry.updated_at = datetime.now(timezone.utc)

        self.bq.upsert_registry(registry)

        result = {
            "conversation_id": conversation_id,
            "ci_conversation_name": registry.ci_conversation_name,
            "analysis_name": analysis.name,
            "phrase_matchers_used": len(phrase_matcher_names) if phrase_matcher_names else 0,
            "status": "analyzed",
            "skipped": False,
        }

        logger.info(f"CI analysis complete: {result}")
        return result

    # =========================================================================
    # Step 4: Export CI results to BigQuery
    # =========================================================================

    def export_ci_to_bq(
        self,
        conversation_id: str,
    ) -> dict[str, Any]:
        """
        Export CI analysis results to BigQuery ci_enrichment table.

        Combines:
        - CI analysis results (sentiment, entities, topics, summary, phrase matches)
        - Original conversation data (transcript, turn_count, duration, labels)

        Prerequisites:
        - CI analysis must be complete

        Args:
            conversation_id: UUID of the conversation

        Returns:
            Dict with enrichment data and status
        """
        # Get registry entry
        registry = self.bq.get_registry(conversation_id)

        if registry is None:
            raise ValueError(f"Conversation {conversation_id} not found in registry")

        if not registry.ci_analysis_id:
            raise ValueError(f"Conversation {conversation_id} has no CI analysis")

        # Get analysis from CI
        analysis = self.insights.get_analysis(registry.ci_analysis_id)

        if analysis is None:
            raise ValueError(f"Could not fetch analysis {registry.ci_analysis_id}")

        # Get conversation from CI (for summary and runtime annotations)
        ci_conversation = self.insights.get_conversation(registry.ci_conversation_name)

        if ci_conversation is None:
            raise ValueError(f"Could not fetch conversation {registry.ci_conversation_name}")

        # Load original conversation data from GCS
        conversation = self._load_conversation_from_gcs(registry)

        # Get transcript turns for context snippets
        transcript_turns = [
            {"text": turn.text, "speaker": turn.speaker.value}
            for turn in conversation.transcription.turns
        ]

        # Extract FULL CI analysis results (sentiment, entities, topics, summary, phrase matches)
        enrichment_data = self.insights.extract_analysis_results_full(
            analysis,
            ci_conversation,
            transcript_turns,
        )
        enrichment_data["conversation_id"] = conversation_id

        # Add transcript data from original transcription.json
        enrichment_data["transcript"] = conversation.to_transcript_text()
        enrichment_data["turn_count"] = len(conversation.transcription.turns)
        enrichment_data["duration_sec"] = conversation.transcription.duration_sec

        # Add labels from original metadata.json
        enrichment_data["labels"] = json.dumps(conversation.to_ccai_labels())

        # Insert to ci_enrichment table
        self.bq.insert_ci_enrichment(enrichment_data)

        # Update registry status
        registry.status = RegistryStatus.ENRICHED
        registry.enriched_at = datetime.now(timezone.utc)
        registry.updated_at = datetime.now(timezone.utc)

        self.bq.upsert_registry(registry)

        # Count phrase matches and flags for logging
        phrase_match_count = len(enrichment_data.get("phrase_matches", []))
        ci_flag_count = enrichment_data.get("ci_flag_count", 0)

        result = {
            "conversation_id": conversation_id,
            "ci_conversation_name": registry.ci_conversation_name,
            "analysis_name": registry.ci_analysis_id,
            "enrichment_fields": list(enrichment_data.keys()),
            "phrase_match_count": phrase_match_count,
            "ci_flag_count": ci_flag_count,
            "status": "enriched",
        }

        logger.info(f"Exported to BQ: {result}")
        return result

    # =========================================================================
    # Combined Pipeline (for batch processing)
    # =========================================================================

    def process_conversation(
        self,
        conversation_id: str,
        run_analysis: bool = True,
    ) -> dict[str, Any]:
        """
        Run full pipeline for a single conversation.

        This combines all steps for convenience, but each step is idempotent.

        Args:
            conversation_id: UUID of the conversation
            run_analysis: Whether to run CI analysis

        Returns:
            Dict with all pipeline results
        """
        results = {
            "conversation_id": conversation_id,
            "steps": {},
        }

        try:
            # Step 2: Ingest to CI
            ci_result = self.ingest_to_ci(conversation_id)
            results["steps"]["ingest_to_ci"] = ci_result

            if run_analysis and not ci_result.get("skipped"):
                # Step 3: Run analysis
                analysis_result = self.run_ci_analysis(conversation_id)
                results["steps"]["run_ci_analysis"] = analysis_result

                # Step 4: Export to BQ
                export_result = self.export_ci_to_bq(conversation_id)
                results["steps"]["export_ci_to_bq"] = export_result

            results["status"] = "success"

        except Exception as e:
            logger.error(f"Pipeline failed for {conversation_id}: {e}")
            results["status"] = "failed"
            results["error"] = str(e)

            # Update registry with error
            registry = self.bq.get_registry(conversation_id)
            if registry:
                registry.status = RegistryStatus.FAILED
                registry.last_error = str(e)
                registry.retry_count += 1
                registry.updated_at = datetime.now(timezone.utc)
                self.bq.upsert_registry(registry)

        return results

    # =========================================================================
    # Helper methods
    # =========================================================================

    def _load_conversation_from_gcs(
        self,
        registry: ConversationRegistry,
    ) -> Conversation:
        """Load conversation data from GCS URIs in registry."""
        # Load transcription
        trans_data = self._load_json_from_gcs(registry.transcript_uri_raw)
        transcription = Transcription(**trans_data)

        # Load metadata
        meta_data = self._load_json_from_gcs(registry.metadata_uri_raw)
        metadata = ConversationMetadata(**meta_data)

        return Conversation(transcription=transcription, metadata=metadata)

    def _load_json_from_gcs(self, gcs_uri: str) -> dict:
        """Load JSON from GCS URI."""
        # Parse URI
        parts = gcs_uri.replace("gs://", "").split("/", 1)
        bucket_name = parts[0]
        blob_path = parts[1]

        # Download and parse
        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        content = blob.download_as_text()

        return json.loads(content)

    def list_pending_conversations(
        self,
        status: Optional[RegistryStatus] = None,
        limit: int = 100,
    ) -> list[ConversationRegistry]:
        """List conversations pending processing."""
        return self.bq.list_registry(status=status, limit=limit)
