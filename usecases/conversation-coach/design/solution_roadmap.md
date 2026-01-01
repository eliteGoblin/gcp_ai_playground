# AI Coach Solution Roadmap

## Overview

This document provides a progressive, pragmatic roadmap to build an AI coaching system for contact center agents. The approach follows **KISS principles**: build simple, working pieces first, then layer complexity.

---

## The Big Picture: Multi-Level Coaching

"Multi-level" means coaching at different time granularities, where each level builds on the previous:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MULTI-LEVEL COACHING                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Per-Conversation         Daily              Weekly           Monthly   │
│   ────────────────         ─────              ──────           ───────   │
│                                                                          │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────┐ │
│   │ Transcript   │    │ Aggregated   │    │ Daily        │    │Weekly │ │
│   │ (raw)        │───▶│ metrics      │───▶│ summaries    │───▶│reports│ │
│   │ ~3K tokens   │    │ ~500 tokens  │    │ ~1K tokens   │    │~2K tok│ │
│   └──────────────┘    └──────────────┘    └──────────────┘    └───────┘ │
│          │                   │                   │                 │     │
│          ▼                   ▼                   ▼                 ▼     │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────┐ │
│   │ Detailed     │    │ Daily digest │    │ Weekly       │    │Monthly│ │
│   │ coaching     │    │ for agent    │    │ report +     │    │trends │ │
│   │ feedback     │    │              │    │ action plan  │    │       │ │
│   └──────────────┘    └──────────────┘    └──────────────┘    └───────┘ │
│                                                                          │
│   BUILD FIRST ◀────────────────────────────────────────▶ BUILD LATER    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key insight**: You don't send raw transcripts to higher levels. You send pre-computed metrics and summaries. This solves the context window problem.

---

## System Thinking Approach

Before diving into implementation, understand the system through these views:

### View 1: Data Flow (What data goes where)
```
Transcript → Per-Conv Coach → Scores/Issues → BQ → Aggregation → Period Coach → Report
```

### View 2: Time Sequence (When things happen)
```
Call ends → Minutes later: Per-conv coaching → End of day: Daily summary → End of week: Weekly report
```

### View 3: Storage Pyramid (What gets stored at each level)
```
                    ┌─────────────┐
                    │   Monthly   │  ← Highly compressed (trends only)
                    │   ~1 row    │
                    ├─────────────┤
                    │   Weekly    │  ← Compressed (weekly per agent)
                    │   ~4 rows   │
                    ├─────────────┤
                    │    Daily    │  ← Semi-compressed (daily per agent)
                    │  ~20 rows   │
                    ├─────────────┤
                    │ Per-Convo   │  ← Detailed (one per conversation)
                    │ ~400 rows   │
                    ├─────────────┤
                    │    Raw      │  ← Full transcripts
                    │   (GCS)     │
                    └─────────────┘
```

---

## Phase Overview

| Phase | Deliverable | Input | Output | Status |
|-------|-------------|-------|--------|--------|
| **0** | CI Pipeline + Phrase Matchers | Transcripts | CI enrichment in BQ | ✅ DONE |
| **1** | Per-Conversation Coach | Transcript + CI + RAG | Scores + coaching | 🔄 CURRENT |
| **2** | Daily Summary | Day's coach_analysis | Daily digest | Next |
| **3** | Weekly Report + Dashboard | Week's data | Report + viz | MVP |
| **4** | Evaluation Framework | Coach outputs | Metrics + calibration | Post-MVP |
| **5** | Monitoring & Alerting | Pipeline metrics | Dashboards + alerts | Post-MVP |
| **6** | FinOps | Token usage | Cost tracking + optimization | Post-MVP |

**MVP Definition**: Bot can do per-conversation coaching, daily summary, and weekly summary with RAG.

**Design Documents:**
- Phase 1: `design/phase1_adk_conversation_coach.md`
- Phase 4: `design/evaluation_framework.md`

---

## Synthetic Data Generation (ADK Multi-Agent)

### Why Synthetic Data?

| Need | Current State | Required |
|------|---------------|----------|
| Test per-conversation coach | 9 dev conversations | 50+ for validation |
| Test daily aggregation | Need 1 agent × 20 calls | 3 agents × 20 calls × 5 days |
| Test weekly aggregation | Need 1 week of data | ~300-600 conversations |
| Evaluation baseline | None | 100+ labeled conversations |

### Multi-Agent Conversation Generator

Use ADK to create realistic conversations between two agents:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 SYNTHETIC CONVERSATION GENERATOR                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Scenario Config (JSON)                                               │    │
│  │ ─────────────────────                                                │    │
│  │ {                                                                    │    │
│  │   "scenario_id": "HARDSHIP_DEESCALATION_001",                       │    │
│  │   "customer_persona": "angry_but_genuine_hardship",                 │    │
│  │   "agent_persona": "empathetic_compliant",                          │    │
│  │   "expected_outcome": "payment_plan_agreed",                        │    │
│  │   "expected_issues": [],                                            │    │
│  │   "expected_scores": {"empathy": 8, "compliance": 9}                │    │
│  │ }                                                                    │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │                                            │
│                                 ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                       │   │
│  │   ┌─────────────────┐         ┌─────────────────┐                    │   │
│  │   │ CustomerAgent   │◀───────▶│ CollectorAgent  │                    │   │
│  │   │ (ADK)           │  turns  │ (ADK)           │                    │   │
│  │   │                 │         │                 │                    │   │
│  │   │ Persona:        │         │ Persona:        │                    │   │
│  │   │ • Debt amount   │         │ • Experience    │                    │   │
│  │   │ • Hardship type │         │ • Compliance    │                    │   │
│  │   │ • Emotional     │         │ • Empathy level │                    │   │
│  │   │   state         │         │ • Skills        │                    │   │
│  │   │ • Goals         │         │ • Flaws         │                    │   │
│  │   └─────────────────┘         └─────────────────┘                    │   │
│  │                                                                       │   │
│  │   Orchestrator runs multi-turn conversation until:                   │   │
│  │   • Resolution reached, or                                           │   │
│  │   • Max turns (30-40), or                                           │   │
│  │   • Escalation triggered                                             │   │
│  │                                                                       │   │
│  └───────────────────────────────┬──────────────────────────────────────┘   │
│                                  │                                           │
│                                  ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Output                                                               │    │
│  │ ──────                                                               │    │
│  │ • transcript.json (same format as real data)                        │    │
│  │ • metadata.json (agent_id, scenario, etc.)                          │    │
│  │ • expected_labels.json (ground truth for evaluation)                │    │
│  │   ├── expected_scores: {empathy: 8, compliance: 9, ...}            │    │
│  │   ├── expected_issues: ["MISSING_DISCLOSURE"]                       │    │
│  │   └── expected_flags: {resolution: true, escalation: false}        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Personas

**Customer Personas:**

| Persona | Description | Expected Agent Response |
|---------|-------------|------------------------|
| `angry_but_genuine_hardship` | Lost job, frustrated, needs help | De-escalation + hardship offer |
| `hostile_refusing` | Denies debt, threatens complaint | Stay calm, offer dispute process |
| `cooperative_payment` | Wants to pay, needs options | Offer payment plans |
| `vulnerable_elderly` | Confused, mentions health issues | Extra patience, hardship path |
| `wrong_party` | Not the account holder | Immediate end, no disclosure |
| `dispute_already_paid` | Claims debt was paid | Acknowledge, offer investigation |

**Agent Personas (Collector):**

| Persona | Description | Expected Coaching |
|---------|-------------|-------------------|
| `empathetic_compliant` | Model behavior | High scores, use as GOOD_EXAMPLE |
| `compliant_but_robotic` | Follows rules, no empathy | Coach on empathy |
| `pushy_but_legal` | Aggressive, borderline | Coach on tone |
| `toxic_violations` | Threatens, harasses | CRITICAL issues, compliance training |
| `rushed_incomplete` | Misses disclosures | Coach on required disclosures |
| `new_agent_nervous` | Hesitant, inefficient | Coach on confidence |

### Generation Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SYNTHETIC DATA GENERATION PLAN                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  For Weekly Aggregation Test (600 conversations):                           │
│  ────────────────────────────────────────────────                           │
│                                                                              │
│  3 Agents × 5 Days × 40 Calls/Day = 600 conversations                       │
│                                                                              │
│  Agent Distribution:                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │ Agent A1001 (Good Empathy, Weak Compliance)                        │     │
│  │ ├── 60% normal scenarios → scores 7-8                              │     │
│  │ ├── 30% hardship scenarios → high empathy, some disclosure misses │     │
│  │ └── 10% difficult customers → good de-escalation                   │     │
│  │                                                                     │     │
│  │ Agent A1002 (Strong Compliance, Struggles with Anger)              │     │
│  │ ├── 60% normal scenarios → scores 7-8                              │     │
│  │ ├── 20% angry customers → failed de-escalation                     │     │
│  │ └── 20% compliance-heavy → perfect compliance, low empathy        │     │
│  │                                                                     │     │
│  │ Agent A1003 (Balanced, Occasional Efficiency Issues)               │     │
│  │ ├── 70% normal scenarios → scores 7-8                              │     │
│  │ ├── 20% complex cases → some resolution issues                     │     │
│  │ └── 10% exemplary calls → GOOD_EXAMPLE candidates                  │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  Expected Weekly Report Narrative:                                           │
│  • A1001: "Strong empathy but missed disclosures 12 times"                  │
│  • A1002: "Excellent compliance, work on de-escalation skills"              │
│  • A1003: "Consistent performer, minor efficiency improvements"             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Evaluation Data vs Training Data

| Type | Purpose | With Labels? | Volume |
|------|---------|--------------|--------|
| **Training Data** | Test pipeline works | No | 100+ |
| **Evaluation Data** | Measure coach accuracy | Yes (ground truth) | 100-200 |
| **Regression Set** | Prevent quality drift | Yes (fixed set) | 50 curated |

**Evaluation Data Format:**

```json
{
  "conversation_id": "SYNTH-EVAL-001",
  "scenario_id": "HARDSHIP_DEESCALATION_001",
  "transcript": "...",
  "metadata": {...},

  "ground_truth": {
    "empathy_score": 8,
    "compliance_score": 9,
    "resolution_score": 8,
    "expected_issues": [],
    "expected_flags": {
      "resolution_achieved": true,
      "escalation_required": false
    },
    "notable_turns": [
      {"turn": 6, "label": "good_empathy_statement"},
      {"turn": 12, "label": "hardship_offer_made"}
    ]
  },

  "evaluation_criteria": {
    "empathy_tolerance": 1,
    "compliance_tolerance": 1,
    "must_detect_issues": [],
    "must_not_flag": ["THREAT_LEGAL_ACTION"]
  }
}
```

### CLI Commands (Future)

```bash
# Generate synthetic conversations
cc-coach synth generate \
  --agents 3 \
  --days 5 \
  --calls-per-day 40 \
  --output-dir artifacts/data/synth/

# Generate evaluation set with labels
cc-coach synth generate-eval \
  --scenarios evaluation_scenarios.yaml \
  --count 100 \
  --output-dir artifacts/data/eval/

# Run evaluation against ground truth
cc-coach eval run \
  --eval-set artifacts/data/eval/ \
  --output-report reports/eval_2025-01-15.json
```

### Benefits of Multi-Agent Generation

1. **Realistic Conversations**: LLM-generated dialogue is more natural than templates
2. **Controlled Scenarios**: Define exactly what issues should appear
3. **Ground Truth Labels**: Know expected scores for evaluation
4. **Scalable**: Generate 1000s of conversations cheaply
5. **Reproducible**: Same seed + scenario = same conversation
6. **Edge Cases**: Create rare scenarios (suicide mention, threats) safely

---

## CI + ADK Integration Architecture

The coaching system uses **both** CCAI Insights (CI) and ADK/LLM, each for what they do best:

### What CI Does vs What ADK Does

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CI vs ADK ROLES                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CI (Fast, Cheap, Consistent)              ADK Coach (Smart, Contextual)    │
│  ─────────────────────────────             ─────────────────────────────    │
│                                                                              │
│  ✅ Customer sentiment                     ✅ Agent behavior assessment     │
│  ✅ Keyword detection (phrase matcher)     ✅ Contextual compliance judging │
│  ✅ Call summary (situation/action/result) ✅ Empathy/professionalism scoring│
│  ✅ Topic modeling (for dashboard)         ✅ Coaching recommendations      │
│  ✅ QA Scorecard (at scale, 2K+ samples)   ✅ Policy interpretation (RAG)   │
│                                                                              │
│  ❌ Agent sentiment/tone analysis          ✅ Agent sentiment/tone analysis │
│  ❌ Contextual compliance (gray areas)     ✅ Reason about gray areas       │
│  ❌ Generate coaching tips                 ✅ Personalized coaching         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Complete Data Flow: CI + ADK

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CI + ADK COACH INTEGRATION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  LAYER 1: CI Pre-processing (Fast, Cheap, Consistent)                       │
│  ─────────────────────────────────────────────────────                       │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │ Sentiment       │  │ Phrase Matcher  │  │ Summarization   │              │
│  │ Analysis        │  │ (Compliance     │  │ (Situation/     │              │
│  │                 │  │  Keywords)      │  │  Action/Result) │              │
│  │ • Customer      │  │                 │  │                 │              │
│  │   sentiment     │  │ • "legal action"│  │ • Call notes    │              │
│  │ • Per-turn      │  │ • "sue you"     │  │ • Quick summary │              │
│  │   journey       │  │ • "garnish"     │  │                 │              │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘              │
│           │                    │                    │                        │
│           └────────────────────┼────────────────────┘                        │
│                                │                                             │
│                                ▼                                             │
│                      ┌─────────────────────┐                                │
│                      │ ci_enrichment (BQ)  │                                │
│                      │                     │                                │
│                      │ • sentiment_score   │                                │
│                      │ • phrase_matches[]  │                                │
│                      │ • summary_text      │                                │
│                      │ • entities[]        │                                │
│                      └──────────┬──────────┘                                │
│                                 │                                            │
│  LAYER 2: ADK Coach (Smart, Contextual, Coaching)                           │
│  ────────────────────────────────────────────────                           │
│                                 │                                            │
│                                 ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                       │   │
│  │   ┌─────────────────┐        ┌─────────────────────────────────────┐ │   │
│  │   │ Input to Coach  │        │ Conversation Coach (LLM)            │ │   │
│  │   │ ────────────────│        │                                     │ │   │
│  │   │ • transcript    │───────▶│ 1. Assess agent behavior            │ │   │
│  │   │ • CI sentiment  │        │ 2. Check compliance (contextual)    │ │   │
│  │   │ • CI phrases    │◀─ flag │ 3. Score empathy, professionalism   │ │   │
│  │   │ • CI summary    │        │ 4. Generate coaching points         │ │   │
│  │   │ • metadata      │        │ 5. Reference policy (RAG)           │ │   │
│  │   │ • policy (RAG)  │        │                                     │ │   │
│  │   └─────────────────┘        └──────────────────┬──────────────────┘ │   │
│  │                                                 │                     │   │
│  │                                                 ▼                     │   │
│  │                              ┌─────────────────────────────────────┐ │   │
│  │                              │ coach_analysis (BQ)                 │ │   │
│  │                              │                                     │ │   │
│  │                              │ • empathy_score (LLM assessed)      │ │   │
│  │                              │ • compliance_score (LLM judged)     │ │   │
│  │                              │ • agent_issues[] (LLM identified)   │ │   │
│  │                              │ • coaching_points[] (LLM generated) │ │   │
│  │                              │ • compliance_checks[] (with policy) │ │   │
│  │                              └─────────────────────────────────────┘ │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  LAYER 3: Aggregation (SQL + LLM Period Coaches)                            │
│  ───────────────────────────────────────────────                            │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                                                                     │     │
│  │  coach_analysis ──▶ SQL Aggregate ──▶ Daily Coach ──▶ daily_summary│     │
│  │  (20 rows/day)      (metrics)         (LLM)          (1 row)       │     │
│  │                                                                     │     │
│  │  daily_summary ──▶ SQL Aggregate ──▶ Weekly Coach ──▶ weekly_report│     │
│  │  (7 rows/week)      (trends)          (LLM)          (1 row)       │     │
│  │                                                                     │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  LAYER 4: Dashboard (Looker Studio)                                         │
│  ──────────────────────────────────                                         │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  ┌─────────────────────┐     ┌─────────────────────┐               │     │
│  │  │ Agent Radar Chart   │     │ Call Drivers        │               │     │
│  │  │      Empathy        │     │ ┌─────────────────┐ │               │     │
│  │  │         ●           │     │ │ Payment Plans 32%│ │               │     │
│  │  │        /|\          │     │ │ Hardship      28%│ │               │     │
│  │  │       / | \         │     │ │ Disputes      18%│ │               │     │
│  │  │ Compliance Resolution│     │ └─────────────────┘ │               │     │
│  │  └─────────────────────┘     └─────────────────────┘               │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Progressive Implementation Roadmap

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PROGRESSIVE CI + ADK ROADMAP                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Done               Current             MVP Complete        Future (Scale)  │
│  ──────             ───────             ────────────        ──────────────  │
│                                                                              │
│  ┌────────────┐    ┌────────────┐     ┌────────────┐     ┌────────────┐    │
│  │ CI Setup   │    │ Per-Conv   │     │ Daily +    │     │ Topic Model│    │
│  │ ✅ Sentiment│───▶│ ADK Coach  │────▶│ Weekly     │────▶│ QA Scorecard│   │
│  │ ✅ Summary  │    │ + RAG      │     │ Summaries  │     │ Evaluation │    │
│  │ ✅ Phrase   │    │            │     │            │     │            │    │
│  │   Matchers │    │            │     │            │     │ (1000-2000+│    │
│  └────────────┘    └────────────┘     └────────────┘     │  convos)   │    │
│       ✓                 ◀── CURRENT         MVP              └────────────┘    │
│                           FOCUS                                              │
│                                                                              │
│  Pipeline +         Conversation        + Daily digest    Production scale  │
│  CI integration     coaching works      + Weekly report   + Evaluation      │
│                                         + Dashboard       framework         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Phase 1 CI Features (DONE)

| Feature | Status | Training Required |
|---------|--------|-------------------|
| Sentiment Analysis | ✅ Enabled | None |
| Summarization | ✅ Enabled | None |
| Entity Extraction | ✅ Enabled | None |
| **Phrase Matcher** | ✅ Implemented | None (rule-based) |

### Phrase Matcher Configuration (Phase 1)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHRASE MATCHERS TO CREATE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Matcher: "compliance_violations"          Matcher: "required_disclosures"  │
│  ─────────────────────────────────         ───────────────────────────────  │
│  • "legal action"                          • "right to dispute"             │
│  • "sue you"                               • "hardship program"             │
│  • "take you to court"                     • "financial hardship"           │
│  • "garnish your wages"                    • "payment arrangement"          │
│  • "seize your property"                   • "payment plan"                 │
│                                                                              │
│  Matcher: "empathy_indicators"             Matcher: "escalation_triggers"   │
│  ─────────────────────────────             ──────────────────────────────   │
│  • "I understand"                          • "speak to supervisor"          │
│  • "that must be difficult"                • "make a complaint"             │
│  • "I appreciate you sharing"              • "report this"                  │
│  • "let me help"                           • "not acceptable"               │
│  • "I'm sorry to hear"                     • "unacceptable"                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Phrase Matcher Output (Per-Conversation)

```json
{
  "conversation_id": "a1b2c3d4-toxic-agent-test-0001",
  "phrase_matches": {
    "compliance_violations": {
      "found": true,
      "count": 2,
      "matches": [
        {"phrase": "legal action", "turn": 15, "speaker": "AGENT"},
        {"phrase": "garnish your wages", "turn": 23, "speaker": "AGENT"}
      ]
    },
    "required_disclosures": {
      "found": false,
      "count": 0,
      "matches": []
    },
    "empathy_indicators": {
      "found": false,
      "count": 0,
      "matches": []
    },
    "escalation_triggers": {
      "found": true,
      "count": 1,
      "matches": [
        {"phrase": "make a complaint", "turn": 31, "speaker": "CUSTOMER"}
      ]
    }
  },
  "ci_flags": {
    "has_compliance_violations": true,
    "missing_required_disclosures": true,
    "no_empathy_shown": true,
    "customer_escalated": true
  }
}
```

### Policy RAG Structure

```
RAG Knowledge Base:
├── Official Compliance (External)
│   ├── ASIC Guidelines
│   │   ├── Debt Collection Guidelines
│   │   ├── Hardship Provisions
│   │   └── Consumer Protection Rules
│   └── Industry Standards
│
├── Corporate Compliance (Internal, Versioned)
│   ├── compliance_policy_v2024.1.md
│   ├── compliance_policy_v2025.1.md  ← Current
│   └── Metadata: effective_date, business_line
│
├── Coaching Playbooks (Versioned)
│   ├── de_escalation_playbook_v1.md
│   ├── hardship_handling_v2.md
│   └── collections_best_practices_v3.md
│
└── Retrieval Strategy
    ├── Filter by: business_line, effective_date
    ├── Chunk by section (~300-500 tokens)
    └── Cite: section_id in compliance checks
```

---

## Phase 0: Current State (DONE)

### What Exists
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Local/GCS    │────▶│ CCAI Insights│────▶│ BigQuery     │     │              │
│ transcripts  │     │ (sentiment,  │     │ ci_enrichment│     │ (not built)  │
│ + metadata   │     │  entities)   │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
     ✅                    ✅                   ✅                   ❌
```

### Current Tables
- `conversation_registry` - Pipeline state tracking
- `ci_enrichment` - CI analysis results (sentiment, entities, topics)
- `coaching_cards` - Schema exists, but EMPTY (no coach implemented yet)

---

## Phase 1: Per-Conversation Coach (MVP)

### Goal
For each conversation, generate detailed coaching feedback with scores.

### Data Flow
```
┌─────────────────────────────────────────────────────────────────────────┐
│                     PER-CONVERSATION COACHING                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐                                                     │
│  │ ci_enrichment   │                                                     │
│  │ ─────────────── │                                                     │
│  │ - transcript    │──┐                                                  │
│  │ - sentiment     │  │                                                  │
│  │ - turn_count    │  │     ┌──────────────────────┐                    │
│  └─────────────────┘  │     │                      │                    │
│                       ├────▶│  Conversation Coach  │                    │
│  ┌─────────────────┐  │     │  (LLM - Gemini)      │                    │
│  │ conversation_   │  │     │                      │                    │
│  │ registry        │──┘     │  System Prompt:      │                    │
│  │ ─────────────── │        │  - Score empathy     │                    │
│  │ - agent_id      │        │  - Score compliance  │                    │
│  │ - call_outcome  │        │  - Identify issues   │                    │
│  │ - queue         │        │  - Give coaching pts │                    │
│  └─────────────────┘        └──────────┬───────────┘                    │
│                                        │                                 │
│                                        ▼                                 │
│                             ┌──────────────────────┐                    │
│                             │ coach_analysis       │                    │
│                             │ ────────────────     │                    │
│                             │ - empathy_score      │                    │
│                             │ - compliance_score   │                    │
│                             │ - resolution_score   │                    │
│                             │ - agent_issues[]     │                    │
│                             │ - coaching_points[]  │                    │
│                             │ - situation_summary  │                    │
│                             └──────────────────────┘                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Schema: coach_analysis (Evidence-Based)

**Core Principle**: Scores alone are meaningless. Every score needs:
- **Issue Type** (categorical, for pattern detection)
- **Evidence** (quotes from transcript, for proof and coaching)
- **Coaching Point** (actionable advice)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  WHY EVIDENCE-BASED?                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SCORE-ONLY (❌ Bad):                                                       │
│  empathy_score: 3                                                            │
│  → "Your empathy could improve" (but WHY? what did agent do wrong?)         │
│                                                                              │
│  EVIDENCE-BASED (✅ Good):                                                  │
│  empathy_score: 3                                                            │
│  issue_types: ["DISMISSIVE_LANGUAGE", "NO_ACKNOWLEDGMENT"]                  │
│  evidence: [                                                                 │
│    {turn: 4, quote: "I've heard every excuse in the book", severity: HIGH}  │
│    {turn: 14, quote: "not our problem", severity: MEDIUM}                   │
│  ]                                                                           │
│  coaching_point: "Acknowledge customer's situation before discussing payment"│
│                                                                              │
│  → Now coach can say: "On Turn 4, saying 'heard every excuse' was dismissive.│
│     Try: 'I understand this is difficult' before asking about payment."     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Issue Type Taxonomy (Enables Pattern Detection)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ISSUE TYPE TAXONOMY                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  EMPATHY ISSUES:                                                             │
│  ├── DISMISSIVE_LANGUAGE        "heard every excuse"                        │
│  ├── NO_ACKNOWLEDGMENT          Didn't acknowledge hardship                 │
│  ├── RUSHING_CUSTOMER           Cut customer off, hurried                   │
│  ├── BLAME_SHIFTING             "that's your responsibility"                │
│  └── LACK_OF_PATIENCE           Short responses, sighing                    │
│                                                                              │
│  COMPLIANCE ISSUES:                                                          │
│  ├── THREAT_LEGAL_ACTION        Threatened court/lawyers                    │
│  ├── THREAT_GARNISHMENT         Threatened wage garnishment                 │
│  ├── HARASSMENT                 Excessive pressure                          │
│  ├── MISSING_DISCLOSURE         Didn't mention dispute rights               │
│  ├── MISSING_HARDSHIP_OFFER     Didn't offer hardship options               │
│  └── PRIVACY_VIOLATION          Disclosed to third party                    │
│                                                                              │
│  RESOLUTION ISSUES:                                                          │
│  ├── NO_PAYMENT_OPTIONS         Didn't offer flexible payment               │
│  ├── UNREALISTIC_DEMANDS        Demanded full payment immediately           │
│  ├── FAILED_DE_ESCALATION       Customer more upset at end                  │
│  └── UNRESOLVED_WITHOUT_ACTION  Call ended without next steps               │
│                                                                              │
│  Why taxonomy matters:                                                       │
│  ✅ Aggregate: "Agent M7741 has 8 DISMISSIVE issues this week"              │
│  ✅ Compare: "Agent A: empathy issues. Agent B: compliance issues"          │
│  ✅ Target coaching: "You specifically struggle with de-escalation"         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

```python
COACH_ANALYSIS_SCHEMA = [
    # === IDENTITY ===
    ("conversation_id", "STRING", "REQUIRED"),
    ("agent_id", "STRING", "REQUIRED"),
    ("business_line", "STRING"),          # "COLLECTIONS" | "LOANS"
    ("team", "STRING"),
    ("queue", "STRING"),
    ("analyzed_at", "TIMESTAMP"),

    # === OVERALL SCORES (for dashboards, 1-10) ===
    ("empathy_score", "INTEGER"),
    ("compliance_score", "INTEGER"),
    ("resolution_score", "INTEGER"),
    ("professionalism_score", "INTEGER"),
    ("de_escalation_score", "INTEGER"),
    ("efficiency_score", "INTEGER"),
    ("overall_score", "FLOAT"),           # Weighted average

    # === EVIDENCE-BASED ASSESSMENTS (the key addition) ===
    ("assessments", "RECORD", "REPEATED", [
        ("dimension", "STRING"),          # "empathy", "compliance", etc.
        ("score", "INTEGER"),
        ("issue_types", "STRING", "REPEATED"),  # ["DISMISSIVE", "NO_ACK"]
        ("evidence", "RECORD", "REPEATED", [
            ("turn_index", "INTEGER"),
            ("speaker", "STRING"),        # "AGENT" or "CUSTOMER"
            ("quote", "STRING"),          # Actual text (~100 chars)
            ("issue_type", "STRING"),     # Specific issue
            ("severity", "STRING"),       # CRITICAL, HIGH, MEDIUM, LOW
        ]),
        ("coaching_point", "STRING"),     # Specific actionable advice
    ]),

    # === QUICK-ACCESS ISSUE SUMMARY (for filtering/aggregation) ===
    ("issue_types", "STRING", "REPEATED"),     # All issues in this call
    ("critical_issues", "STRING", "REPEATED"), # Only CRITICAL severity
    ("issue_count", "INTEGER"),
    ("compliance_breach_count", "INTEGER"),

    # === BINARY FLAGS ===
    ("resolution_achieved", "BOOLEAN"),
    ("escalation_required", "BOOLEAN"),
    ("customer_started_negative", "BOOLEAN"),

    # === CALL CLASSIFICATION ===
    ("call_type", "STRING"),              # hardship, complaint, payment, etc.
    ("call_outcome", "STRING"),           # From metadata

    # === COACHING OUTPUT ===
    ("coaching_summary", "STRING"),       # 2-3 sentence summary
    ("coaching_points", "STRING", "REPEATED"),
    ("strengths", "STRING", "REPEATED"),
    ("example_type", "STRING"),           # "GOOD_EXAMPLE", "NEEDS_WORK", null

    # === SITUATION CONTEXT ===
    ("situation_summary", "STRING"),      # What was the call about
    ("behavior_summary", "STRING"),       # How agent handled it
    ("key_moment", "RECORD", [            # Most notable moment for reference
        ("turn_index", "INTEGER"),
        ("quote", "STRING"),
        ("why_notable", "STRING"),
    ]),

    # === CI DATA (pre-computed) ===
    ("customer_sentiment", "FLOAT"),
    ("customer_sentiment_start", "FLOAT"),
    ("customer_sentiment_end", "FLOAT"),
    ("ci_flags", "STRING", "REPEATED"),   # From phrase matcher

    # === POLICY CITATIONS (RAG) ===
    ("policy_citations", "RECORD", "REPEATED", [
        ("policy_id", "STRING"),
        ("section_id", "STRING"),
        ("relevance", "STRING"),
    ]),

    # === METADATA ===
    ("model_version", "STRING"),
    ("prompt_version", "STRING"),
    ("duration_sec", "INTEGER"),
    ("turn_count", "INTEGER"),
]
```

### Why These Specific Scores?

| Score | What It Measures | How It's Aggregated | Dashboard Use |
|-------|------------------|---------------------|---------------|
| empathy_score | Agent showed understanding | AVG per day/week | Radar chart dimension |
| compliance_score | Followed policy | AVG + breach COUNT | Compliance % metric |
| resolution_score | Problem solved | AVG + resolution_rate | Success metric |
| de_escalation_score | Calmed upset customer | AVG (filtered to negative start) | De-escalation skill |
| efficiency_score | No unnecessary talk | AVG | Efficiency metric |
| professionalism_score | Appropriate tone | AVG | Professionalism metric |

### Implementation Components

```
cc_coach/
├── services/
│   ├── vertex_ai.py      # NEW: Gemini client wrapper
│   └── coaching.py       # NEW: Coaching generation logic
├── agents/
│   └── conversation_coach.py  # NEW: Per-conversation coach
├── prompts/
│   └── conversation_coach_v1.py  # NEW: System prompt
└── pipeline.py           # ADD: generate_coaching() step
```

### CLI Commands (Phase 1)
```bash
# Generate coaching for single conversation
cc-coach coach generate <conversation-id>

# Generate coaching for all pending (status=ENRICHED)
cc-coach coach generate-pending

# View coaching output
cc-coach coach get <conversation-id>
```

### Definition of Done (Phase 1)
- [ ] Vertex AI / Gemini integration working
- [ ] ConversationCoach generates structured JSON output
- [ ] coach_analysis table populated for test conversations
- [ ] Scores are reasonable (manual validation on 5-10 calls)
- [ ] CLI commands working
- [ ] Registry status updated to COACHED

---

## Phase 2: Daily Summary

### Goal
At end of day, generate a brief coaching summary for each agent.

### Data Flow
```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DAILY AGGREGATION                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ BigQuery Aggregation Query (no LLM needed)                       │    │
│  │                                                                   │    │
│  │ SELECT                                                            │    │
│  │   agent_id,                                                       │    │
│  │   DATE(analyzed_at) as date,                                      │    │
│  │   COUNT(*) as call_count,                                         │    │
│  │   AVG(empathy_score) as avg_empathy,                              │    │
│  │   AVG(compliance_score) as avg_compliance,                        │    │
│  │   AVG(resolution_score) as avg_resolution,                        │    │
│  │   COUNTIF(resolution_achieved) as resolved_count,                 │    │
│  │   ARRAY_AGG(DISTINCT issue IGNORE NULLS) as issues_today,         │    │
│  │   -- Get worst 3 calls for context                                │    │
│  │   ARRAY_AGG(STRUCT(conversation_id, empathy_score, situation_summary)  │
│  │             ORDER BY empathy_score LIMIT 3) as worst_calls        │    │
│  │ FROM coach_analysis, UNNEST(agent_issues) as issue                │    │
│  │ WHERE DATE(analyzed_at) = @target_date                            │    │
│  │ GROUP BY agent_id, date                                           │    │
│  └───────────────────────────────┬─────────────────────────────────┘    │
│                                  │                                       │
│                                  ▼                                       │
│                       ┌──────────────────────┐                          │
│                       │ Daily Coach (LLM)    │                          │
│                       │ ────────────────     │                          │
│                       │ Input: ~500 tokens   │                          │
│                       │ - aggregate metrics  │                          │
│                       │ - top 3 issues       │                          │
│                       │ - worst call summary │                          │
│                       └──────────┬───────────┘                          │
│                                  │                                       │
│                                  ▼                                       │
│                       ┌──────────────────────┐                          │
│                       │ daily_agent_summary  │                          │
│                       │ ────────────────     │                          │
│                       │ - agent_id, date     │                          │
│                       │ - call_count         │                          │
│                       │ - avg_scores         │                          │
│                       │ - top_issues[]       │                          │
│                       │ - daily_narrative    │                          │
│                       │ - focus_area         │                          │
│                       └──────────────────────┘                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Schema: daily_agent_summary

**Rich Example References**: Instead of just storing conversation IDs, we store "micro-summaries" that provide context without needing to re-read the full conversation.

```python
DAILY_AGENT_SUMMARY_SCHEMA = [
    # === IDENTITY ===
    ("agent_id", "STRING", "REQUIRED"),
    ("business_line", "STRING"),
    ("team", "STRING"),
    ("date", "DATE", "REQUIRED"),
    ("generated_at", "TIMESTAMP"),

    # === METRICS (pre-aggregated from coach_analysis) ===
    ("call_count", "INTEGER"),
    ("avg_empathy", "FLOAT"),
    ("avg_compliance", "FLOAT"),
    ("avg_resolution", "FLOAT"),
    ("avg_professionalism", "FLOAT"),
    ("avg_efficiency", "FLOAT"),
    ("avg_de_escalation", "FLOAT"),
    ("resolution_rate", "FLOAT"),
    ("compliance_breach_count", "INTEGER"),

    # === ISSUE DISTRIBUTION (for pattern detection) ===
    ("issue_distribution", "RECORD", "REPEATED", [
        ("issue_type", "STRING"),
        ("count", "INTEGER"),
        ("severity_breakdown", "JSON"),  # {"CRITICAL": 1, "HIGH": 3}
    ]),

    # === TOP EVIDENCE (keep worst 5 for context) ===
    ("top_evidence", "RECORD", "REPEATED", [
        ("conversation_id", "STRING"),
        ("issue_type", "STRING"),
        ("turn_index", "INTEGER"),
        ("quote", "STRING"),
        ("severity", "STRING"),
    ]),

    # === CATEGORICAL AGGREGATES ===
    ("top_issues", "STRING", "REPEATED"),
    ("top_strengths", "STRING", "REPEATED"),

    # === LLM GENERATED ===
    ("daily_narrative", "STRING"),    # 2-3 sentence summary
    ("focus_area", "STRING"),
    ("quick_wins", "STRING", "REPEATED"),

    # === RICH EXAMPLE REFERENCES (not just IDs) ===
    ("example_conversations", "RECORD", "REPEATED", [
        ("conversation_id", "STRING"),
        ("example_type", "STRING"),       # "GOOD_EXAMPLE" or "NEEDS_WORK"
        ("headline", "STRING"),           # "Hardship case - de-escalated angry to grateful"
        ("key_moment", "RECORD", [
            ("turn_index", "INTEGER"),
            ("quote", "STRING"),
            ("why_notable", "STRING"),
        ]),
        ("outcome", "STRING"),            # "90-day hold + fee waiver"
        ("sentiment_journey", "STRING"),  # "-1.0 → +1.0"
        ("scores", "JSON"),               # {"empathy": 9, "compliance": 10}
        ("call_type", "STRING"),
    ]),

    # === VS PREVIOUS DAY ===
    ("empathy_delta", "FLOAT"),
    ("compliance_delta", "FLOAT"),
]
```

**Rich Example Format** (enables Weekly Coach to reference without re-reading):
```json
{
  "example_conversations": [
    {
      "conversation_id": "conv_abc",
      "example_type": "GOOD_EXAMPLE",
      "headline": "Hardship case - cancer diagnosis - de-escalated",
      "key_moment": {
        "turn_index": 6,
        "quote": "I completely understand, let me see what options we have",
        "why_notable": "Pivotal empathy statement that changed tone"
      },
      "outcome": "90-day hardship hold + fee waiver",
      "sentiment_journey": "-1.0 → +1.0",
      "scores": {"empathy": 9, "compliance": 10, "resolution": 10},
      "call_type": "HARDSHIP"
    },
    {
      "conversation_id": "conv_xyz",
      "example_type": "NEEDS_WORK",
      "headline": "Threatened legal action, customer escalated",
      "key_moment": {
        "turn_index": 8,
        "quote": "We can garnish your wages",
        "why_notable": "Compliance violation - threat"
      },
      "outcome": "UNRESOLVED, complaint lodged",
      "sentiment_journey": "-0.5 → -1.0",
      "scores": {"empathy": 2, "compliance": 1, "resolution": 1},
      "call_type": "COLLECTIONS"
    }
  ]
}
```

### Why Daily Summary?

1. **Context window friendly**: ~500 tokens input (not 100K)
2. **Actionable**: Agent can review at end of shift
3. **Foundation for weekly**: Weekly aggregates daily summaries

### Definition of Done (Phase 2)
- [ ] BQ aggregation query working
- [ ] DailyCoach generates narrative from aggregates
- [ ] daily_agent_summary populated
- [ ] CLI: `cc-coach coach daily <agent-id> [date]`

---

## Phase 3: Weekly Report + Dashboard

### Goal
Weekly coaching report with visualizations (hexagon/radar chart).

### Data Flow
```
┌─────────────────────────────────────────────────────────────────────────┐
│                        WEEKLY AGGREGATION                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                                                                   │   │
│  │   daily_agent_summary (7 rows)                                    │   │
│  │   ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┐                    │   │
│  │   │ Mon │ Tue │ Wed │ Thu │ Fri │ Sat │ Sun │                    │   │
│  │   └──┬──┴──┬──┴──┬──┴──┬──┴──┬──┴──┬──┴──┬──┘                    │   │
│  │      │     │     │     │     │     │                              │   │
│  │      └─────┴─────┴──┬──┴─────┴─────┘                              │   │
│  │                     │                                              │   │
│  │                     ▼                                              │   │
│  │            ┌─────────────────┐                                     │   │
│  │            │ Weekly Coach    │                                     │   │
│  │            │ (LLM)           │                                     │   │
│  │            │                 │                                     │   │
│  │            │ Input:          │                                     │   │
│  │            │ - 7 daily sums  │                                     │   │
│  │            │ - week trends   │                                     │   │
│  │            │ - worst calls   │                                     │   │
│  │            └────────┬────────┘                                     │   │
│  │                     │                                              │   │
│  │                     ▼                                              │   │
│  │            ┌─────────────────┐                                     │   │
│  │            │weekly_agent_rpt │                                     │   │
│  │            │                 │                                     │   │
│  │            │ - week_scores   │───────▶  Dashboard                  │   │
│  │            │ - trend_delta   │          (Looker Studio)            │   │
│  │            │ - narrative     │                                     │   │
│  │            │ - action_plan   │          ┌─────────────────┐        │   │
│  │            └─────────────────┘          │   Radar Chart   │        │   │
│  │                                         │   ┌───────────┐ │        │   │
│  │                                         │   │ Empathy   │ │        │   │
│  │                                         │   │     ●     │ │        │   │
│  │                                         │   │  ●     ●  │ │        │   │
│  │                                         │   │Compliance │ │        │   │
│  │                                         │   └───────────┘ │        │   │
│  │                                         └─────────────────┘        │   │
│  │                                                                    │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Schema: weekly_agent_report

```python
WEEKLY_AGENT_REPORT_SCHEMA = [
    # Keys
    ("agent_id", "STRING", "REQUIRED"),
    ("week_start", "DATE", "REQUIRED"),  # Monday of the week
    ("generated_at", "TIMESTAMP"),

    # === WEEK SCORES (for radar chart) ===
    ("empathy_score", "FLOAT"),
    ("compliance_score", "FLOAT"),
    ("resolution_score", "FLOAT"),
    ("professionalism_score", "FLOAT"),
    ("efficiency_score", "FLOAT"),
    ("de_escalation_score", "FLOAT"),

    # === TREND vs PREVIOUS WEEK ===
    ("empathy_delta", "FLOAT"),      # This week - last week
    ("compliance_delta", "FLOAT"),
    ("resolution_delta", "FLOAT"),

    # === COUNTS ===
    ("total_calls", "INTEGER"),
    ("resolution_rate", "FLOAT"),
    ("compliance_breach_count", "INTEGER"),

    # === TOP ITEMS ===
    ("top_issues", "STRING", "REPEATED"),
    ("top_strengths", "STRING", "REPEATED"),
    ("recommended_training", "STRING", "REPEATED"),

    # === LLM NARRATIVE ===
    ("weekly_summary", "STRING"),     # 3-5 sentence summary
    ("trend_analysis", "STRING"),     # What's improving/declining
    ("action_plan", "STRING"),        # 2-3 specific actions

    # === REFERENCE CALLS ===
    ("exemplary_call_ids", "STRING", "REPEATED"),  # Best calls to review
    ("needs_review_call_ids", "STRING", "REPEATED"),  # Worst calls
]
```

### Hexagon/Radar Chart Data

The 6 scores map directly to radar chart axes:

```
                    Empathy (8.2)
                         ●
                        /|\
                       / | \
      Efficiency (6.5)●  |  ● Compliance (9.1)
                      \  |  /
                       \ | /
                        \|/
      De-escalation (7.0)●───●───● Resolution (7.8)
                             |
                             ●
                    Professionalism (8.5)
```

### Definition of Done (Phase 3)
- [ ] weekly_agent_report populated
- [ ] Radar chart data structure ready
- [ ] Looker Studio dashboard connected
- [ ] Agent can view their weekly report
- [ ] Supervisor can see team radar charts

---

## Phase 4: Trend Analysis + Historical References

### Goal
- Show trends over time (month-over-month)
- Reference back to specific conversations as examples

### Trend Query Pattern
```sql
-- Month-over-month trend for agent
SELECT
  agent_id,
  DATE_TRUNC(week_start, MONTH) as month,
  AVG(empathy_score) as empathy,
  AVG(resolution_rate) as resolution_rate,
  -- vs previous month
  LAG(AVG(empathy_score)) OVER (PARTITION BY agent_id ORDER BY month) as prev_empathy
FROM weekly_agent_report
GROUP BY agent_id, month
ORDER BY month
```

### Historical Reference Pattern

When generating weekly narrative, include specific examples:

```
"Your empathy score dropped from 8.2 to 6.5 this week. This was driven by
3 calls with 'interrupted_customer' issues. Example: In call abc123 on Tuesday,
you cut off the customer twice when they were explaining their hardship situation.
Compare with your excellent handling in call xyz789 last week where you let the
customer fully explain before responding."
```

### Definition of Done (Phase 4)
- [ ] Monthly trend queries working
- [ ] Historical comparison in weekly narrative
- [ ] Specific call references in coaching feedback
- [ ] Trend visualization in dashboard

---

## Complete Data Flow (All Phases)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COMPLETE DATA FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  PHASE 0 (DONE)                                                              │
│  ─────────────                                                               │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐                           │
│  │ GCS      │───▶│ CCAI     │───▶│ ci_enrichment│                           │
│  │transcript│    │ Insights │    │ (BQ table)   │                           │
│  └──────────┘    └──────────┘    └──────┬───────┘                           │
│                                         │                                    │
│  PHASE 1 (MVP)                          │                                    │
│  ─────────────                          ▼                                    │
│                               ┌──────────────────┐    ┌──────────────────┐  │
│                               │ Conversation     │───▶│ coach_analysis   │  │
│                               │ Coach (Gemini)   │    │ (BQ table)       │  │
│                               └──────────────────┘    └────────┬─────────┘  │
│                                                                │             │
│  PHASE 2                                                       │             │
│  ───────                                                       ▼             │
│                               ┌──────────────────┐    ┌──────────────────┐  │
│                               │ Daily Coach      │◀───│ BQ Aggregation   │  │
│                               │ (Gemini)         │    │ (SQL)            │  │
│                               └────────┬─────────┘    └──────────────────┘  │
│                                        │                                     │
│                                        ▼                                     │
│                               ┌──────────────────┐                          │
│                               │daily_agent_summary│                          │
│                               │ (BQ table)        │                          │
│                               └────────┬─────────┘                          │
│                                        │                                     │
│  PHASE 3                               │                                     │
│  ───────                               ▼                                     │
│                               ┌──────────────────┐    ┌──────────────────┐  │
│                               │ Weekly Coach     │───▶│weekly_agent_report│  │
│                               │ (Gemini)         │    │ (BQ table)        │  │
│                               └──────────────────┘    └────────┬─────────┘  │
│                                                                │             │
│                                                                ▼             │
│                                                       ┌──────────────────┐  │
│                                                       │ Dashboard        │  │
│                                                       │ (Looker Studio)  │  │
│                                                       │ - Radar charts   │  │
│                                                       │ - Trend lines    │  │
│                                                       │ - Drill-down     │  │
│                                                       └──────────────────┘  │
│                                                                              │
│  PHASE 4                                                                     │
│  ───────                                                                     │
│                               ┌──────────────────┐                          │
│                               │ Trend Analysis   │◀── Historical BQ queries │
│                               │ + Call References│                          │
│                               └──────────────────┘                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Time Sequence (Single Agent's Week)

```
Monday 9:00am    - Agent starts shift
        9:15am    - Call 1 ends → ci_enrichment written
        9:20am    - Conversation Coach runs → coach_analysis written
        ...
        5:00pm    - Shift ends
        5:30pm    - Daily Coach runs → daily_agent_summary written
        5:31pm    - Agent can view daily digest

Tuesday-Friday   - Same pattern

Saturday 6:00am  - Weekly Coach runs → weekly_agent_report written
         6:01am  - Agent can view weekly report + radar chart
                 - Supervisor sees team dashboard updated
```

---

## Context Window Strategy Summary

| Level | Raw Data Size | Input to LLM | Strategy |
|-------|---------------|--------------|----------|
| Per-Conv | 3-5K tokens | 3-5K tokens | Send full transcript |
| Daily | 20 calls × 4K = 80K | ~500 tokens | Aggregate metrics + 3 worst call summaries |
| Weekly | 7 days × 80K = 560K | ~1K tokens | 7 daily narratives + week metrics |
| Monthly | 4 weeks × 560K = 2.2M | ~2K tokens | 4 weekly summaries + trend data |

**Key insight**: Each level compresses 10-100x. LLM never sees raw transcripts except at per-conversation level.

---

## Token Budget Analysis (Gemini Context)

### Gemini Model Context Windows

| Model | Context Window | Use Case |
|-------|---------------|----------|
| Gemini 1.5 Flash | 1M tokens | Per-conversation, daily, weekly |
| Gemini 1.5 Pro | 2M tokens | Monthly aggregation, complex reasoning |

### Per-Conversation Token Estimation

Based on our dev dataset (9 synthetic conversations):

| Component | Tokens (typical) | Notes |
|-----------|------------------|-------|
| Transcript (~30 turns) | 1,500-2,500 | Varies by call length |
| CI Sentiment data | ~200 | Per-turn sentiment array |
| CI Summary | ~150 | Situation/Action/Result |
| Metadata + Context | ~200 | Agent, queue, outcome, etc. |
| Policy snippets (RAG) | ~500 | 2-3 relevant sections |
| **Total Input** | **~2,600** | Per conversation |
| LLM Output (coach_analysis) | ~800 | Evidence-based JSON |

### Agent Volume Estimation

Typical contact center agent:
- 40 calls/day
- 5 days/week = 200 calls/week
- 4 weeks/month = 800 calls/month

### Context Window Feasibility

| Aggregation Level | Data Volume | Tokens | % of 1M Context | Feasible? |
|-------------------|-------------|--------|-----------------|-----------|
| **Per-Conversation** | 1 call | ~2,600 | 0.26% | ✅ Trivial |
| **Daily Coach** | 40 calls summary | ~2,600 × 40 = 104K raw | 10.4% | ✅ With compression |
| **Weekly Coach** | 200 calls summary | ~2,600 × 200 = 520K raw | 52% | ✅ With compression |
| **Monthly Coach** | 800 calls summary | ~2,600 × 800 = 2.1M raw | 210% | ⚠️ Needs weekly summaries |

### Why Compression Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPRESSION STRATEGY                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Per-Conversation (2.6K tokens) → coach_analysis row                        │
│  ═══════════════════════════════════════════════════                        │
│  Stored: scores, issue_types, evidence[], key_moment, coaching_points       │
│  Result: ~600 tokens worth of structured data per conversation              │
│                                                                              │
│  Daily (40 calls × 600 = 24K) → daily_agent_summary                         │
│  ══════════════════════════════════════════════════                         │
│  Aggregate: AVG scores, issue distribution, top 5 evidence, 3 examples      │
│  Result: ~2K tokens per day                                                 │
│                                                                              │
│  Weekly (5 days × 2K = 10K) → weekly_agent_report                           │
│  ═════════════════════════════════════════════════                          │
│  Aggregate: Week AVGs, trend deltas, top issues, 5 best/worst examples      │
│  Result: ~3K tokens per week                                                │
│                                                                              │
│  Monthly (4 weeks × 3K = 12K) → monthly coaching                            │
│  ════════════════════════════════════════════════                           │
│  Fits easily in context with full narrative generation                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Demo Configuration

For best demo results, we **maximize context**:

| Level | Input Strategy | Tokens |
|-------|---------------|--------|
| Per-Conv | Full transcript + all CI data + policy snippets | ~3K |
| Daily | All 40 coach_analysis rows (rich data) | ~25K |
| Weekly | 5 daily summaries + 10 example conversations | ~15K |

With Gemini's 1M context, we have headroom for rich, detailed coaching.

---

## Test Data Requirements for Demo

### Volume Needed

To properly demo weekly aggregation with multiple agents:

| Component | Quantity | Rationale |
|-----------|----------|-----------|
| **Agents** | 3 | Show comparison across agents |
| **Days** | 5 | Full work week |
| **Calls/Agent/Day** | 40 | Realistic volume |
| **Total Conversations** | 600 | 3 × 5 × 40 |

### Current Dev Dataset

Current: 9 conversations in `artifacts/data/dev/2025-12-28/`

This is sufficient for:
- ✅ Per-conversation coaching (demo works)
- ✅ Pipeline validation (all scenarios covered)
- ⚠️ Daily aggregation (9 calls = 1 day for 1 agent)
- ❌ Weekly aggregation (need 5 days)

### Test Data Generation Plan

```
Phase 1 (Current): 9 hand-crafted conversations
├── Purpose: Validate pipeline, test edge cases
└── Coverage: All scenario types, CI features

Phase 2 (Pre-Demo): Generate 600 conversations
├── 3 agents (A1001, A1002, A1003)
├── 5 days (2025-12-28 to 2026-01-01)
├── 40 calls/agent/day
├── Distribution:
│   ├── 60% "normal" (baseline, some issues)
│   ├── 25% "needs work" (multiple issues)
│   └── 15% "exemplary" (model behavior)
└── Agent Personas:
    ├── A1001: Good empathy, weak on compliance disclosures
    ├── A1002: Strong compliance, struggles with angry customers
    └── A1003: Balanced, occasional efficiency issues
```

### Agent Persona Distribution (for meaningful weekly coaching)

| Agent | Empathy Pattern | Compliance Pattern | Signature Issues |
|-------|-----------------|-------------------|------------------|
| A1001 | 7-9 (high) | 5-7 (low) | MISSING_DISCLOSURE, NO_HARDSHIP_OFFER |
| A1002 | 5-7 (medium) | 8-10 (high) | RUSHED_CUSTOMER, FAILED_DE_ESCALATION |
| A1003 | 7-8 (good) | 7-8 (good) | UNREALISTIC_DEMANDS (occasional) |

This creates meaningful weekly narratives:
- A1001: "Strong empathy but missed disclosures 12 times this week"
- A1002: "Excellent compliance, work on calming upset customers"
- A1003: "Consistent performance, minor efficiency improvements possible"

---

## What About Daily Context Window Overflow?

**Q: What if an agent has 100 calls in one day?**

**A: You don't send 100 transcripts. You send:**
1. Aggregate metrics (1 row of numbers)
2. Issue frequency counts
3. Top 3 worst call summaries (~500 tokens total)

The LLM receives structured data, not raw transcripts:

```json
{
  "agent_id": "M7741",
  "date": "2025-01-15",
  "call_count": 100,
  "avg_empathy": 6.2,
  "avg_compliance": 8.5,
  "resolution_rate": 0.72,
  "top_issues": ["interrupted_customer", "no_alternatives_offered"],
  "worst_calls": [
    {"id": "abc123", "empathy": 2.0, "summary": "Customer upset about fees, agent dismissive"},
    {"id": "def456", "empathy": 3.0, "summary": "Hardship request, agent rushed to close"},
    {"id": "ghi789", "empathy": 3.5, "summary": "Complaint escalated due to tone"}
  ]
}
```

This is ~500 tokens regardless of whether the agent had 10 or 1000 calls.

---

## Tech Stack Summary

| Component | Technology | Why |
|-----------|------------|-----|
| LLM | Vertex AI Gemini 1.5 Flash | Cost-effective, fast, good for structured output |
| Storage | BigQuery | Already using, good for aggregation |
| Dashboard | Looker Studio | Free, integrates with BQ |
| Scheduling | Cloud Scheduler | Simple, reliable |
| Framework | Python + existing CLI | Build on what exists |

---

## Estimated Effort

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 1 (MVP) | 2-3 days | Vertex AI API access |
| Phase 2 | 1 day | Phase 1 |
| Phase 3 | 2-3 days | Phase 2, Looker setup |
| Phase 4 | 1-2 days | Phase 3 |

**Total MVP to Dashboard: ~1-2 weeks**

---

## Next Steps

### Current: Phase 1 - Per-Conversation Coach
1. **Implement ADK Coach**: ConversationCoach with Gemini + RAG
   - See: `design/phase1_adk_conversation_coach.md`
2. **Validate**: Run on test conversations, verify scores are sensible
3. **Iterate**: Refine prompt based on output quality

### Then: Phase 2 & 3 - Aggregation (MVP Complete)
4. **Daily Summary**: SQL aggregation + Daily Coach LLM
5. **Weekly Report**: Weekly aggregation + visualization

### Post-MVP: Production Readiness

| Phase | Focus | Key Components |
|-------|-------|----------------|
| **Phase 4** | Evaluation | Human calibration, automatic evals, improvement flywheel |
| **Phase 5** | Monitoring | Latency/error dashboards, quality drift alerts, anomaly detection |
| **Phase 6** | FinOps | Token cost tracking, budget alerts, model tier optimization |

**Post-MVP References:**
- Evaluation: `design/evaluation_framework.md`
- Monitoring: Track latency P50/P95, error rates, JSON validity rate
- FinOps: Token usage per conversation, daily/weekly cost aggregation
