"""Data models for CI Phrase Matcher results."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class MatcherCategory(str, Enum):
    """Phrase matcher categories."""

    COMPLIANCE_VIOLATIONS = "compliance_violations"
    REQUIRED_DISCLOSURES = "required_disclosures"
    EMPATHY_INDICATORS = "empathy_indicators"
    ESCALATION_TRIGGERS = "escalation_triggers"
    VULNERABILITY_INDICATORS = "vulnerability_indicators"


class Speaker(str, Enum):
    """Speaker roles."""

    AGENT = "AGENT"
    CUSTOMER = "CUSTOMER"
    UNKNOWN = "UNKNOWN"


@dataclass
class PhraseMatch:
    """Individual phrase match from CI."""

    phrase: str
    turn_index: int
    speaker: Speaker
    text_snippet: str  # Context around the match
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dict for BQ insertion."""
        return {
            "phrase": self.phrase,
            "turn_index": self.turn_index,
            "speaker": self.speaker.value,
            "text_snippet": self.text_snippet,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PhraseMatch":
        """Create from dict."""
        return cls(
            phrase=data["phrase"],
            turn_index=data["turn_index"],
            speaker=Speaker(data["speaker"]),
            text_snippet=data.get("text_snippet", ""),
        )


@dataclass
class MatcherResult:
    """Results from a single phrase matcher."""

    matcher_id: str
    display_name: str
    match_count: int
    matches: list[PhraseMatch] = field(default_factory=list)

    @property
    def has_matches(self) -> bool:
        """Check if any matches found."""
        return self.match_count > 0

    @property
    def agent_matches(self) -> list[PhraseMatch]:
        """Get matches from agent turns only."""
        return [m for m in self.matches if m.speaker == Speaker.AGENT]

    @property
    def customer_matches(self) -> list[PhraseMatch]:
        """Get matches from customer turns only."""
        return [m for m in self.matches if m.speaker == Speaker.CUSTOMER]

    def to_dict(self) -> dict:
        """Convert to dict for BQ insertion."""
        return {
            "matcher_id": self.matcher_id,
            "display_name": self.display_name,
            "match_count": self.match_count,
            "matches": [m.to_dict() for m in self.matches],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MatcherResult":
        """Create from dict."""
        return cls(
            matcher_id=data["matcher_id"],
            display_name=data["display_name"],
            match_count=data["match_count"],
            matches=[PhraseMatch.from_dict(m) for m in data.get("matches", [])],
        )


@dataclass
class PhraseMatchResults:
    """Complete phrase match results for a conversation."""

    conversation_id: str
    matcher_results: list[MatcherResult] = field(default_factory=list)
    ci_flags: list[str] = field(default_factory=list)
    processed_at: Optional[datetime] = None

    @property
    def total_match_count(self) -> int:
        """Total matches across all matchers."""
        return sum(r.match_count for r in self.matcher_results)

    @property
    def has_compliance_violations(self) -> bool:
        """Check for compliance violation matches."""
        return any(
            r.matcher_id == MatcherCategory.COMPLIANCE_VIOLATIONS.value and r.has_matches
            for r in self.matcher_results
        )

    @property
    def has_escalation_triggers(self) -> bool:
        """Check for escalation trigger matches."""
        return any(
            r.matcher_id == MatcherCategory.ESCALATION_TRIGGERS.value and r.has_matches
            for r in self.matcher_results
        )

    @property
    def has_vulnerability_indicators(self) -> bool:
        """Check for vulnerability indicator matches."""
        return any(
            r.matcher_id == MatcherCategory.VULNERABILITY_INDICATORS.value
            and r.has_matches
            for r in self.matcher_results
        )

    def get_matcher(self, matcher_id: str) -> Optional[MatcherResult]:
        """Get results for a specific matcher."""
        for r in self.matcher_results:
            if r.matcher_id == matcher_id:
                return r
        return None

    def to_bq_fields(self) -> dict:
        """Convert to BQ field values."""
        return {
            "phrase_matches": [r.to_dict() for r in self.matcher_results],
            "ci_flags": self.ci_flags,
            "ci_flag_count": len(self.ci_flags),
        }

    def generate_ci_flags(self) -> list[str]:
        """Generate CI flags based on matcher results.

        Returns list of flag strings for quick filtering in BQ/dashboard.
        """
        flags = []

        for result in self.matcher_results:
            if not result.has_matches:
                continue

            # Compliance violations from agent are red flags
            if result.matcher_id == MatcherCategory.COMPLIANCE_VIOLATIONS.value:
                if result.agent_matches:
                    flags.append("AGENT_COMPLIANCE_VIOLATION")

            # Escalation triggers from customer
            elif result.matcher_id == MatcherCategory.ESCALATION_TRIGGERS.value:
                if result.customer_matches:
                    flags.append("CUSTOMER_ESCALATION")

            # Vulnerability indicators
            elif result.matcher_id == MatcherCategory.VULNERABILITY_INDICATORS.value:
                flags.append("VULNERABILITY_DETECTED")

        self.ci_flags = flags
        return flags


@dataclass
class CoachPhraseContext:
    """Phrase match context prepared for ADK coach consumption."""

    conversation_id: str
    ci_sentiment_score: float
    ci_summary: str
    ci_flags: list[str]
    phrase_matches: list[dict]  # Simplified for prompt injection

    @classmethod
    def from_enrichment(cls, enrichment_data: dict) -> "CoachPhraseContext":
        """Create coach context from ci_enrichment data."""
        # Simplify phrase matches for prompt
        simplified_matches = []
        for pm in enrichment_data.get("phrase_matches", []):
            if pm.get("match_count", 0) > 0:
                simplified_matches.append(
                    {
                        "category": pm["display_name"],
                        "matches": [
                            {
                                "phrase": m["phrase"],
                                "turn": m["turn_index"],
                                "speaker": m["speaker"],
                            }
                            for m in pm.get("matches", [])
                        ],
                    }
                )

        return cls(
            conversation_id=enrichment_data["conversation_id"],
            ci_sentiment_score=enrichment_data.get("customer_sentiment_score", 0.0),
            ci_summary=enrichment_data.get("ci_summary_text", ""),
            ci_flags=enrichment_data.get("ci_flags", []),
            phrase_matches=simplified_matches,
        )

    def to_coach_prompt_section(self) -> str:
        """Generate prompt section for coach about CI findings."""
        if not self.ci_flags and not self.phrase_matches:
            return "No CI flags or phrase matches detected."

        sections = []

        if self.ci_flags:
            sections.append(f"**CI Flags**: {', '.join(self.ci_flags)}")

        if self.phrase_matches:
            sections.append("**Detected Phrases**:")
            for pm in self.phrase_matches:
                sections.append(f"  - {pm['category']}:")
                for m in pm["matches"]:
                    sections.append(
                        f"    - \"{m['phrase']}\" (Turn {m['turn']}, {m['speaker']})"
                    )

        if self.ci_sentiment_score:
            sections.append(f"**Customer Sentiment**: {self.ci_sentiment_score:.1f}")

        return "\n".join(sections)
