"""Topic extraction for RAG retrieval.

Extracts search topics from conversation data to query the knowledge base.
Topics are derived from:
- CI entities (high salience)
- CI phrase matcher hits
- Business line context
- Transcript keywords (optional)
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional


# Mapping from phrase matcher IDs to RAG topics
PHRASE_MATCHER_TOPIC_MAP = {
    # Prohibited language
    "threat_language": ["prohibited language", "threats", "compliance violations"],
    "prohibited_terms": ["prohibited language", "compliance violations"],
    "legal_threats": ["prohibited language", "legal threats", "compliance"],
    # Hardship
    "hardship_indicators": ["hardship provisions", "hardship triggers"],
    "financial_difficulty": ["hardship provisions", "payment difficulty"],
    # Compliance
    "identity_verification": ["identity verification", "verification procedures"],
    "disclosure_required": ["required disclosures", "compliance"],
    # De-escalation
    "escalation_request": ["escalation procedures", "de-escalation"],
    "supervisor_request": ["escalation procedures"],
    # Positive indicators
    "empathy_phrases": ["empathy techniques", "coaching examples"],
    "resolution_offer": ["resolution strategies", "payment options"],
}

# Business line to topic mapping
BUSINESS_LINE_TOPICS = {
    "COLLECTIONS": ["collections compliance", "debt collection rules"],
    "HARDSHIP": ["hardship provisions", "financial difficulty handling"],
    "CUSTOMER_SERVICE": ["customer service standards", "complaint handling"],
    "SALES": ["sales compliance", "disclosure requirements"],
}

# High-value keywords to look for in transcripts
TRANSCRIPT_KEYWORDS = {
    "legal": ["legal action", "prohibited language", "compliance"],
    "lawyer": ["legal action", "prohibited language"],
    "court": ["legal action", "prohibited language"],
    "sue": ["legal action", "prohibited language", "threats"],
    "hardship": ["hardship provisions", "financial difficulty"],
    "can't pay": ["hardship provisions", "payment difficulty"],
    "lost job": ["hardship provisions", "hardship triggers"],
    "unemployed": ["hardship provisions", "hardship triggers"],
    "medical": ["hardship provisions", "hardship triggers"],
    "complaint": ["complaint handling", "escalation procedures"],
    "supervisor": ["escalation procedures", "de-escalation"],
    "manager": ["escalation procedures", "de-escalation"],
    "ombudsman": ["complaint handling", "external dispute resolution"],
    "afca": ["complaint handling", "external dispute resolution"],
}


@dataclass
class ExtractionResult:
    """Result of topic extraction."""

    topics: list[str] = field(default_factory=list)
    sources: dict[str, list[str]] = field(default_factory=dict)

    def add_topics(self, source: str, topics: list[str]) -> None:
        """Add topics from a source."""
        self.topics.extend(topics)
        if source not in self.sources:
            self.sources[source] = []
        self.sources[source].extend(topics)

    def get_unique_topics(self) -> list[str]:
        """Get deduplicated list of topics."""
        return list(set(self.topics))


class TopicExtractor:
    """Extract topics from conversation data for RAG retrieval."""

    def __init__(
        self,
        min_entity_salience: float = 0.3,
        include_transcript_keywords: bool = True,
        max_topics: int = 10,
    ):
        """Initialize topic extractor.

        Args:
            min_entity_salience: Minimum salience for CI entities to include
            include_transcript_keywords: Whether to scan transcript for keywords
            max_topics: Maximum number of topics to return
        """
        self.min_entity_salience = min_entity_salience
        self.include_transcript_keywords = include_transcript_keywords
        self.max_topics = max_topics

    def extract_topics(
        self,
        ci_enrichment: Optional[dict[str, Any]] = None,
        transcript: Optional[list[dict[str, Any]]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        """Extract search topics from conversation data.

        Args:
            ci_enrichment: CCAI Insights analysis results
            transcript: List of transcript turns
            metadata: Conversation metadata

        Returns:
            List of topic strings for RAG queries
        """
        result = ExtractionResult()

        # Extract from CI entities
        if ci_enrichment:
            self._extract_from_entities(ci_enrichment, result)
            self._extract_from_phrase_matches(ci_enrichment, result)

        # Extract from metadata
        if metadata:
            self._extract_from_metadata(metadata, result)

        # Extract from transcript keywords
        if self.include_transcript_keywords and transcript:
            self._extract_from_transcript(transcript, result)

        # Get unique topics and limit
        unique_topics = result.get_unique_topics()
        return unique_topics[: self.max_topics]

    def _extract_from_entities(
        self, ci_enrichment: dict[str, Any], result: ExtractionResult
    ) -> None:
        """Extract topics from CI entities.

        Handles both dict format (from raw CI API) and list format (from BQ).
        """
        entities = ci_enrichment.get("entities", [])

        # Handle both dict and list formats
        entity_list: list[dict[str, Any]] = []
        if isinstance(entities, dict):
            entity_list = list(entities.values())
        elif isinstance(entities, list):
            entity_list = entities
        else:
            return

        for entity in entity_list:
            salience = entity.get("salience", 0)
            if salience >= self.min_entity_salience:
                # Handle different field names
                display_name = entity.get("displayName", entity.get("name", ""))
                entity_type = entity.get("type", "")

                if display_name:
                    # Use entity display name as a topic
                    result.add_topics("entities", [display_name.lower()])

                    # Map certain entity types to policy topics
                    if entity_type == "ORGANIZATION":
                        result.add_topics("entities", ["organization references"])
                    elif entity_type == "PERSON":
                        result.add_topics("entities", ["identity verification"])

    def _extract_from_phrase_matches(
        self, ci_enrichment: dict[str, Any], result: ExtractionResult
    ) -> None:
        """Extract topics from CI phrase matcher hits."""
        phrase_matches = ci_enrichment.get("phrase_matches", [])

        for match in phrase_matches:
            matcher_id = match.get("phrase_matcher_id", "")
            matcher_name = match.get("display_name", "")

            # Try to map by ID first, then by name
            topics = []

            # Check ID mapping
            for key, mapped_topics in PHRASE_MATCHER_TOPIC_MAP.items():
                if key in matcher_id.lower() or key in matcher_name.lower():
                    topics.extend(mapped_topics)

            if topics:
                result.add_topics("phrase_matches", topics)

    def _extract_from_metadata(
        self, metadata: dict[str, Any], result: ExtractionResult
    ) -> None:
        """Extract topics from conversation metadata."""
        # Business line context
        business_line = metadata.get("business_line", "")
        if business_line and business_line in BUSINESS_LINE_TOPICS:
            result.add_topics("metadata", BUSINESS_LINE_TOPICS[business_line])

        # Queue-specific topics
        queue = metadata.get("queue", "")
        if "hardship" in queue.lower():
            result.add_topics("metadata", ["hardship provisions", "financial difficulty"])
        elif "complaint" in queue.lower():
            result.add_topics("metadata", ["complaint handling", "escalation procedures"])

        # Call outcome hints
        outcome = metadata.get("call_outcome", "")
        if "escalat" in outcome.lower():
            result.add_topics("metadata", ["escalation procedures"])
        elif "hardship" in outcome.lower():
            result.add_topics("metadata", ["hardship provisions"])

    def _extract_from_transcript(
        self, transcript: list[dict[str, Any]], result: ExtractionResult
    ) -> None:
        """Extract topics from transcript keywords."""
        # Combine all transcript text
        full_text = " ".join(
            turn.get("text", "") for turn in transcript
        ).lower()

        # Search for keywords
        for keyword, topics in TRANSCRIPT_KEYWORDS.items():
            if keyword.lower() in full_text:
                result.add_topics("transcript", topics)

    def extract_with_details(
        self,
        ci_enrichment: Optional[dict[str, Any]] = None,
        transcript: Optional[list[dict[str, Any]]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Extract topics with source tracking.

        Same as extract_topics but returns full ExtractionResult
        with source information for debugging/auditing.

        Args:
            ci_enrichment: CCAI Insights analysis results
            transcript: List of transcript turns
            metadata: Conversation metadata

        Returns:
            ExtractionResult with topics and sources
        """
        result = ExtractionResult()

        if ci_enrichment:
            self._extract_from_entities(ci_enrichment, result)
            self._extract_from_phrase_matches(ci_enrichment, result)

        if metadata:
            self._extract_from_metadata(metadata, result)

        if self.include_transcript_keywords and transcript:
            self._extract_from_transcript(transcript, result)

        return result
