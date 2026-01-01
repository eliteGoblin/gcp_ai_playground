# Phrase Matcher Design Document

## 1. Overview

### Purpose
Add CI Phrase Matcher capability to detect compliance-relevant keywords in conversations before ADK coach analysis. Phrase Matchers provide fast, rule-based detection that complements the LLM's contextual analysis.

### Value Proposition
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CI Phrase Matcher + ADK Coach = Best of Both Worlds                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CI Phrase Matcher (Fast, Cheap)          ADK Coach (Smart, Contextual)     │
│  ─────────────────────────────            ────────────────────────────      │
│  ✓ Detects exact phrases                  ✓ Understands context             │
│  ✓ No per-token cost                      ✓ Judges severity                 │
│  ✓ Consistent results                     ✓ Reduces false positives         │
│  ✓ First-pass filter                      ✓ Generates coaching              │
│                                                                              │
│  Example: CI detects "legal action"       Coach determines if threatening   │
│           phrase in transcript      →     or informational mention          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Phrase Matcher Categories

### 2.1 Compliance Violations (Red Flags)
Phrases that may indicate compliance breaches - require LLM confirmation.

```yaml
matcher_id: compliance_violations
display_name: "Compliance Violations"
type: ANY_OF  # Match if any phrase found
revision_tag: v1.0.0

phrases:
  # Threatening language
  - "legal action"
  - "take you to court"
  - "sue you"
  - "garnish your wages"
  - "garnish wages"
  - "seize your property"
  - "lien on your property"
  - "send lawyers"
  - "our lawyers"

  # Harassment indicators
  - "heard every excuse"
  - "not our problem"
  - "doesn't pay bills"
  - "your choice"  # Often used dismissively

  # Unprofessional language
  - "don't be dramatic"
  - "irresponsible"
  - "couldn't be bothered"
```

### 2.2 Required Disclosures (Compliance Checks)
Phrases that SHOULD be present in certain call types.

```yaml
matcher_id: required_disclosures
display_name: "Required Disclosures"
type: ANY_OF
revision_tag: v1.0.0

phrases:
  # Right to dispute
  - "right to dispute"
  - "dispute this"
  - "raise a dispute"

  # Hardship options
  - "hardship"
  - "hardship program"
  - "hardship hold"
  - "financial hardship"
  - "hardship provisions"
  - "payment arrangement"
  - "payment plan"
  - "flexible"

  # Identity verification (required)
  - "confirm your"
  - "verify your"
  - "date of birth"
```

### 2.3 Empathy Indicators (Quality Signals)
Positive phrases indicating good agent behavior.

```yaml
matcher_id: empathy_indicators
display_name: "Empathy Indicators"
type: ANY_OF
revision_tag: v1.0.0

phrases:
  - "I understand"
  - "I'm sorry"
  - "I apologise"
  - "that must be"
  - "I can hear how"
  - "I appreciate"
  - "thank you for sharing"
  - "difficult situation"
  - "here to help"
  - "let me help"
```

### 2.4 Escalation Triggers (Risk Signals)
Phrases indicating potential complaint or escalation.

```yaml
matcher_id: escalation_triggers
display_name: "Escalation Triggers"
type: ANY_OF
revision_tag: v1.0.0

phrases:
  - "speak to supervisor"
  - "speak to manager"
  - "speak to a manager"
  - "make a complaint"
  - "file a complaint"
  - "formal complaint"
  - "recording this"
  - "this is harassment"
  - "stop calling"
  - "stop harassing"
  - "ombudsman"
  - "AFCA"  # Australian Financial Complaints Authority
```

### 2.5 Vulnerability Indicators
Phrases indicating vulnerable customer situations.

```yaml
matcher_id: vulnerability_indicators
display_name: "Vulnerability Indicators"
type: ANY_OF
revision_tag: v1.0.0

phrases:
  # Health
  - "cancer"
  - "hospital"
  - "medical"
  - "diagnosis"
  - "surgery"
  - "mental health"
  - "anxiety"
  - "depression"
  - "panic attack"
  - "dialysis"

  # Financial
  - "lost my job"
  - "job loss"
  - "unemployed"
  - "no income"
  - "rent behind"
  - "can't afford"

  # Family
  - "family violence"
  - "domestic violence"
  - "divorce"
  - "separation"
```

---

## 3. Data Contract: CI → BigQuery → ADK Coach

### 3.1 Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHRASE MATCHER DATA FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. CI Analysis (with Phrase Matcher enabled)                               │
│  ────────────────────────────────────────────                               │
│                                                                              │
│  ┌─────────────────────┐                                                    │
│  │ CI creates analysis │──▶ run_phrase_matcher_annotator=True              │
│  │ with annotators     │    phrase_matchers=[compliance_violations, ...]    │
│  └──────────┬──────────┘                                                    │
│             │                                                                │
│             ▼                                                                │
│  ┌─────────────────────┐                                                    │
│  │ Analysis result     │                                                    │
│  │ includes:           │                                                    │
│  │ - phrase_matchers   │  RuntimeAnnotation with phrase match data         │
│  │   in annotations    │                                                    │
│  └──────────┬──────────┘                                                    │
│             │                                                                │
│  2. Extract & Store in BigQuery                                             │
│  ─────────────────────────────                                              │
│             │                                                                │
│             ▼                                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ci_enrichment table                                                  │   │
│  │                                                                       │   │
│  │ phrase_matches: RECORD REPEATED                                       │   │
│  │ ├── matcher_id: STRING         # "compliance_violations"             │   │
│  │ ├── display_name: STRING       # "Compliance Violations"             │   │
│  │ ├── match_count: INTEGER       # Number of matches                   │   │
│  │ └── matches: RECORD REPEATED                                          │   │
│  │     ├── phrase: STRING         # "legal action"                      │   │
│  │     ├── turn_index: INTEGER    # Which turn                          │   │
│  │     ├── speaker: STRING        # "AGENT" or "CUSTOMER"               │   │
│  │     └── text_snippet: STRING   # Surrounding context                 │   │
│  │                                                                       │   │
│  │ ci_flags: STRING REPEATED      # ["compliance_violation", "escalation"]│   │
│  │ ci_flag_count: INTEGER         # Total flag count                    │   │
│  │ ci_summary_text: STRING        # From CI summarization               │   │
│  │ ci_summary_resolution: STRING  # Y/N from CI summary                 │   │
│  └──────────────────────────────────────┬───────────────────────────────┘   │
│                                         │                                    │
│  3. ADK Coach Consumption                                                   │
│  ────────────────────────                                                   │
│                                         │                                    │
│                                         ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ADK Coach receives enriched context:                                 │   │
│  │                                                                       │   │
│  │ {                                                                     │   │
│  │   "transcript": "...",                                               │   │
│  │   "ci_sentiment": -1.0,                                              │   │
│  │   "ci_flags": ["compliance_violation", "vulnerability_indicator"],   │   │
│  │   "ci_phrase_matches": [                                             │   │
│  │     {                                                                 │   │
│  │       "matcher": "compliance_violations",                            │   │
│  │       "matches": [                                                    │   │
│  │         {"phrase": "legal action", "turn": 8, "speaker": "AGENT"}   │   │
│  │       ]                                                               │   │
│  │     }                                                                 │   │
│  │   ]                                                                   │   │
│  │ }                                                                     │   │
│  │                                                                       │   │
│  │ Coach then:                                                           │   │
│  │ 1. Reviews flagged phrases in context                                │   │
│  │ 2. Judges if actual violation (vs false positive)                    │   │
│  │ 3. Generates coaching with CI flag confirmation                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 BigQuery Schema Updates

Add to `ci_enrichment` table:

```python
# In cc_coach/services/bigquery.py

CI_ENRICHMENT_SCHEMA = [
    # ... existing fields ...

    # NEW: Phrase Matcher results
    bigquery.SchemaField(
        "phrase_matches",
        "RECORD",
        mode="REPEATED",
        fields=[
            bigquery.SchemaField("matcher_id", "STRING"),
            bigquery.SchemaField("display_name", "STRING"),
            bigquery.SchemaField("match_count", "INTEGER"),
            bigquery.SchemaField(
                "matches",
                "RECORD",
                mode="REPEATED",
                fields=[
                    bigquery.SchemaField("phrase", "STRING"),
                    bigquery.SchemaField("turn_index", "INTEGER"),
                    bigquery.SchemaField("speaker", "STRING"),
                    bigquery.SchemaField("text_snippet", "STRING"),
                ],
            ),
        ],
    ),

    # NEW: Aggregated CI flags for quick filtering
    bigquery.SchemaField("ci_flags", "STRING", mode="REPEATED"),
    bigquery.SchemaField("ci_flag_count", "INTEGER"),

    # NEW: CI Summary text
    bigquery.SchemaField("ci_summary_text", "STRING"),
    bigquery.SchemaField("ci_summary_resolution", "STRING"),
]
```

---

## 4. Python Data Models

### 4.1 Phrase Match Models

```python
# cc_coach/models/phrase_match.py
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
            r.matcher_id == MatcherCategory.COMPLIANCE_VIOLATIONS.value
            and r.has_matches
            for r in self.matcher_results
        )

    @property
    def has_escalation_triggers(self) -> bool:
        """Check for escalation trigger matches."""
        return any(
            r.matcher_id == MatcherCategory.ESCALATION_TRIGGERS.value
            and r.has_matches
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

            # Missing required disclosures (absence of expected phrases)
            # Note: This is inverse - absence is the flag
            # Handled separately in coach logic

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
                simplified_matches.append({
                    "category": pm["display_name"],
                    "matches": [
                        {
                            "phrase": m["phrase"],
                            "turn": m["turn_index"],
                            "speaker": m["speaker"],
                        }
                        for m in pm.get("matches", [])
                    ]
                })

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
```

### 4.2 CI Enrichment Extended Model

```python
# cc_coach/models/ci_enrichment.py (extended)
"""Extended CI enrichment model with phrase match support."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from cc_coach.models.phrase_match import (
    MatcherResult,
    PhraseMatchResults,
    CoachPhraseContext,
)


@dataclass
class PerTurnSentiment:
    """Per-turn sentiment data."""
    turn_index: int
    score: float
    magnitude: float


@dataclass
class Entity:
    """Extracted entity."""
    type: str
    name: str
    salience: float
    speaker_tag: Optional[int] = None


@dataclass
class CIEnrichment:
    """Complete CI enrichment data for a conversation."""
    conversation_id: str
    ci_conversation_name: str

    # Transcript
    transcript: str
    turn_count: int
    duration_sec: int

    # Sentiment (customer only)
    customer_sentiment_score: Optional[float] = None
    customer_sentiment_magnitude: Optional[float] = None
    per_turn_sentiments: list[PerTurnSentiment] = field(default_factory=list)

    # Entities and topics
    entities: list[Entity] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)

    # Metadata labels
    labels: dict[str, Any] = field(default_factory=dict)

    # NEW: Phrase matches
    phrase_matches: list[MatcherResult] = field(default_factory=list)
    ci_flags: list[str] = field(default_factory=list)
    ci_flag_count: int = 0

    # NEW: Summary
    ci_summary_text: Optional[str] = None
    ci_summary_resolution: Optional[str] = None

    # Timestamps
    analysis_completed_at: Optional[datetime] = None
    exported_at: Optional[datetime] = None

    def to_bq_row(self) -> dict:
        """Convert to BigQuery row dict."""
        return {
            "conversation_id": self.conversation_id,
            "ci_conversation_name": self.ci_conversation_name,
            "transcript": self.transcript,
            "turn_count": self.turn_count,
            "duration_sec": self.duration_sec,
            "customer_sentiment_score": self.customer_sentiment_score,
            "customer_sentiment_magnitude": self.customer_sentiment_magnitude,
            "per_turn_sentiments": [
                {"turn_index": s.turn_index, "score": s.score, "magnitude": s.magnitude}
                for s in self.per_turn_sentiments
            ],
            "entities": [
                {"type": e.type, "name": e.name, "salience": e.salience, "speaker_tag": e.speaker_tag}
                for e in self.entities
            ],
            "topics": self.topics,
            "labels": self.labels,
            # Phrase matches
            "phrase_matches": [m.to_dict() for m in self.phrase_matches],
            "ci_flags": self.ci_flags,
            "ci_flag_count": self.ci_flag_count,
            "ci_summary_text": self.ci_summary_text,
            "ci_summary_resolution": self.ci_summary_resolution,
            # Timestamps
            "analysis_completed_at": self.analysis_completed_at.isoformat() if self.analysis_completed_at else None,
            "exported_at": self.exported_at.isoformat() if self.exported_at else None,
        }

    def to_coach_context(self) -> CoachPhraseContext:
        """Create coach context from this enrichment."""
        return CoachPhraseContext(
            conversation_id=self.conversation_id,
            ci_sentiment_score=self.customer_sentiment_score or 0.0,
            ci_summary=self.ci_summary_text or "",
            ci_flags=self.ci_flags,
            phrase_matches=[m.to_dict() for m in self.phrase_matches if m.has_matches],
        )
```

---

## 5. CI API Integration

### 5.1 Create Phrase Matchers

```python
# cc_coach/services/phrase_matcher.py
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
            "legal action", "take you to court", "sue you",
            "garnish your wages", "garnish wages", "seize your property",
            "lien on your property", "send lawyers", "our lawyers",
            "heard every excuse", "not our problem", "doesn't pay bills",
            "don't be dramatic", "irresponsible", "couldn't be bothered",
        ],
    },
    "required_disclosures": {
        "display_name": "Required Disclosures",
        "phrases": [
            "right to dispute", "dispute this", "raise a dispute",
            "hardship", "hardship program", "hardship hold",
            "financial hardship", "hardship provisions",
            "payment arrangement", "payment plan", "flexible",
            "confirm your", "verify your", "date of birth",
        ],
    },
    "empathy_indicators": {
        "display_name": "Empathy Indicators",
        "phrases": [
            "I understand", "I'm sorry", "I apologise",
            "that must be", "I can hear how", "I appreciate",
            "thank you for sharing", "difficult situation",
            "here to help", "let me help",
        ],
    },
    "escalation_triggers": {
        "display_name": "Escalation Triggers",
        "phrases": [
            "speak to supervisor", "speak to manager", "speak to a manager",
            "make a complaint", "file a complaint", "formal complaint",
            "recording this", "this is harassment",
            "stop calling", "stop harassing", "ombudsman", "AFCA",
        ],
    },
    "vulnerability_indicators": {
        "display_name": "Vulnerability Indicators",
        "phrases": [
            "cancer", "hospital", "medical", "diagnosis", "surgery",
            "mental health", "anxiety", "depression", "panic attack", "dialysis",
            "lost my job", "job loss", "unemployed", "no income",
            "rent behind", "can't afford",
            "family violence", "domestic violence", "divorce", "separation",
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
        type_: str = "ANY_OF",
    ) -> insights.PhraseMatcher:
        """Create a phrase matcher in CI.

        Args:
            matcher_id: Unique ID for the matcher
            display_name: Human-readable name
            phrases: List of phrases to match
            type_: Match type (ANY_OF = any phrase matches)

        Returns:
            Created PhraseMatcher resource
        """
        # Build phrase match rules
        phrase_match_rule_groups = []
        for phrase in phrases:
            rule = insights.PhraseMatchRule(
                query=phrase,
                negated=False,
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
            revision_tag="v1.0.0",
        )

        request = insights.CreatePhraseMatcherRequest(
            parent=self.parent,
            phrase_matcher=matcher,
            phrase_matcher_id=matcher_id,
        )

        try:
            created = self.client.create_phrase_matcher(request=request)
            logger.info(f"Created phrase matcher: {created.name}")
            return created
        except Exception as e:
            if "ALREADY_EXISTS" in str(e):
                logger.info(f"Phrase matcher {matcher_id} already exists")
                return self.get_phrase_matcher(matcher_id)
            raise

    def get_phrase_matcher(self, matcher_id: str) -> Optional[insights.PhraseMatcher]:
        """Get phrase matcher by ID."""
        name = f"{self.parent}/phraseMatchers/{matcher_id}"
        try:
            return self.client.get_phrase_matcher(name=name)
        except Exception as e:
            logger.warning(f"Phrase matcher not found: {name}")
            return None

    def list_phrase_matchers(self) -> list[insights.PhraseMatcher]:
        """List all phrase matchers."""
        request = insights.ListPhraseMatchersRequest(parent=self.parent)
        return list(self.client.list_phrase_matchers(request=request))

    def delete_phrase_matcher(self, matcher_id: str) -> bool:
        """Delete a phrase matcher."""
        name = f"{self.parent}/phraseMatchers/{matcher_id}"
        try:
            self.client.delete_phrase_matcher(name=name)
            logger.info(f"Deleted phrase matcher: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete phrase matcher: {e}")
            return False

    def ensure_all_matchers(self) -> dict[str, insights.PhraseMatcher]:
        """Create all configured phrase matchers."""
        results = {}
        for matcher_id, config in PHRASE_MATCHERS.items():
            matcher = self.create_phrase_matcher(
                matcher_id=matcher_id,
                display_name=config["display_name"],
                phrases=config["phrases"],
            )
            results[matcher_id] = matcher
        return results

    def get_matcher_names(self) -> list[str]:
        """Get full resource names of all configured matchers."""
        return [
            f"{self.parent}/phraseMatchers/{matcher_id}"
            for matcher_id in PHRASE_MATCHERS.keys()
        ]
```

### 5.2 Update InsightsService

```python
# In cc_coach/services/insights.py - updated create_analysis method

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
        enable_summarization: Whether to generate AI summary
        enable_phrase_matchers: Whether to run phrase matchers
        phrase_matcher_names: Specific phrase matcher resource names to use

    Returns:
        Analysis result
    """
    # Build annotator selector
    annotator_selector = insights.AnnotatorSelector(
        run_sentiment_annotator=True,
        run_entity_annotator=True,
        run_intent_annotator=True,
    )

    # Enable summarization
    if enable_summarization:
        annotator_selector.run_summarization_annotator = True
        annotator_selector.summarization_config = insights.AnnotatorSelector.SummarizationConfig(
            summarization_model=insights.AnnotatorSelector.SummarizationConfig.SummarizationModel.BASELINE_MODEL_V2_0
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

    result = operation.result()
    logger.info(f"Analysis complete: {result.name}")
    return result


def extract_phrase_matches(
    self,
    conversation: insights.Conversation,
    transcript_turns: list[dict],
) -> list[dict]:
    """
    Extract phrase match data from CI conversation.

    Args:
        conversation: CI Conversation with analysis
        transcript_turns: Original transcript turns for context

    Returns:
        List of matcher results for BQ insertion
    """
    matcher_results = {}

    # Get phrase match annotations from runtime annotations
    for annotation in conversation.runtime_annotations:
        if annotation.phrase_match_data:
            pm_data = annotation.phrase_match_data
            matcher_name = pm_data.phrase_matcher
            matcher_id = matcher_name.split("/")[-1]

            if matcher_id not in matcher_results:
                matcher_results[matcher_id] = {
                    "matcher_id": matcher_id,
                    "display_name": pm_data.display_name,
                    "match_count": 0,
                    "matches": [],
                }

            # Get turn info from annotation boundaries
            turn_index = annotation.annotation_start_boundary.transcript_index
            speaker = "AGENT" if annotation.channel_tag == 2 else "CUSTOMER"

            # Get text snippet from original transcript
            text_snippet = ""
            if turn_index < len(transcript_turns):
                text_snippet = transcript_turns[turn_index].get("text", "")[:200]

            matcher_results[matcher_id]["matches"].append({
                "phrase": pm_data.phrase_matcher_group,  # The matched phrase
                "turn_index": turn_index,
                "speaker": speaker,
                "text_snippet": text_snippet,
            })
            matcher_results[matcher_id]["match_count"] += 1

    return list(matcher_results.values())
```

---

## 6. Implementation Plan

### Phase 1: Setup (Day 1)
1. Create phrase matcher configuration file
2. Add phrase matcher service class
3. Create all phrase matchers via CI API
4. Verify matchers exist: `cc-coach explore phrase-matchers`

### Phase 2: Integration (Day 2)
1. Update `create_analysis()` to enable phrase matchers
2. Implement `extract_phrase_matches()` extraction
3. Update CI enrichment schema in BigQuery
4. Add phrase match Python models

### Phase 3: Pipeline Update (Day 3)
1. Update pipeline to extract phrase matches
2. Store phrase matches in `ci_enrichment`
3. Generate `ci_flags` from matches
4. Test with dev dataset

### Phase 4: Coach Integration (Day 4)
1. Update coach prompt to include CI flags
2. Add phrase context to coach input
3. Test coach uses CI flags appropriately
4. Verify false positive filtering works

---

## 7. Testing Matrix

### Test Conversations by Expected Matches

| Conversation | Compliance Violations | Required Disclosures | Empathy | Escalation | Vulnerability |
|--------------|----------------------|---------------------|---------|------------|---------------|
| toxic-agent-0001 | ✅ Many | ❌ Missing | ❌ None | ✅ Customer | ✅ Medical |
| exemplary-agent-0001 | ❌ None | ✅ Present | ✅ Many | ❌ None | ✅ Medical |
| 3f2d9e4b (hardship) | ❌ None | ✅ Present | ✅ Some | ❌ None | ✅ Mental health |
| 6a4a8f17 (wrong party) | ❌ None | ✅ Verify ID | ❌ None | ✅ Stop calling | ❌ None |
| 9c8f3c2a (angry) | ❌ None | ✅ Present | ✅ Some | ✅ Complaint | ❌ None |
| c9e5f3a0 (escalation) | ❌ None | ❌ Partial | ✅ Some | ✅ Manager | ✅ Job loss |
| b8d4e2f9 (happy path) | ❌ None | ✅ Present | ✅ Some | ❌ None | ❌ None |

### Expected CI Flags by Conversation

```
toxic-agent-0001:      [AGENT_COMPLIANCE_VIOLATION, VULNERABILITY_DETECTED]
exemplary-agent-0001:  [VULNERABILITY_DETECTED]
3f2d9e4b:             [VULNERABILITY_DETECTED]
6a4a8f17:             [CUSTOMER_ESCALATION]
9c8f3c2a:             [CUSTOMER_ESCALATION]
c9e5f3a0:             [CUSTOMER_ESCALATION, VULNERABILITY_DETECTED]
b8d4e2f9:             [] (clean conversation)
```

---

## 8. Sample Output

### CI Enrichment Row (BQ)

```json
{
  "conversation_id": "a1b2c3d4-toxic-agent-test-0001",
  "ci_conversation_name": "projects/.../conversations/a1b2c3d4-toxic-agent-test-0001",

  "phrase_matches": [
    {
      "matcher_id": "compliance_violations",
      "display_name": "Compliance Violations",
      "match_count": 5,
      "matches": [
        {"phrase": "legal action", "turn_index": 6, "speaker": "AGENT", "text_snippet": "...I need at least $3,000 today to stop this from going to legal..."},
        {"phrase": "garnish your wages", "turn_index": 8, "speaker": "AGENT", "text_snippet": "...We can garnish your wages, put a lien on your property..."},
        {"phrase": "legal action", "turn_index": 20, "speaker": "AGENT", "text_snippet": "...If this goes to our legal team..."},
        {"phrase": "heard every excuse", "turn_index": 4, "speaker": "AGENT", "text_snippet": "...I've heard every excuse in the book..."},
        {"phrase": "don't be dramatic", "turn_index": 24, "speaker": "AGENT", "text_snippet": "Don't be dramatic. You could sell that car..."}
      ]
    },
    {
      "matcher_id": "vulnerability_indicators",
      "display_name": "Vulnerability Indicators",
      "match_count": 3,
      "matches": [
        {"phrase": "lost my job", "turn_index": 3, "speaker": "CUSTOMER", "text_snippet": "...I lost my job back in October..."},
        {"phrase": "medical", "turn_index": 3, "speaker": "CUSTOMER", "text_snippet": "...unexpected medical bills..."},
        {"phrase": "hospital", "turn_index": 13, "speaker": "CUSTOMER", "text_snippet": "...My wife was in hospital for three weeks..."}
      ]
    },
    {
      "matcher_id": "escalation_triggers",
      "display_name": "Escalation Triggers",
      "match_count": 2,
      "matches": [
        {"phrase": "speak to supervisor", "turn_index": 19, "speaker": "CUSTOMER", "text_snippet": "...I want to speak to your supervisor..."},
        {"phrase": "this is harassment", "turn_index": 21, "speaker": "CUSTOMER", "text_snippet": "...This is harassment..."}
      ]
    },
    {
      "matcher_id": "empathy_indicators",
      "display_name": "Empathy Indicators",
      "match_count": 0,
      "matches": []
    },
    {
      "matcher_id": "required_disclosures",
      "display_name": "Required Disclosures",
      "match_count": 0,
      "matches": []
    }
  ],

  "ci_flags": ["AGENT_COMPLIANCE_VIOLATION", "VULNERABILITY_DETECTED", "CUSTOMER_ESCALATION"],
  "ci_flag_count": 3,

  "ci_summary_text": "situation: Customer owes $12,847.50, 97 days past due...",
  "ci_summary_resolution": "N",

  "customer_sentiment_score": -1.0,
  "customer_sentiment_magnitude": 1.0
}
```

---

## 9. ADK Coach Prompt Integration

### Sample Prompt Section

```markdown
## CI Pre-Analysis Findings

The following signals were detected by automated keyword matching.
Review these in context to confirm if they represent actual issues.

**CI Flags**: AGENT_COMPLIANCE_VIOLATION, VULNERABILITY_DETECTED, CUSTOMER_ESCALATION

**Detected Phrases**:
  - Compliance Violations:
    - "legal action" (Turn 6, AGENT)
    - "garnish your wages" (Turn 8, AGENT)
    - "heard every excuse" (Turn 4, AGENT)
    - "don't be dramatic" (Turn 24, AGENT)
  - Vulnerability Indicators:
    - "lost my job" (Turn 3, CUSTOMER)
    - "hospital" (Turn 13, CUSTOMER)
  - Escalation Triggers:
    - "speak to supervisor" (Turn 19, CUSTOMER)
    - "this is harassment" (Turn 21, CUSTOMER)

**Customer Sentiment**: -1.0 (very negative)

**CI Summary**: Customer owes $12,847.50, 97 days past due. Agent demanded
immediate payment and threatened legal action. Customer offered payment plan
but was refused. Resolution: N

---

Based on these CI findings and your review of the transcript, provide your coaching assessment.
For each CI flag, confirm whether it represents an actual issue requiring coaching.
```
