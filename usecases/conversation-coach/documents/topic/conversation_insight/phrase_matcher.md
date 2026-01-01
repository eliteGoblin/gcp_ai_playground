# CI Phrase Matcher: How It Works

## Overview

Phrase Matchers are a feature of **Google Cloud Contact Center AI Insights (CCAI)** that detect specific keywords or phrases in conversation transcripts. They are:

- **Rule-based** - No ML/LLM involved
- **Exact string matching** - Case-insensitive substring search
- **Fast and cheap** - Included in CI analysis, no extra cost
- **Stored in GCP** - Managed via API or Console

---

## How Phrase Matching Works

### The Core Concept

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHRASE MATCHING = Ctrl+F                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   You define:     "don't be dramatic"                                       │
│                                                                              │
│   Transcript:     "Don't be dramatic. You could sell that car..."           │
│                    ^^^^^^^^^^^^^^^^^                                         │
│                          │                                                   │
│                          └──── MATCH! (case-insensitive substring)          │
│                                                                              │
│   Result:         Turn flagged under "Compliance Violations" matcher        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What It CAN Do

| Capability | Example |
|------------|---------|
| Exact phrase match | "legal action" matches "...taking legal action against..." |
| Case-insensitive | "Don't Be Dramatic" matches "don't be dramatic" |
| Partial match | "hospital" matches "My wife was in hospital for..." |
| Multiple phrases per matcher | One matcher can have 10-50+ phrases |

### What It CANNOT Do

| Limitation | Example |
|------------|---------|
| Semantic understanding | "You're being emotional" will NOT match "don't be dramatic" |
| Synonym matching | "sue" will NOT match "take legal action" (unless both defined) |
| Context awareness | Cannot distinguish threat from disclosure ("legal action" always matches) |
| Typo tolerance | "leagal action" will NOT match "legal action" |

---

## Rule Structure

### Hierarchy

```
PhraseMatcher (stored in GCP)
├── display_name: "Compliance Violations"
├── type: ANY_OF (match if ANY rule group matches)
├── active: true
│
└── phrase_match_rule_groups: [
      ┌─────────────────────────────────────────┐
      │ RuleGroup 1                              │
      │ ├── type: ANY_OF                         │
      │ └── rules: [                             │
      │       PhraseMatchRule {                  │
      │         query: "legal action"            │
      │         config: ExactMatchConfig {       │
      │           case_sensitive: false          │
      │         }                                │
      │       }                                  │
      │     ]                                    │
      └─────────────────────────────────────────┘
      ┌─────────────────────────────────────────┐
      │ RuleGroup 2                              │
      │ └── rules: [ query: "sue you" ]          │
      └─────────────────────────────────────────┘
      ┌─────────────────────────────────────────┐
      │ RuleGroup 3                              │
      │ └── rules: [ query: "garnish wages" ]    │
      └─────────────────────────────────────────┘
      ... (one rule group per phrase)
    ]
```

### Key Points

- **One rule = one phrase** - Each phrase is a separate `PhraseMatchRule`
- **One rule group per phrase** - Our implementation wraps each phrase in its own group
- **ANY_OF logic** - Match triggers if ANY phrase is found
- **ExactMatchConfig** - Required, sets `case_sensitive: false`

---

## Current Implementation

### Phrase Matchers Defined

We have 5 phrase matchers configured in `cc_coach/services/phrase_matcher.py`:

#### 1. Compliance Violations (15 phrases)
Detects threatening or unprofessional language from agents.

```python
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
}
```

#### 2. Required Disclosures (14 phrases)
Detects whether agents mention required compliance information.

```python
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
}
```

#### 3. Empathy Indicators (10 phrases)
Detects empathetic language from agents.

```python
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
}
```

#### 4. Escalation Triggers (12 phrases)
Detects when customers express intent to escalate.

```python
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
}
```

#### 5. Vulnerability Indicators (20 phrases)
Detects signs of customer vulnerability (medical, financial, domestic).

```python
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
}
```

---

## Where They're Stored

### GCP Location

```
Project:  vertexdemo-481519
Location: us-central1
Service:  Contact Center AI Insights

Resource Names:
├── projects/38797000650/locations/us-central1/phraseMatchers/1074601424508207727  (Vulnerability)
├── projects/38797000650/locations/us-central1/phraseMatchers/16023211626256327059 (Escalation)
├── projects/38797000650/locations/us-central1/phraseMatchers/8126200328266097586  (Empathy)
├── projects/38797000650/locations/us-central1/phraseMatchers/8689117984500873752  (Disclosures)
└── projects/38797000650/locations/us-central1/phraseMatchers/8420925564263523014  (Compliance)
```

### Console Access

```
GCP Console → Contact Center AI Insights → Phrase Matchers
```

---

## Real Data Example

### Conversation: Toxic Agent Test

**ID:** `a1b2c3d4-toxic-agent-test-0001`

This is a synthetic test conversation where an agent uses threatening language with a customer experiencing hardship.

### Phrase Match Results

The CI analysis found **17 phrase match annotations** across 5 matchers:

#### Compliance Violations (6 matches)

| Turn | Speaker | Matched Phrase | Context |
|------|---------|----------------|---------|
| 4 | AGENT | "heard every excuse" | "Mr Chen, I've **heard every excuse** in the book. Medical bills, job loss..." |
| 8 | AGENT | "legal action", "garnish your wages" | "...We're talking about **legal action** here. We can **garnish your wages**..." |
| 14 | AGENT | "doesn't pay bills" | "Compassion **doesn't pay bills**, Mr Chen..." |
| 16 | AGENT | "couldn't be bothered", "irresponsible" | "...you **couldn't be bothered** to make payments. That's **irresponsible**..." |
| 24 | AGENT | "don't be dramatic" | "**Don't be dramatic**. You could sell that car of yours..." |
| 36 | AGENT | "legal action", "our lawyers" | "**Legal action** will commence tomorrow... You'll be hearing from **our lawyers**." |

#### Vulnerability Indicators (7 matches)

| Turn | Speaker | Matched Phrase | Context |
|------|---------|----------------|---------|
| 3 | CUSTOMER | "medical", "lost my job" | "I had some unexpected **medical** bills and I **lost my job**..." |
| 5 | CUSTOMER | "lost my job" | "I just told you I **lost my job**..." |
| 13 | CUSTOMER | "medical", "hospital" | "I had a **medical** emergency. My wife was in **hospital**..." |
| 14 | AGENT | "medical" | "Your wife's **medical** situation, while unfortunate..." |
| 25 | CUSTOMER | "dialysis" | "She needs it to get to her **dialysis** appointments!" |
| 26 | AGENT | "dialysis" | "Everyone's got an excuse. **Dialysis**, chemo, dying grandmother..." |

#### Escalation Triggers (3 matches)

| Turn | Speaker | Matched Phrase | Context |
|------|---------|----------------|---------|
| 21 | CUSTOMER | "this is harassment" | "Are you seriously trying to scare me right now? **This is harassment**." |
| 29 | CUSTOMER | "file a complaint" | "I'm going to **file a complaint**. This call is probably recorded..." |
| 37 | CUSTOMER | "recording this" | "I'm **recording this** whole conversation and I'm going to—" |

#### Required Disclosures (1 match)

| Turn | Speaker | Matched Phrase | Context |
|------|---------|----------------|---------|
| 10 | AGENT | "date of birth" | "...we have all your details. **Date of birth** 15th March 1985..." |

### Generated CI Flags

Based on the phrase matches, the pipeline generates summary flags:

```python
ci_flags = [
    "AGENT_COMPLIANCE_VIOLATION",   # Agent said threatening phrases
    "CUSTOMER_ESCALATION",          # Customer mentioned complaint/harassment
    "VULNERABILITY_DETECTED",       # Medical/hardship keywords found
]
```

---

## Pipeline Integration

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHRASE MATCHER PIPELINE FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. SETUP (one-time)                                                         │
│     ┌─────────────────────────────────────────────────────────────────┐     │
│     │ cc-coach phrase-matcher ensure                                   │     │
│     │                                                                   │     │
│     │ Creates 5 matchers in GCP from PHRASE_MATCHERS config            │     │
│     │ Idempotent - skips if already exists                             │     │
│     └─────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼                                               │
│  2. ANALYSIS (per conversation)                                              │
│     ┌─────────────────────────────────────────────────────────────────┐     │
│     │ pipeline.run_ci_analysis(conversation_id)                        │     │
│     │                                                                   │     │
│     │ AnnotatorSelector:                                                │     │
│     │   run_phrase_matcher_annotator: true                              │     │
│     │   phrase_matchers: [list of 5 resource names]                    │     │
│     │                                                                   │     │
│     │ CI scans every turn for every phrase                             │     │
│     │ Creates annotations with turn boundaries                         │     │
│     └─────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼                                               │
│  3. EXTRACTION (export to BQ)                                                │
│     ┌─────────────────────────────────────────────────────────────────┐     │
│     │ pipeline.export_ci_to_bq(conversation_id)                        │     │
│     │                                                                   │     │
│     │ Reads: analysis.call_analysis_metadata.annotations               │     │
│     │ Extracts: phrase_match_data fields                                │     │
│     │ Generates: ci_flags based on who said what                       │     │
│     │ Stores in: ci_enrichment.phrase_matches[]                        │     │
│     └─────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼                                               │
│  4. CONSUMPTION (ADK Coach)                                                  │
│     ┌─────────────────────────────────────────────────────────────────┐     │
│     │ Coach reads ci_enrichment and receives:                          │     │
│     │                                                                   │     │
│     │   ci_flags: ["AGENT_COMPLIANCE_VIOLATION", ...]                  │     │
│     │   phrase_matches: [                                               │     │
│     │     {matcher: "Compliance Violations", matches: [...]}           │     │
│     │   ]                                                               │     │
│     │                                                                   │     │
│     │ Coach uses these as HINTS to investigate with LLM reasoning      │     │
│     └─────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `cc_coach/services/phrase_matcher.py` | Phrase matcher definitions and GCP API |
| `cc_coach/services/insights.py` | CI analysis with phrase matcher config |
| `cc_coach/services/bigquery.py` | BQ schema for phrase_matches |
| `cc_coach/models/phrase_match.py` | Data models for phrase match results |

---

## BigQuery Schema

Phrase match results are stored in `ci_enrichment.phrase_matches`:

```sql
-- Schema
phrase_matches: RECORD (REPEATED)
├── matcher_id: STRING        -- e.g., "8420925564263523014"
├── display_name: STRING      -- e.g., "Compliance Violations"
├── match_count: INTEGER      -- e.g., 6
└── matches: RECORD (REPEATED)
    ├── phrase: STRING        -- The matcher display name
    ├── turn_index: INTEGER   -- Which turn (0-indexed)
    ├── speaker: STRING       -- "AGENT" or "CUSTOMER"
    └── text_snippet: STRING  -- Context from transcript

-- Additional fields
ci_flags: STRING (REPEATED)   -- ["AGENT_COMPLIANCE_VIOLATION", ...]
ci_flag_count: INTEGER        -- 3
```

### Query Example

```sql
SELECT
  conversation_id,
  ci_flags,
  pm.display_name as matcher,
  pm.match_count,
  m.turn_index,
  m.speaker,
  m.text_snippet
FROM `vertexdemo-481519.conversation_coach.ci_enrichment`,
UNNEST(phrase_matches) as pm,
UNNEST(pm.matches) as m
WHERE ci_flag_count > 0
ORDER BY conversation_id, pm.display_name, m.turn_index
```

---

## CLI Commands

```bash
# List all phrase matchers in GCP
cc-coach phrase-matcher list

# Show configured phrases (from code)
cc-coach phrase-matcher show-config

# Create all matchers (idempotent)
cc-coach phrase-matcher ensure

# Delete all matchers (use with caution)
cc-coach phrase-matcher delete-all

# Re-analyze all conversations with phrase matchers
cc-coach pipeline reanalyze-all
```

---

## CI vs LLM: When to Use What

| Aspect | CI Phrase Matcher | LLM/ADK Coach |
|--------|-------------------|---------------|
| **Speed** | Fast (milliseconds) | Slower (seconds) |
| **Cost** | Included in CI | Per-token cost |
| **Accuracy** | High for exact phrases | High for semantic meaning |
| **False positives** | Possible (no context) | Low (understands context) |
| **Use case** | First-pass flagging | Contextual judgment |

### Recommended Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  CI Phrase Matcher (Layer 1)                                     │
│  ────────────────────────────                                    │
│  Fast keyword detection → flags conversations                   │
│                                                                  │
│                    │                                             │
│                    ▼                                             │
│                                                                  │
│  LLM/ADK Coach (Layer 2)                                         │
│  ───────────────────────                                         │
│  Contextual analysis of flagged conversations                   │
│  "Was this really a threat, or appropriate disclosure?"         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Summary

1. **Phrase Matchers** = exact substring matching (like Ctrl+F)
2. **One rule = one phrase** - define each keyword separately
3. **Stored in GCP** - viewable in Console, managed via API
4. **5 matchers** configured for compliance, disclosures, empathy, escalation, vulnerability
5. **Results stored in BQ** - `ci_enrichment.phrase_matches[]`
6. **Use as first-pass filter** - LLM does contextual judgment
