"""Service for managing CI Phrase Matchers."""

import logging
from typing import Optional

from google.cloud import contact_center_insights_v1 as insights

from cc_coach.config import Settings, get_settings

logger = logging.getLogger(__name__)


# Phrase Matcher Configurations
PHRASE_MATCHERS = {
    "compliance_violations": {
        "display_name": "Compliance Violations",
        "phrases": [
            "legal action",
            "take you to court",
            "sue you",
            "garnish your wages",
            "garnish wages",
            "seize your property",
            "lien on your property",
            "send lawyers",
            "our lawyers",
            "heard every excuse",
            "not our problem",
            "doesn't pay bills",
            "don't be dramatic",
            "irresponsible",
            "couldn't be bothered",
        ],
    },
    "required_disclosures": {
        "display_name": "Required Disclosures",
        "phrases": [
            "right to dispute",
            "dispute this",
            "raise a dispute",
            "hardship",
            "hardship program",
            "hardship hold",
            "financial hardship",
            "hardship provisions",
            "payment arrangement",
            "payment plan",
            "flexible",
            "confirm your",
            "verify your",
            "date of birth",
        ],
    },
    "empathy_indicators": {
        "display_name": "Empathy Indicators",
        "phrases": [
            "I understand",
            "I'm sorry",
            "I apologise",
            "that must be",
            "I can hear how",
            "I appreciate",
            "thank you for sharing",
            "difficult situation",
            "here to help",
            "let me help",
        ],
    },
    "escalation_triggers": {
        "display_name": "Escalation Triggers",
        "phrases": [
            "speak to supervisor",
            "speak to manager",
            "speak to a manager",
            "make a complaint",
            "file a complaint",
            "formal complaint",
            "recording this",
            "this is harassment",
            "stop calling",
            "stop harassing",
            "ombudsman",
            "AFCA",
        ],
    },
    "vulnerability_indicators": {
        "display_name": "Vulnerability Indicators",
        "phrases": [
            "cancer",
            "hospital",
            "medical",
            "diagnosis",
            "surgery",
            "mental health",
            "anxiety",
            "depression",
            "panic attack",
            "dialysis",
            "lost my job",
            "job loss",
            "unemployed",
            "no income",
            "rent behind",
            "can't afford",
            "family violence",
            "domestic violence",
            "divorce",
            "separation",
        ],
    },
}


class PhraseMatcherService:
    """Service for CI Phrase Matcher management."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client: Optional[insights.ContactCenterInsightsClient] = None

    @property
    def client(self) -> insights.ContactCenterInsightsClient:
        if self._client is None:
            self._client = insights.ContactCenterInsightsClient()
        return self._client

    @property
    def parent(self) -> str:
        return self.settings.insights_parent

    def create_phrase_matcher(
        self,
        matcher_id: str,
        display_name: str,
        phrases: list[str],
    ) -> insights.PhraseMatcher:
        """Create a phrase matcher in CI.

        Args:
            matcher_id: Unique ID for the matcher
            display_name: Human-readable name
            phrases: List of phrases to match

        Returns:
            Created PhraseMatcher resource
        """
        # Build phrase match rules - each phrase is a separate rule group
        # Use exact match config for each phrase rule
        phrase_match_rule_groups = []
        for phrase in phrases:
            # Create exact match config for the rule
            exact_match_config = insights.ExactMatchConfig(case_sensitive=False)
            rule = insights.PhraseMatchRule(
                query=phrase,
                negated=False,
                config=insights.PhraseMatchRuleConfig(
                    exact_match_config=exact_match_config
                ),
            )
            rule_group = insights.PhraseMatchRuleGroup(
                type_=insights.PhraseMatchRuleGroup.PhraseMatchRuleGroupType.ANY_OF,
                phrase_match_rules=[rule],
            )
            phrase_match_rule_groups.append(rule_group)

        # Create matcher
        matcher = insights.PhraseMatcher(
            display_name=display_name,
            type_=insights.PhraseMatcher.PhraseMatcherType.ANY_OF,
            active=True,
            phrase_match_rule_groups=phrase_match_rule_groups,
        )

        request = insights.CreatePhraseMatcherRequest(
            parent=self.parent,
            phrase_matcher=matcher,
        )

        try:
            created = self.client.create_phrase_matcher(request=request)
            logger.info(f"Created phrase matcher: {created.name}")
            return created
        except Exception as e:
            if "ALREADY_EXISTS" in str(e):
                logger.info(f"Phrase matcher {matcher_id} already exists")
                return self.get_phrase_matcher_by_display_name(display_name)
            raise

    def get_phrase_matcher(self, matcher_name: str) -> Optional[insights.PhraseMatcher]:
        """Get phrase matcher by full resource name."""
        try:
            return self.client.get_phrase_matcher(name=matcher_name)
        except Exception as e:
            logger.warning(f"Phrase matcher not found: {matcher_name}: {e}")
            return None

    def get_phrase_matcher_by_display_name(
        self, display_name: str
    ) -> Optional[insights.PhraseMatcher]:
        """Get phrase matcher by display name."""
        matchers = self.list_phrase_matchers()
        for m in matchers:
            if m.display_name == display_name:
                return m
        return None

    def list_phrase_matchers(self) -> list[insights.PhraseMatcher]:
        """List all phrase matchers."""
        request = insights.ListPhraseMatchersRequest(parent=self.parent)
        return list(self.client.list_phrase_matchers(request=request))

    def delete_phrase_matcher(self, matcher_name: str) -> bool:
        """Delete a phrase matcher by full resource name."""
        try:
            self.client.delete_phrase_matcher(name=matcher_name)
            logger.info(f"Deleted phrase matcher: {matcher_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete phrase matcher: {e}")
            return False

    def ensure_all_matchers(self) -> dict[str, insights.PhraseMatcher]:
        """Create all configured phrase matchers if they don't exist.

        Returns:
            Dict mapping matcher_id to PhraseMatcher resource
        """
        existing = {m.display_name: m for m in self.list_phrase_matchers()}
        results = {}

        for matcher_id, config in PHRASE_MATCHERS.items():
            display_name = config["display_name"]

            if display_name in existing:
                logger.info(f"Phrase matcher already exists: {display_name}")
                results[matcher_id] = existing[display_name]
            else:
                matcher = self.create_phrase_matcher(
                    matcher_id=matcher_id,
                    display_name=display_name,
                    phrases=config["phrases"],
                )
                results[matcher_id] = matcher

        return results

    def get_matcher_names(self) -> list[str]:
        """Get full resource names of all configured matchers.

        Returns:
            List of full resource names for use in analysis config
        """
        matchers = self.list_phrase_matchers()
        configured_names = {c["display_name"] for c in PHRASE_MATCHERS.values()}

        return [m.name for m in matchers if m.display_name in configured_names]

    def delete_all_matchers(self) -> int:
        """Delete all phrase matchers. Use with caution.

        Returns:
            Number of matchers deleted
        """
        matchers = self.list_phrase_matchers()
        deleted = 0
        for m in matchers:
            if self.delete_phrase_matcher(m.name):
                deleted += 1
        return deleted
