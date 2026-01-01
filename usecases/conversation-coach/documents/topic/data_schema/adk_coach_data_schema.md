# ADK Coach Data Schema

This document defines the data schemas for the ADK Conversation Coach, including:
- **Input**: What the coach consumes from BQ (CI-enriched data)
- **Output**: What the coach produces (coaching analysis)

---

## BigQuery Tables Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      BQ TABLES: conversation_coach                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Project:  vertexdemo-481519                                                │
│  Dataset:  conversation_coach                                               │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ conversation_registry   │ Pipeline state tracking                   │    │
│  │                         │ Status: NEW → INGESTED → ENRICHED → COACHED│   │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ ci_enrichment          │ CI analysis output + raw transcript        │    │
│  │                         │ INPUT to ADK Coach                        │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ coach_analysis          │ Per-conversation coaching output          │    │
│  │                         │ OUTPUT from ADK Coach                     │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ daily_agent_summary     │ Daily aggregation per agent               │    │
│  │                         │ OUTPUT from Period Coach                  │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ weekly_agent_report     │ Weekly coaching report per agent          │    │
│  │                         │ OUTPUT from Period Coach                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW DIAGRAM                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  GCS (Raw Input)                                                             │
│  ┌──────────────────────────────────┐                                       │
│  │ gs://bucket/{date}/{conv_id}/    │                                       │
│  │   ├── transcription.json         │                                       │
│  │   └── metadata.json              │                                       │
│  └───────────────┬──────────────────┘                                       │
│                  │                                                           │
│                  ▼                                                           │
│  ┌──────────────────────────────────┐                                       │
│  │     CI (Contact Center AI)       │                                       │
│  │  ┌────────────────────────────┐  │                                       │
│  │  │ • Sentiment analysis       │  │                                       │
│  │  │ • Entity extraction        │  │                                       │
│  │  │ • Summarization           │  │                                       │
│  │  │ • Phrase matcher          │  │                                       │
│  │  └────────────────────────────┘  │                                       │
│  └───────────────┬──────────────────┘                                       │
│                  │                                                           │
│                  ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     BQ: ci_enrichment                                 │   │
│  │  ┌────────────────────────────────────────────────────────────────┐  │   │
│  │  │ • transcript (full text)                                        │  │   │
│  │  │ • customer_sentiment_score                                      │  │   │
│  │  │ • per_turn_sentiments[]                                         │  │   │
│  │  │ • phrase_matches[]                                              │  │   │
│  │  │ • ci_flags[]                                                    │  │   │
│  │  │ • labels (metadata)                                             │  │   │
│  │  └────────────────────────────────────────────────────────────────┘  │   │
│  └───────────────┬──────────────────────────────────────────────────────┘   │
│                  │                                                           │
│                  ▼  ADK COACH INPUT                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     ADK Conversation Coach                            │   │
│  │  ┌────────────────────────────────────────────────────────────────┐  │   │
│  │  │ Input:                        │ Output:                        │  │   │
│  │  │ • transcript                  │ • scores (empathy, compliance) │  │   │
│  │  │ • customer_sentiment          │ • assessments[] with evidence  │  │   │
│  │  │ • ci_flags                    │ • coaching_points[]            │  │   │
│  │  │ • phrase_matches              │ • issue_types[]                │  │   │
│  │  │ • labels (agent, queue)       │ • situation_summary            │  │   │
│  │  │ • policy context (RAG)        │ • key_moment                   │  │   │
│  │  └────────────────────────────────────────────────────────────────┘  │   │
│  └───────────────┬──────────────────────────────────────────────────────┘   │
│                  │                                                           │
│                  ▼  ADK COACH OUTPUT                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     BQ: coach_analysis                                │   │
│  │  (see schema below)                                                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## INPUT: ci_enrichment Schema

This is what the ADK Coach reads to generate coaching.

### Schema Definition

| Field | Type | Description |
|-------|------|-------------|
| `conversation_id` | STRING (REQUIRED) | Unique conversation identifier |
| `ci_conversation_name` | STRING | Full CI resource name |
| `transcript` | STRING | **Full transcript text** (Speaker.AGENT/CUSTOMER format) |
| `turn_count` | INTEGER | Number of conversation turns |
| `duration_sec` | INTEGER | Call duration in seconds |
| `customer_sentiment_score` | FLOAT | Overall customer sentiment (-1 to 1) |
| `customer_sentiment_magnitude` | FLOAT | Sentiment intensity |
| `per_turn_sentiments` | RECORD[] | Per-turn customer sentiment |
| `entities` | RECORD[] | Named entities extracted |
| `topics` | STRING[] | Topic labels |
| `ci_summary_text` | STRING | CI-generated summary |
| `ci_summary_resolution` | STRING | Resolution status |
| `phrase_matches` | RECORD[] | Phrase matcher results |
| `ci_flags` | STRING[] | Derived flags (AGENT_COMPLIANCE_VIOLATION, etc.) |
| `ci_flag_count` | INTEGER | Number of flags |
| `labels` | JSON | Original metadata (agent_id, queue, etc.) |
| `analysis_completed_at` | TIMESTAMP | When CI analysis completed |
| `exported_at` | TIMESTAMP | When exported to BQ |

### Nested Types

#### per_turn_sentiments

```json
{
  "turn_index": 3,
  "score": -0.5,
  "magnitude": 0.5
}
```

#### phrase_matches

```json
{
  "matcher_id": "8420925564263523014",
  "display_name": "Compliance Violations",
  "match_count": 6,
  "matches": [
    {
      "phrase": "Compliance Violations",
      "turn_index": 24,
      "speaker": "AGENT",
      "text_snippet": "Don't be dramatic. You could sell that car..."
    }
  ]
}
```

#### labels (JSON)

```json
{
  "agent_id": "M7741",
  "business_line": "COLLECTIONS",
  "call_outcome": "UNRESOLVED",
  "direction": "OUTBOUND",
  "queue": "HARDSHIP",
  "site": "MEL",
  "team": "COLLECTIONS_TEAM_3"
}
```

---

## INPUT: Real Data Example

### Conversation: Toxic Agent Test
**ID:** `a1b2c3d4-toxic-agent-test-0001`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ METADATA                                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ conversation_id:          a1b2c3d4-toxic-agent-test-0001                    │
│ turn_count:               39                                                 │
│ duration_sec:             630                                                │
│ customer_sentiment_score: -1.0                                               │
│                                                                              │
│ LABELS:                                                                      │
│   agent_id:       M7741                                                      │
│   business_line:  COLLECTIONS                                                │
│   queue:          HARDSHIP                                                   │
│   call_outcome:   UNRESOLVED                                                 │
│   team:           COLLECTIONS_TEAM_3                                         │
│   site:           MEL                                                        │
│   direction:      OUTBOUND                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ CI FLAGS                                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ • VULNERABILITY_DETECTED                                                     │
│ • CUSTOMER_ESCALATION                                                        │
│ • AGENT_COMPLIANCE_VIOLATION                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHRASE MATCHES                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ Vulnerability Indicators: 7 matches                                          │
│   Turn 4 (AGENT): "I've heard every excuse in the book. Medical bills..."   │
│   Turn 13 (CUSTOMER): "I had a medical emergency. My wife was in hospital.."│
│                                                                              │
│ Compliance Violations: 6 matches                                             │
│   Turn 16 (AGENT): "You couldn't be bothered to make payments..."           │
│   Turn 24 (AGENT): "Don't be dramatic. You could sell that car..."          │
│                                                                              │
│ Escalation Triggers: 3 matches                                               │
│   Turn 29 (CUSTOMER): "I'm going to file a complaint..."                    │
│   Turn 37 (CUSTOMER): "I'm recording this whole conversation..."            │
│                                                                              │
│ Required Disclosures: 1 matches                                              │
│   Turn 10 (AGENT): "Date of birth 15th March 1985..."                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ PER-TURN SENTIMENTS (customer only)                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ Turn 3:  score=-0.5, magnitude=0.5                                           │
│ Turn 5:  score=-1.0, magnitude=1.0                                           │
│ Turn 7:  score=-1.0, magnitude=1.0                                           │
│ Turn 9:  score=-1.0, magnitude=1.0                                           │
│ Turn 11: score=-1.0, magnitude=1.0                                           │
│ ...consistently negative throughout                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Transcript Sample (first 10 turns)

```
Speaker.AGENT: This is Marcus from Apex Collections calling for Michael Chen.
               Is this Michael?

Speaker.CUSTOMER: Yes, this is Michael. What's this about?

Speaker.AGENT: Mr Chen, I'm calling about your overdue account with FastCash
               Loans. You currently owe $12,847.50 and this account is now
               97 days past due. This is your seventh contact attempt.

Speaker.CUSTOMER: Right, yes, I know about this. Look, I've been meaning to
                  call you guys. I had some unexpected medical bills and I
                  lost my job back in October. I'm trying to get back on my feet.

Speaker.AGENT: Mr Chen, I've heard every excuse in the book. Medical bills,
               job loss, car problems. Everyone has a story. What I need from
               you right now is a commitment to pay. Can you pay the full
               amount today?

Speaker.CUSTOMER: The full amount? No, I just told you I lost my job. I can
                  maybe do $200 a month when I start my new position next week.

Speaker.AGENT: $200 a month? At that rate, you'll be paying this off for the
               next five years with all the interest and fees. That's not
               acceptable. I need at least $500 per month, starting today.

Speaker.CUSTOMER: I don't have $500! Are you not listening to me? My wife was
                  in the hospital, I lost my income—

Speaker.AGENT: I am listening, Mr Chen. But what you're not understanding is
               the seriousness of this. We're talking about legal action here.
               We can garnish your wages, put a lien on your property. Do you
               own your home at 47 Parkview Crescent, Burwood?

Speaker.CUSTOMER: What? How do you know my address? Is that a threat?

Speaker.AGENT: I'm not threatening anything. I'm informing you of the
               consequences. And yes, we have all your details. Date of birth
               15th March 1985, mobile 0412 555 789, employer... well, former
               employer... Westfield Group. We know everything, Mr Chen.
```

---

## OUTPUT: coach_analysis Schema

This is what the ADK Coach produces.

### Schema Location

```
cc_coach/schemas/coach_analysis.json
```

### Schema Version

```
Version: 2.1.0
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| **Identifiers** | | |
| `conversation_id` | STRING (REQUIRED) | Links to ci_enrichment |
| `agent_id` | STRING (REQUIRED) | Agent for aggregation |
| `business_line` | STRING | COLLECTIONS or LOANS |
| `team` | STRING | Team identifier |
| `queue` | STRING | Queue type |
| **Scores (1-10)** | | |
| `empathy_score` | INTEGER | Agent empathy |
| `compliance_score` | INTEGER | Compliance adherence |
| `resolution_score` | INTEGER | Problem resolution |
| `professionalism_score` | INTEGER | Professionalism |
| `de_escalation_score` | INTEGER | De-escalation skill |
| `efficiency_score` | INTEGER | Call efficiency |
| `overall_score` | FLOAT | Weighted average |
| **Evidence-Based Assessments** | | |
| `assessments[]` | RECORD | Per-dimension with evidence |
| `assessments[].dimension` | STRING | empathy, compliance, etc. |
| `assessments[].score` | INTEGER | Score for this dimension |
| `assessments[].issue_types[]` | STRING | Issues found |
| `assessments[].evidence[]` | RECORD | Quotes + turn numbers |
| `assessments[].coaching_point` | STRING | Specific advice |
| **Issues** | | |
| `issue_types[]` | STRING | All issues found |
| `critical_issues[]` | STRING | CRITICAL severity only |
| `issue_count` | INTEGER | Total issues |
| `compliance_breach_count` | INTEGER | Compliance breaches |
| **Call Context** | | |
| `call_type` | STRING | hardship, complaint, payment, etc. |
| `call_outcome` | STRING | From metadata |
| `resolution_achieved` | BOOLEAN | Was issue resolved? |
| `escalation_required` | BOOLEAN | Needed escalation? |
| `customer_started_negative` | BOOLEAN | Initial sentiment |
| **Coaching Output** | | |
| `coaching_summary` | STRING | 2-3 sentence summary |
| `coaching_points[]` | STRING | Specific recommendations |
| `strengths[]` | STRING | Identified strengths |
| `situation_summary` | STRING | What the call was about |
| `behavior_summary` | STRING | How agent handled it |
| `key_moment` | RECORD | Most notable moment |
| `example_type` | STRING | GOOD_EXAMPLE or NEEDS_WORK |
| **Lineage** | | |
| `ci_flags[]` | STRING | CI phrase matcher flags |
| `policy_citations[]` | RECORD | Policy sections cited |
| `model_version` | STRING | LLM model used |
| `prompt_version` | STRING | Prompt version used |
| `analyzed_at` | TIMESTAMP | When analysis ran |

### Evidence Structure

```json
{
  "dimension": "compliance",
  "score": 2,
  "issue_types": ["THREAT_LEGAL_ACTION", "HARASSMENT", "PRIVACY_VIOLATION"],
  "evidence": [
    {
      "turn_index": 8,
      "speaker": "AGENT",
      "quote": "We're talking about legal action here. We can garnish your wages...",
      "issue_type": "THREAT_LEGAL_ACTION",
      "severity": "CRITICAL"
    },
    {
      "turn_index": 24,
      "speaker": "AGENT",
      "quote": "Don't be dramatic. You could sell that car of yours...",
      "issue_type": "HARASSMENT",
      "severity": "HIGH"
    }
  ],
  "coaching_point": "Never threaten legal action to pressure customers. Instead, focus on understanding their situation and offering hardship options."
}
```

### Expected Output Example (for toxic agent)

```json
{
  "conversation_id": "a1b2c3d4-toxic-agent-test-0001",
  "agent_id": "M7741",
  "business_line": "COLLECTIONS",
  "queue": "HARDSHIP",

  "empathy_score": 1,
  "compliance_score": 2,
  "resolution_score": 1,
  "professionalism_score": 2,
  "de_escalation_score": 1,
  "overall_score": 1.4,

  "issue_types": [
    "THREAT_LEGAL_ACTION",
    "HARASSMENT",
    "DISMISSIVE_LANGUAGE",
    "PRIVACY_VIOLATION",
    "MISSING_HARDSHIP_OFFER",
    "NO_EMPATHY"
  ],
  "critical_issues": ["THREAT_LEGAL_ACTION", "HARASSMENT"],
  "issue_count": 6,
  "compliance_breach_count": 3,

  "call_type": "hardship",
  "call_outcome": "UNRESOLVED",
  "resolution_achieved": false,
  "escalation_required": true,
  "customer_started_negative": false,

  "coaching_summary": "This call demonstrates multiple serious compliance breaches. The agent used threatening language, dismissed the customer's legitimate hardship situation, and failed to offer any payment options or hardship provisions despite the customer explicitly mentioning job loss and medical bills.",

  "coaching_points": [
    "Never threaten legal action as a pressure tactic",
    "Acknowledge customer hardship with empathy before discussing options",
    "Always offer hardship provisions when customer mentions financial difficulty",
    "Avoid dismissive phrases like 'I've heard every excuse' or 'Don't be dramatic'",
    "Do not mention customer's personal details (address, DOB) in a threatening manner"
  ],

  "strengths": [],

  "situation_summary": "Customer called regarding overdue account, disclosed job loss and wife's hospitalization",

  "behavior_summary": "Agent was aggressive, dismissive, and threatening throughout the call",

  "key_moment": {
    "turn_index": 8,
    "quote": "We're talking about legal action here. We can garnish your wages, put a lien on your property.",
    "why_notable": "Agent threatened legal action before offering any hardship options - clear compliance violation"
  },

  "example_type": "NEEDS_WORK",

  "ci_flags": ["VULNERABILITY_DETECTED", "CUSTOMER_ESCALATION", "AGENT_COMPLIANCE_VIOLATION"],

  "policy_citations": [
    {
      "policy_id": "COMPLIANCE_2025_V1",
      "section_id": "SEC_002",
      "relevance": "Prohibition on threatening language"
    }
  ],

  "model_version": "gemini-2.0-flash",
  "prompt_version": "coach_v1.0"
}
```

---

## Issue Types Reference

### Compliance Issues

| Issue Type | Severity | Description |
|------------|----------|-------------|
| `THREAT_LEGAL_ACTION` | CRITICAL | Threatening legal action without proper process |
| `HARASSMENT` | CRITICAL | Harassing or bullying behavior |
| `PRIVACY_VIOLATION` | HIGH | Inappropriate use of customer data |
| `MISSING_REQUIRED_DISCLOSURE` | HIGH | Failed to mention required disclosures |
| `MISSING_HARDSHIP_OFFER` | HIGH | Didn't offer hardship options when indicated |
| `MISLEADING_INFORMATION` | HIGH | Provided incorrect information |

### Behavior Issues

| Issue Type | Severity | Description |
|------------|----------|-------------|
| `NO_EMPATHY` | MEDIUM | Failed to acknowledge customer situation |
| `DISMISSIVE_LANGUAGE` | MEDIUM | Used dismissive phrases |
| `INTERRUPTING` | LOW | Frequently interrupted customer |
| `CONDESCENDING_TONE` | MEDIUM | Spoke down to customer |
| `FAILED_DE_ESCALATION` | HIGH | Made escalating situation worse |

### Positive Indicators

| Indicator | Description |
|-----------|-------------|
| `STRONG_EMPATHY` | Excellent acknowledgment of situation |
| `GOOD_DE_ESCALATION` | Successfully calmed upset customer |
| `PROPER_DISCLOSURE` | All required disclosures made |
| `CREATIVE_SOLUTION` | Found innovative resolution |
| `HARDSHIP_HANDLED_WELL` | Properly processed hardship case |

---

## Schema-as-Code Locations

### Input Schemas (GCS raw data)

```
/artifacts/schemas/
├── metadata.schema.json      # Call metadata JSON schema
└── transcription.schema.json # Transcript JSON schema
```

### BQ Table Schemas

```
/artifacts/cli/cc_coach/services/bigquery.py
├── REGISTRY_SCHEMA           # conversation_registry
└── CI_ENRICHMENT_SCHEMA      # ci_enrichment

/artifacts/cli/cc_coach/schemas/
├── coach_analysis.json       # coach_analysis (v2.1.0)
├── daily_agent_summary.json  # daily aggregation
└── weekly_agent_report.json  # weekly report
```

---

## SQL Query Examples

### Get coach input for a conversation

```sql
SELECT
  conversation_id,
  transcript,
  turn_count,
  duration_sec,
  customer_sentiment_score,
  ci_flags,
  phrase_matches,
  labels
FROM `vertexdemo-481519.conversation_coach.ci_enrichment`
WHERE conversation_id = 'a1b2c3d4-toxic-agent-test-0001'
  AND ci_flag_count > 0  -- Get row with phrase matches
LIMIT 1
```

### Get conversations pending coaching

```sql
SELECT
  r.conversation_id,
  r.status,
  e.turn_count,
  e.ci_flags,
  JSON_VALUE(e.labels, '$.agent_id') as agent_id
FROM `vertexdemo-481519.conversation_coach.conversation_registry` r
LEFT JOIN `vertexdemo-481519.conversation_coach.ci_enrichment` e
  ON r.conversation_id = e.conversation_id
WHERE r.status = 'ENRICHED'
  AND r.coached_at IS NULL
ORDER BY r.enriched_at ASC
```

### Aggregate coach results by agent

```sql
SELECT
  agent_id,
  COUNT(*) as call_count,
  AVG(empathy_score) as avg_empathy,
  AVG(compliance_score) as avg_compliance,
  SUM(compliance_breach_count) as total_breaches,
  ARRAY_AGG(DISTINCT issue ORDER BY issue) as all_issues
FROM `vertexdemo-481519.conversation_coach.coach_analysis`,
UNNEST(issue_types) as issue
GROUP BY agent_id
ORDER BY total_breaches DESC
```

---

## Current State

| Table | Rows | Notes |
|-------|------|-------|
| conversation_registry | 9 | All dev conversations |
| ci_enrichment | ~18 | Multiple rows per conversation (re-analyses) |
| coach_analysis | 0 | **ADK coach not implemented yet** |
| daily_agent_summary | 0 | **Period coach not implemented yet** |
| weekly_agent_report | 0 | **Period coach not implemented yet** |

---

## Next Steps

1. **Implement ADK Conversation Coach**
   - Read from `ci_enrichment`
   - Generate coaching using Gemini
   - Write to `coach_analysis`

2. **Implement Period Coach**
   - Aggregate `coach_analysis` by agent
   - Generate daily/weekly summaries
   - Write to `daily_agent_summary` and `weekly_agent_report`
