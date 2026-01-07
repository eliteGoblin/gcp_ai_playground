# Period Summary Design: Daily & Weekly Agent Reports

## Overview

This document details the design for generating periodic coaching summaries (daily and weekly) for contact center agents. The system creates **evidence-based summaries** that show not just scores, but WHY those scores with specific examples, quotes, and actionable guidance.

**Key Principle: Evidence over metrics.** A good summary shows what happened, not just numbers.

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [Summary Components](#2-summary-components)
3. [Trend Analysis Design](#3-trend-analysis-design)
4. [Goals & Requirements](#4-goals--requirements)
5. [Architecture Overview](#5-architecture-overview)
6. [Data Flow](#6-data-flow)
7. [BigQuery Schema](#7-bigquery-schema)
8. [SQL Aggregation Queries](#8-sql-aggregation-queries)
9. [LLM Summary Generation](#9-llm-summary-generation)
10. [RAG Considerations](#10-rag-considerations)
11. [CLI Commands](#11-cli-commands)
12. [Implementation Plan](#12-implementation-plan)
13. [Summary](#13-summary)

---

## 1. Design Philosophy

### 1.1 Evidence Over Metrics

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVIDENCE-FIRST DESIGN PRINCIPLE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ❌ BAD: Metric-only summary                                              │
│   ════════════════════════════                                             │
│                                                                             │
│   "Alex scored 8.2 in empathy, 7.5 in efficiency, 9.1 in compliance."      │
│                                                                             │
│   Problems:                                                                 │
│   • No context - WHY these scores?                                         │
│   • No evidence - WHAT moments demonstrated this?                          │
│   • Not actionable - WHAT specifically to improve?                         │
│   • Could be generated without LLM (just SQL)                              │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   ✅ GOOD: Evidence-based summary                                          │
│   ═══════════════════════════════                                          │
│                                                                             │
│   "Alex's empathy (8.2) was strong - particularly in the hardship call     │
│   where he said 'I understand how stressful this must be for you' which    │
│   shifted the customer from frustrated to collaborative. However,           │
│   efficiency (7.5) suffered in 2 calls where Alex spent excessive time     │
│   re-explaining payment options that were already declined."                │
│                                                                             │
│   Why better:                                                               │
│   • Shows WHY the score                                                     │
│   • Provides EVIDENCE (quotes)                                             │
│   • Is ACTIONABLE (stop re-explaining declined options)                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 What Makes a Summary Valuable?

| Aspect | Bad Summary | Good Summary |
|--------|-------------|--------------|
| **Scores** | "Empathy: 8.2" | "Empathy: 8.2 - strong emotional validation in hardship calls" |
| **Issues** | "3 compliance issues" | "3 compliance issues: missed hardship disclosure in conv-123, incomplete verification in conv-456" |
| **Advice** | "Improve efficiency" | "When customer declines an option, move on instead of re-explaining. See conv-789 turn 15." |
| **Trends** | "Empathy +0.3" | "Empathy improved +0.3 after focusing on validation phrases last week" |

---

## 2. Summary Components

### 2.1 Daily Summary Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DAILY SUMMARY STRUCTURE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  COMPONENT 1: OVERVIEW                                               │  │
│   │  ════════════════════════                                            │  │
│   │                                                                      │  │
│   │  What: Call count, overall score, quick context                     │  │
│   │  Why useful: Sets the stage, gives context for the day              │  │
│   │                                                                      │  │
│   │  Example: "5 calls | Overall: 8.5/10 | Mix of hardship & complaints"│  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  COMPONENT 2: KEY MOMENTS (Evidence of Excellence)                   │  │
│   │  ══════════════════════════════════════════════                      │  │
│   │                                                                      │  │
│   │  What: Top 2-3 pivotal moments from today's calls                   │  │
│   │  Contains: conversation_id, turn, quote, why_notable                │  │
│   │  Why useful: Shows WHAT the agent did well with proof              │  │
│   │                                                                      │  │
│   │  Example:                                                           │  │
│   │  ┌───────────────────────────────────────────────────────────────┐  │  │
│   │  │ KEY MOMENT (conv-123, turn 9):                                │  │  │
│   │  │ "I understand how stressful this must be for you. Let me see  │  │  │
│   │  │  what options we have to help."                               │  │  │
│   │  │                                                                │  │  │
│   │  │ Why notable: De-escalated angry customer, led to successful   │  │  │
│   │  │ payment arrangement. Shows strong empathy under pressure.     │  │  │
│   │  └───────────────────────────────────────────────────────────────┘  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  COMPONENT 3: ISSUES WITH EVIDENCE                                   │  │
│   │  ══════════════════════════════════                                  │  │
│   │                                                                      │  │
│   │  What: Coaching issues with specific conversation references        │  │
│   │  Contains: issue_type, conversation_id, context, quote             │  │
│   │  Why useful: Specific, reviewable, actionable                      │  │
│   │                                                                      │  │
│   │  Example:                                                           │  │
│   │  ┌───────────────────────────────────────────────────────────────┐  │  │
│   │  │ ISSUE: Missed Hardship Disclosure (conv-456)                  │  │  │
│   │  │ Context: Customer mentioned "lost my job" but agent didn't    │  │  │
│   │  │ offer hardship program.                                       │  │  │
│   │  │ Quote: "Let's set up a payment plan" (should have offered     │  │  │
│   │  │ hardship first)                                               │  │  │
│   │  └───────────────────────────────────────────────────────────────┘  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  COMPONENT 4: STRENGTHS WITH EVIDENCE                                │  │
│   │  ═════════════════════════════════════                               │  │
│   │                                                                      │  │
│   │  What: What went well today with examples                           │  │
│   │  Why useful: Reinforcement, confidence building, know what to keep │  │
│   │                                                                      │  │
│   │  Example:                                                           │  │
│   │  • Strong de-escalation in 3/3 complaint calls                     │  │
│   │  • Perfect compliance: all verifications complete                  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  COMPONENT 5: FOCUS FOR TOMORROW (LLM Generated)                     │  │
│   │  ════════════════════════════════════════════════                    │  │
│   │                                                                      │  │
│   │  What: Specific coaching advice based on today's evidence          │  │
│   │  Why useful: Actionable, references actual calls                   │  │
│   │                                                                      │  │
│   │  Example:                                                           │  │
│   │  "EFFICIENCY: When customer declines an option, move on.            │  │
│   │  Try: 'I understand that doesn't work for you. Let me suggest       │  │
│   │  an alternative...' instead of re-explaining. Review conv-789."    │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Weekly Summary Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WEEKLY SUMMARY STRUCTURE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  COMPONENT 1: WEEK OVERVIEW                                          │  │
│   │  ══════════════════════════                                          │  │
│   │                                                                      │  │
│   │  What: Total calls, days active, overall trend                      │  │
│   │  Example: "28 calls | 5 days | Overall: 8.4/10 (+0.3 vs last week)" │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  COMPONENT 2: TREND ANALYSIS WITH EVIDENCE                           │  │
│   │  ══════════════════════════════════════════                          │  │
│   │                                                                      │  │
│   │  What: What changed vs last week, WITH reasons                      │  │
│   │  Why useful: Shows trajectory, validates coaching effectiveness     │  │
│   │                                                                      │  │
│   │  Example:                                                           │  │
│   │  ┌───────────────────────────────────────────────────────────────┐  │  │
│   │  │ IMPROVING:                                                     │  │  │
│   │  │ • Empathy: 7.9 → 8.4 (+0.5)                                   │  │  │
│   │  │   Evidence: Consistently validated customer emotions           │  │  │
│   │  │   Best example: conv-123 "I hear your frustration..."         │  │  │
│   │  │                                                                │  │  │
│   │  │ DECLINING:                                                     │  │  │
│   │  │ • Efficiency: 8.0 → 7.7 (-0.3)                                │  │  │
│   │  │   Pattern: Thursday/Friday calls averaged 15+ minutes          │  │  │
│   │  │   Common issue: Over-explaining payment options                │  │  │
│   │  │                                                                │  │  │
│   │  │ STABLE:                                                        │  │  │
│   │  │ • Compliance: 9.1 → 9.0 (effectively unchanged)               │  │  │
│   │  └───────────────────────────────────────────────────────────────┘  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  COMPONENT 3: RECURRING PATTERNS                                     │  │
│   │  ════════════════════════════════                                    │  │
│   │                                                                      │  │
│   │  What: Issues/strengths that appeared multiple days                 │  │
│   │  Why useful: Identifies habits (good and bad) vs one-off events    │  │
│   │                                                                      │  │
│   │  Example:                                                           │  │
│   │  • STRENGTH: De-escalation (appeared 4/5 days)                     │  │
│   │    Successfully calmed frustrated customers in 12 of 14 cases      │  │
│   │  • ISSUE: Efficiency on complex calls (appeared 3/5 days)          │  │
│   │    Hardship and complaint calls consistently exceed time targets   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  COMPONENT 4: CONVERSATIONS TO REVIEW                                │  │
│   │  ═════════════════════════════════════                               │  │
│   │                                                                      │  │
│   │  What: Best and worst conversations with context                    │  │
│   │  Why useful: Concrete examples to learn from / review               │  │
│   │                                                                      │  │
│   │  Example:                                                           │  │
│   │  EXEMPLARY (learn from these):                                      │  │
│   │  • conv-123 (9.5) - Perfect hardship handling, strong de-escalation│  │
│   │  • conv-234 (9.3) - Excellent complaint resolution                 │  │
│   │                                                                      │  │
│   │  NEEDS REVIEW (coaching opportunities):                             │  │
│   │  • conv-789 (6.2) - Efficiency issues, call lasted 22 minutes      │  │
│   │  • conv-890 (6.8) - Missed hardship disclosure                     │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  COMPONENT 5: ACTION ITEMS (LLM Generated)                           │  │
│   │  ══════════════════════════════════════════                          │  │
│   │                                                                      │  │
│   │  What: Specific actions for next week based on patterns            │  │
│   │  Why useful: Actionable, prioritized, evidence-based               │  │
│   │                                                                      │  │
│   │  Example:                                                           │  │
│   │  1. Review conv-789 and conv-456 to identify efficiency patterns   │  │
│   │  2. Practice the "acknowledge and move on" technique               │  │
│   │  3. Continue strong de-escalation approach - it's working!         │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Trend Analysis Design

### 3.1 When Are Trends Useful?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TREND ANALYSIS - WHEN USEFUL?                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   DAILY TREND (vs yesterday):                                              │
│   ════════════════════════════                                             │
│                                                                             │
│   Usefulness: LOW TO MEDIUM                                                │
│   • Often NOISY - one bad call can swing score significantly              │
│   • With 5 calls, statistical significance is low                         │
│   • Can be misleading without context                                      │
│                                                                             │
│   Recommendation:                                                          │
│   • SHOW but with sample size context                                      │
│   • "8.2 (↑0.3 vs yesterday, 5 calls)"                                    │
│   • Focus more on EVIDENCE than trend number                              │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   WEEKLY TREND (vs last week):                                             │
│   ═════════════════════════════                                            │
│                                                                             │
│   Usefulness: HIGH                                                         │
│   • Larger sample (25-50 calls) = more meaningful                         │
│   • Shows actual improvement/decline                                       │
│   • Useful for coaching prioritization                                     │
│                                                                             │
│   Recommendation:                                                          │
│   • SHOW with confidence                                                   │
│   • "Empathy: 8.4 (+0.5 vs last week, 28 calls vs 25)"                    │
│   • Include EVIDENCE of why trend occurred                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 When Trends ARE Useful

| Use Case | Example | Why Helpful |
|----------|---------|-------------|
| **Identifying persistent issues** | "Efficiency declined 3 weeks in a row" | Pattern needs attention |
| **Validating coaching** | "After focusing on empathy, score improved 7.5 → 8.5" | Confirms approach works |
| **Motivation** | "Your compliance has been perfect for 2 weeks!" | Reinforcement |
| **Prioritization** | "Declining efficiency should be this week's focus" | Guides coaching |

### 3.3 When Trends Can Be Misleading

| Situation | Example | Problem |
|-----------|---------|---------|
| **Small sample** | "Efficiency dropped 2 points" (but only 3 calls) | Not statistically significant |
| **Outlier days** | One very difficult call tanks the average | Not representative |
| **Different call mix** | Last week: easy inquiries. This week: difficult complaints. | Comparing apples to oranges |

### 3.4 Trend Implementation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TREND DATA TO STORE                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   FOR EACH DIMENSION:                                                      │
│                                                                             │
│   current_score      FLOAT64    8.4       The current period score        │
│   previous_score     FLOAT64    7.9       Previous period score           │
│   delta              FLOAT64    +0.5      current - previous              │
│   current_sample     INT64      28        Calls in current period         │
│   previous_sample    INT64      25        Calls in previous period        │
│   trend_direction    STRING     "improving"  / "declining" / "stable"     │
│   trend_evidence     STRING     "Consistently validated emotions"         │
│                                                                             │
│   CLASSIFICATION LOGIC:                                                    │
│   • |delta| < 0.2 → "stable"                                              │
│   • delta >= 0.2 → "improving"                                            │
│   • delta <= -0.2 → "declining"                                           │
│                                                                             │
│   EVIDENCE GENERATION (LLM):                                               │
│   • For improving: What did agent do differently?                         │
│   • For declining: What pattern caused the drop?                          │
│   • For stable: Is it good-stable or bad-stable?                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Goals & Requirements

### 4.1 Why Period Summaries?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WHY COMPRESS?                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   PROBLEM: Raw Data Volume at Production Scale                             │
│   ════════════════════════════════════════════                             │
│                                                                             │
│   Agent "Alex" - 1 Month:                                                  │
│   • 50 calls/day × 22 working days = 1,100 calls                          │
│   • Each coaching output ~1,000 tokens                                     │
│   • Total: 1.1M tokens ❌ Exceeds context window                          │
│                                                                             │
│   SOLUTION: Progressive Compression                                        │
│   ═══════════════════════════════════                                      │
│                                                                             │
│   Level 1: Per-Conversation     → 1,000 tokens each                       │
│   Level 2: Daily Summary        → 500 tokens (50 calls compressed)        │
│   Level 3: Weekly Summary       → 1,000 tokens (5 days compressed)        │
│                                                                             │
│   Compression Ratios:                                                      │
│   • Daily: 50 calls × 1K = 50K → 500 tokens = 100x compression            │
│   • Weekly: 5 days × 500 = 2.5K → 1K tokens = 2.5x compression            │
│   • Monthly: 4 weeks × 1K = 4K → fits easily                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Requirements

| Requirement | Description |
|-------------|-------------|
| **R1: Trend Visibility** | Show score trends (improving/declining) vs previous period |
| **R2: Issue Patterns** | Surface recurring coaching issues across calls |
| **R3: Actionable Advice** | LLM-generated coaching recommendations |
| **R4: Evidence Links** | Reference specific conversations as examples |
| **R5: Production Scale** | Handle 50+ calls/agent/day |
| **R6: Auditability** | Store both raw metrics and LLM outputs |

### 4.3 Non-Requirements (Out of Scope)

- Cross-agent comparison (team-level reports)
- Real-time dashboards
- Monthly summaries (can query weekly directly)

---

## 5. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PERIOD SUMMARY ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                        DATA SOURCES                                  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   coach_analysis (BQ)              conversation_registry (BQ)              │
│   ┌─────────────────────┐          ┌─────────────────────┐                │
│   │ Per-conversation    │          │ Agent metadata      │                │
│   │ coaching results    │          │ (team, business_line│                │
│   │ • scores (6 dims)   │          │  queue, etc.)       │                │
│   │ • coaching_points   │          │                     │                │
│   │ • key_moment        │          │                     │                │
│   │ • strengths         │          │                     │                │
│   └─────────────────────┘          └─────────────────────┘                │
│            │                                │                              │
│            └────────────────┬───────────────┘                              │
│                             ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                     SQL AGGREGATION LAYER                            │  │
│   │                                                                      │  │
│   │  • AVG scores by dimension                                          │  │
│   │  • COUNT issues by type                                             │  │
│   │  • SELECT best/worst conversations                                  │  │
│   │  • COMPUTE trend vs previous period                                 │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                             │                                              │
│                             ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                     LLM SUMMARY GENERATION                           │  │
│   │                                                                      │  │
│   │  Input: Aggregated metrics + example conversations                  │  │
│   │  Output: Narrative + focus_area + coaching_advice                   │  │
│   │                                                                      │  │
│   │  Model: gemini-2.5-flash (same as per-conversation coach)           │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                             │                                              │
│                             ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                     STORAGE (BigQuery)                               │  │
│   │                                                                      │  │
│   │  daily_agent_summary          weekly_agent_report                   │  │
│   │  ┌─────────────────────┐      ┌─────────────────────┐               │  │
│   │  │ SQL metrics        │      │ SQL metrics (week)  │               │  │
│   │  │ + LLM narrative    │      │ + LLM narrative     │               │  │
│   │  │ + examples         │      │ + trend analysis    │               │  │
│   │  └─────────────────────┘      └─────────────────────┘               │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Data Flow

### 6.1 Daily Summary Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DAILY SUMMARY DATA FLOW                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   TRIGGER: Daily at 6 AM (or on-demand via CLI)                            │
│   SCOPE: One agent, one date                                               │
│                                                                             │
│   STEP 1: Query Raw Data                                                   │
│   ══════════════════════                                                   │
│                                                                             │
│   SELECT * FROM coach_analysis                                             │
│   WHERE agent_id = @agent_id                                               │
│     AND DATE(analyzed_at) = @date                                          │
│                                                                             │
│   Result: 5-50 coaching records                                            │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   STEP 2: SQL Aggregation                                                  │
│   ═══════════════════════                                                  │
│                                                                             │
│   Compute:                                                                 │
│   • call_count                                                             │
│   • avg_empathy, avg_compliance, avg_resolution, etc.                     │
│   • issue_counts (GROUP BY coaching_point category)                       │
│   • best_conversation (MAX overall_score)                                 │
│   • worst_conversation (MIN overall_score)                                │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   STEP 3: Query Previous Day (for trend)                                  │
│   ══════════════════════════════════════                                   │
│                                                                             │
│   SELECT avg_overall FROM daily_agent_summary                              │
│   WHERE agent_id = @agent_id                                               │
│     AND date = DATE_SUB(@date, INTERVAL 1 DAY)                            │
│                                                                             │
│   Compute: overall_delta = today - yesterday                              │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   STEP 4: LLM Summary Generation                                          │
│   ══════════════════════════════                                           │
│                                                                             │
│   Input to LLM (~500 tokens):                                              │
│   • Agent metadata                                                         │
│   • Today's metrics                                                        │
│   • Trend vs yesterday                                                     │
│   • Top issues (with counts)                                              │
│   • Best/worst conversation details                                       │
│                                                                             │
│   Output from LLM:                                                         │
│   • daily_narrative (2-3 sentences)                                       │
│   • focus_area (single area to improve)                                   │
│   • coaching_advice (actionable guidance)                                 │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   STEP 5: Store to BigQuery                                               │
│   ═════════════════════════                                                │
│                                                                             │
│   INSERT INTO daily_agent_summary                                          │
│   (agent_id, date, call_count, avg_*, ..., daily_narrative, ...)          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Weekly Summary Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WEEKLY SUMMARY DATA FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   TRIGGER: Monday at 7 AM (or on-demand via CLI)                           │
│   SCOPE: One agent, previous week (Mon-Sun)                                │
│                                                                             │
│   STEP 1: Query Daily Summaries                                            │
│   ═════════════════════════════                                            │
│                                                                             │
│   SELECT * FROM daily_agent_summary                                        │
│   WHERE agent_id = @agent_id                                               │
│     AND date BETWEEN @week_start AND @week_end                            │
│                                                                             │
│   Result: 5-7 daily summary records                                        │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   STEP 2: Aggregate Week Metrics                                           │
│   ══════════════════════════════                                           │
│                                                                             │
│   Compute:                                                                 │
│   • total_calls = SUM(call_count)                                         │
│   • week_avg_empathy = AVG(avg_empathy) weighted by call_count            │
│   • issue_pattern = Most frequent issues across week                      │
│   • best_day, worst_day                                                   │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   STEP 3: Query Previous Week (for trend)                                 │
│   ═══════════════════════════════════════                                  │
│                                                                             │
│   SELECT * FROM weekly_agent_report                                        │
│   WHERE agent_id = @agent_id                                               │
│     AND week_start = DATE_SUB(@week_start, INTERVAL 7 DAY)                │
│                                                                             │
│   Compute deltas for all dimensions                                        │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   STEP 4: Select Example Conversations                                    │
│   ════════════════════════════════════                                     │
│                                                                             │
│   Query coach_analysis for:                                                │
│   • Top 3 best-scored conversations (exemplary)                           │
│   • Top 3 worst-scored conversations (needs review)                       │
│   Include: conversation_id, score, summary, key_moment                    │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   STEP 5: LLM Summary Generation                                          │
│   ══════════════════════════════                                           │
│                                                                             │
│   Input to LLM (~1000 tokens):                                             │
│   • Agent metadata                                                         │
│   • 7 daily summaries (compressed)                                        │
│   • Week trends vs previous week                                          │
│   • Issue patterns                                                        │
│   • Example conversations                                                 │
│                                                                             │
│   Output from LLM:                                                         │
│   • weekly_narrative (3-5 sentences)                                      │
│   • trend_analysis (what's improving/declining)                           │
│   • action_items (2-3 specific actions)                                   │
│   • recommended_focus (priority for next week)                            │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   STEP 6: Store to BigQuery                                               │
│   ═════════════════════════                                                │
│                                                                             │
│   INSERT INTO weekly_agent_report                                          │
│   (agent_id, week_start, total_calls, ..., weekly_narrative, ...)         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. BigQuery Schema

### 7.1 daily_agent_summary

```sql
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.daily_agent_summary` (
  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 1: PRIMARY KEYS
  -- ═══════════════════════════════════════════════════════════════════════
  agent_id STRING NOT NULL,           -- Agent identifier
  date DATE NOT NULL,                 -- Summary date

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 2: METADATA
  -- ═══════════════════════════════════════════════════════════════════════
  generated_at TIMESTAMP,             -- When summary was generated
  business_line STRING,               -- From conversation_registry
  team STRING,                        -- Agent's team

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 3: RAW METRICS (Computed by SQL from coach_analysis)
  -- These are the "facts" - computed directly, no LLM involved
  -- ═══════════════════════════════════════════════════════════════════════
  call_count INT64,                   -- Number of conversations coached

  -- Average scores (0-10 scale)
  avg_empathy FLOAT64,
  avg_compliance FLOAT64,
  avg_resolution FLOAT64,
  avg_professionalism FLOAT64,
  avg_efficiency FLOAT64,
  avg_de_escalation FLOAT64,
  avg_overall FLOAT64,

  -- Rates
  resolution_rate FLOAT64,            -- resolved_count / call_count

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 4: KEY MOMENTS WITH EVIDENCE (Selected by SQL from coach_analysis)
  -- Shows WHY scores are what they are with specific quotes
  -- ═══════════════════════════════════════════════════════════════════════
  key_moments JSON,                   -- Array of pivotal moments from today's calls
                                      -- [
                                      --   {
                                      --     "conversation_id": "conv-123",
                                      --     "turn": 9,
                                      --     "quote": "I understand how stressful this must be...",
                                      --     "context": "Customer was angry about late fees",
                                      --     "dimension": "empathy",
                                      --     "score_contribution": "positive"
                                      --   },
                                      --   ...
                                      -- ]

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 5: ISSUES WITH EVIDENCE (From coaching_points)
  -- Specific coaching issues with conversation references
  -- ═══════════════════════════════════════════════════════════════════════
  issues_with_evidence JSON,          -- Array of issues with proof
                                      -- [
                                      --   {
                                      --     "issue_type": "missed_hardship_disclosure",
                                      --     "dimension": "compliance",
                                      --     "conversation_id": "conv-456",
                                      --     "context": "Customer mentioned 'lost my job'",
                                      --     "what_happened": "Agent offered payment plan without hardship",
                                      --     "quote": "Let's set up a payment plan...",
                                      --     "should_have": "Offered hardship program first"
                                      --   },
                                      --   ...
                                      -- ]
  issue_counts JSON,                  -- {"compliance": 2, "empathy": 1, ...}

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 6: STRENGTHS WITH EVIDENCE
  -- What went well today with specific examples
  -- ═══════════════════════════════════════════════════════════════════════
  strengths_with_evidence JSON,       -- Array of strengths with proof
                                      -- [
                                      --   {
                                      --     "strength_type": "de_escalation",
                                      --     "dimension": "de_escalation",
                                      --     "occurrences": 3,
                                      --     "best_example_conv": "conv-123",
                                      --     "example_quote": "I hear your frustration...",
                                      --     "outcome": "Customer went from angry to grateful"
                                      --   },
                                      --   ...
                                      -- ]
  top_strengths ARRAY<STRING>,        -- ["de_escalation", "compliance"]

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 7: EXAMPLE CONVERSATIONS (Best/Worst for reference)
  -- ═══════════════════════════════════════════════════════════════════════
  best_conversation JSON,             -- {
                                      --   "conversation_id": "conv-123",
                                      --   "overall_score": 9.5,
                                      --   "call_type": "hardship",
                                      --   "summary": "...",
                                      --   "key_moment_quote": "...",
                                      --   "why_exemplary": "Perfect empathy + compliance"
                                      -- }
  worst_conversation JSON,            -- {
                                      --   "conversation_id": "conv-456",
                                      --   "overall_score": 6.2,
                                      --   "call_type": "complaint",
                                      --   "summary": "...",
                                      --   "issues": ["missed_disclosure", "inefficient"],
                                      --   "primary_issue": "Did not offer hardship when indicated"
                                      -- }

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 8: TREND DATA (Computed by SQL - compare to previous day)
  -- ═══════════════════════════════════════════════════════════════════════
  prev_day_avg_overall FLOAT64,       -- Yesterday's overall score
  prev_day_call_count INT64,          -- Yesterday's call count (for context)
  overall_delta FLOAT64,              -- today - yesterday
  trend_direction STRING,             -- "improving", "declining", "stable"

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 9: LLM GENERATED (Created by Summary Agent)
  -- Narrative synthesis based on evidence in sections 4-8
  -- ═══════════════════════════════════════════════════════════════════════
  daily_narrative STRING,             -- Evidence-based summary:
                                      -- "Alex's empathy (8.2) was strong - particularly
                                      -- in the hardship call where he said 'I understand
                                      -- how stressful...' which shifted the customer from
                                      -- frustrated to collaborative. However, efficiency
                                      -- (7.5) suffered in 2 calls where Alex spent
                                      -- excessive time re-explaining declined options."

  focus_area STRING,                  -- "efficiency"

  coaching_advice STRING,             -- Specific, actionable advice:
                                      -- "When customer declines an option, move on.
                                      -- Try: 'I understand that doesn't work. Let me
                                      -- suggest an alternative...' Review conv-789
                                      -- turn 15 for an example."

  key_wins ARRAY<STRING>,             -- ["Excellent de-escalation in conv-123",
                                      --  "Perfect compliance on all verifications"]

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 10: VERSIONING
  -- ═══════════════════════════════════════════════════════════════════════
  model_version STRING,               -- "gemini-2.5-flash"
  prompt_version STRING               -- "daily_summary_v1.0"
)
PARTITION BY date
CLUSTER BY agent_id;
```

### 7.2 weekly_agent_report

```sql
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.weekly_agent_report` (
  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 1: PRIMARY KEYS
  -- ═══════════════════════════════════════════════════════════════════════
  agent_id STRING NOT NULL,           -- Agent identifier
  week_start DATE NOT NULL,           -- Monday of the week

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 2: METADATA
  -- ═══════════════════════════════════════════════════════════════════════
  generated_at TIMESTAMP,
  week_end DATE,                      -- Sunday of the week
  business_line STRING,
  team STRING,

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 3: WEEK METRICS (Aggregated from daily_agent_summary)
  -- ═══════════════════════════════════════════════════════════════════════
  total_calls INT64,                  -- Sum of all calls in week
  days_with_calls INT64,              -- Number of days with activity

  -- Week average scores (weighted by daily call_count)
  week_avg_empathy FLOAT64,
  week_avg_compliance FLOAT64,
  week_avg_resolution FLOAT64,
  week_avg_professionalism FLOAT64,
  week_avg_efficiency FLOAT64,
  week_avg_de_escalation FLOAT64,
  week_avg_overall FLOAT64,

  -- Week resolution rate
  week_resolution_rate FLOAT64,

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 4: DAILY BREAKDOWN (For charts/visualization)
  -- ═══════════════════════════════════════════════════════════════════════
  daily_scores JSON,                  -- [
                                      --   {"date": "2026-01-06", "avg_overall": 8.5, "calls": 5},
                                      --   {"date": "2026-01-07", "avg_overall": 8.8, "calls": 6},
                                      --   ...
                                      -- ]

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 5: RECURRING PATTERNS WITH EVIDENCE
  -- Issues and strengths that appeared multiple days
  -- ═══════════════════════════════════════════════════════════════════════
  recurring_issues_with_evidence JSON,  -- [
                                        --   {
                                        --     "issue_type": "efficiency_on_complex_calls",
                                        --     "days_occurred": 4,
                                        --     "total_occurrences": 8,
                                        --     "pattern": "Hardship and complaint calls exceed time targets",
                                        --     "example_conversations": ["conv-123", "conv-456"],
                                        --     "typical_quote": "Let me explain that again..."
                                        --   },
                                        --   ...
                                        -- ]
  recurring_strengths_with_evidence JSON, -- [
                                          --   {
                                          --     "strength_type": "de_escalation",
                                          --     "days_occurred": 5,
                                          --     "success_rate": "12 of 14 cases",
                                          --     "pattern": "Consistently calms frustrated customers",
                                          --     "best_example_conv": "conv-789",
                                          --     "example_quote": "I hear your frustration..."
                                          --   },
                                          --   ...
                                          -- ]
  issue_pattern JSON,                   -- {"compliance": 8, "efficiency": 12, ...}

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 6: TREND VS PREVIOUS WEEK WITH EVIDENCE
  -- Shows what changed AND why it changed
  -- ═══════════════════════════════════════════════════════════════════════
  prev_week_avg_overall FLOAT64,
  prev_week_total_calls INT64,        -- For sample size context

  -- Deltas (this week - last week)
  empathy_delta FLOAT64,
  compliance_delta FLOAT64,
  resolution_delta FLOAT64,
  professionalism_delta FLOAT64,
  efficiency_delta FLOAT64,
  de_escalation_delta FLOAT64,
  overall_delta FLOAT64,

  trend_summary STRING,               -- "Overall improving" / "Mixed" / "Declining"

  trends_with_evidence JSON,          -- [
                                      --   {
                                      --     "dimension": "empathy",
                                      --     "direction": "improving",
                                      --     "delta": 0.5,
                                      --     "this_week": 8.4,
                                      --     "last_week": 7.9,
                                      --     "evidence": "Consistently validated customer emotions",
                                      --     "best_example_quote": "I hear your frustration...",
                                      --     "best_example_conv": "conv-123"
                                      --   },
                                      --   {
                                      --     "dimension": "efficiency",
                                      --     "direction": "declining",
                                      --     "delta": -0.3,
                                      --     "this_week": 7.7,
                                      --     "last_week": 8.0,
                                      --     "evidence": "Thursday/Friday calls averaged 15+ minutes",
                                      --     "common_issue": "Over-explaining payment options"
                                      --   },
                                      --   ...
                                      -- ]

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 7: CONVERSATIONS TO REVIEW (Best/Worst from week)
  -- Concrete examples to learn from
  -- ═══════════════════════════════════════════════════════════════════════
  exemplary_conversations JSON,       -- Top 3 best conversations
                                      -- [
                                      --   {
                                      --     "conversation_id": "conv-123",
                                      --     "overall_score": 9.5,
                                      --     "date": "2026-01-08",
                                      --     "call_type": "hardship",
                                      --     "summary": "Perfect hardship handling",
                                      --     "key_moment_quote": "I understand...",
                                      --     "why_exemplary": "Strong de-escalation + compliance"
                                      --   },
                                      --   ...
                                      -- ]

  needs_review_conversations JSON,    -- Top 3 worst conversations
                                      -- [
                                      --   {
                                      --     "conversation_id": "conv-456",
                                      --     "overall_score": 6.2,
                                      --     "date": "2026-01-09",
                                      --     "call_type": "complaint",
                                      --     "primary_issue": "Efficiency - call lasted 22 mins",
                                      --     "coaching_point": "Review transitions between topics"
                                      --   },
                                      --   ...
                                      -- ]

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 8: LLM GENERATED (Evidence-based narratives)
  -- ═══════════════════════════════════════════════════════════════════════
  weekly_narrative STRING,            -- Evidence-based summary:
                                      -- "This was a solid week for Alex with 28 calls.
                                      -- Empathy improved notably (+0.4) - Alex consistently
                                      -- validated emotions, especially in the hardship call
                                      -- (conv-123) saying 'I hear your frustration'.
                                      -- Efficiency declined (-0.3), primarily on Thurs/Fri
                                      -- where complex calls exceeded 15 minutes."

  trend_analysis STRING,              -- "IMPROVING: Empathy (+0.5) - consistent validation
                                      -- phrases. De-escalation (+0.3) - calmed 12 of 14
                                      -- frustrated customers. DECLINING: Efficiency (-0.3)
                                      -- - complex calls taking too long. STABLE: Compliance
                                      -- (9.0→9.1) - excellent verification practices."

  action_items ARRAY<STRING>,         -- ["Review conv-456 and conv-789 for efficiency patterns",
                                      --  "Practice 'acknowledge and move on' technique",
                                      --  "Continue strong de-escalation - it's working!"]

  recommended_focus STRING,           -- Primary focus for next week

  -- ═══════════════════════════════════════════════════════════════════════
  -- SECTION 9: VERSIONING
  -- ═══════════════════════════════════════════════════════════════════════
  model_version STRING,
  prompt_version STRING
)
PARTITION BY week_start
CLUSTER BY agent_id;
```

---

## 8. SQL Aggregation Queries

### 8.1 Daily Metrics Aggregation

```sql
-- Query: Aggregate today's coaching results for one agent
-- Input: @agent_id, @date
-- Output: Metrics for daily_agent_summary

WITH coaching_data AS (
  SELECT
    c.conversation_id,
    c.empathy_score,
    c.compliance_score,
    c.resolution_score,
    c.professionalism_score,
    c.efficiency_score,
    c.de_escalation_score,
    c.overall_score,
    c.call_type,
    c.situation_summary,
    c.key_moment_turn,
    c.key_moment_quote,
    c.coaching_points,
    c.strengths,
    c.resolution_achieved
  FROM `{project}.{dataset}.coach_analysis` c
  WHERE c.agent_id = @agent_id
    AND DATE(c.analyzed_at) = @date
),

metrics AS (
  SELECT
    COUNT(*) as call_count,
    AVG(empathy_score) as avg_empathy,
    AVG(compliance_score) as avg_compliance,
    AVG(resolution_score) as avg_resolution,
    AVG(professionalism_score) as avg_professionalism,
    AVG(efficiency_score) as avg_efficiency,
    AVG(de_escalation_score) as avg_de_escalation,
    AVG(overall_score) as avg_overall,
    SAFE_DIVIDE(
      COUNTIF(resolution_achieved = TRUE),
      COUNT(*)
    ) as resolution_rate
  FROM coaching_data
),

-- Best conversation
best_conv AS (
  SELECT
    conversation_id,
    overall_score,
    call_type,
    situation_summary,
    key_moment_quote
  FROM coaching_data
  ORDER BY overall_score DESC
  LIMIT 1
),

-- Worst conversation
worst_conv AS (
  SELECT
    conversation_id,
    overall_score,
    call_type,
    situation_summary,
    coaching_points
  FROM coaching_data
  ORDER BY overall_score ASC
  LIMIT 1
),

-- Issue counts (flatten coaching_points and count by category)
issue_counts AS (
  SELECT
    -- Extract category from coaching point title or use default
    CASE
      WHEN LOWER(cp) LIKE '%compliance%' THEN 'compliance'
      WHEN LOWER(cp) LIKE '%empathy%' THEN 'empathy'
      WHEN LOWER(cp) LIKE '%efficiency%' THEN 'efficiency'
      WHEN LOWER(cp) LIKE '%resolution%' THEN 'resolution'
      ELSE 'other'
    END as category,
    COUNT(*) as count
  FROM coaching_data,
  UNNEST(coaching_points) as cp
  GROUP BY category
),

-- Previous day for trend
prev_day AS (
  SELECT avg_overall
  FROM `{project}.{dataset}.daily_agent_summary`
  WHERE agent_id = @agent_id
    AND date = DATE_SUB(@date, INTERVAL 1 DAY)
)

SELECT
  @agent_id as agent_id,
  @date as date,
  CURRENT_TIMESTAMP() as generated_at,
  m.*,
  (SELECT TO_JSON_STRING(STRUCT(conversation_id, overall_score, call_type,
                                 situation_summary as summary, key_moment_quote))
   FROM best_conv) as best_conversation,
  (SELECT TO_JSON_STRING(STRUCT(conversation_id, overall_score, call_type,
                                 situation_summary as summary, coaching_points as issues))
   FROM worst_conv) as worst_conversation,
  (SELECT TO_JSON_STRING(ARRAY_AGG(STRUCT(category, count)))
   FROM issue_counts) as issue_counts,
  (SELECT avg_overall FROM prev_day) as prev_day_avg_overall,
  m.avg_overall - COALESCE((SELECT avg_overall FROM prev_day), m.avg_overall) as overall_delta
FROM metrics m;
```

### 8.2 Weekly Metrics Aggregation

```sql
-- Query: Aggregate week's daily summaries for one agent
-- Input: @agent_id, @week_start, @week_end
-- Output: Metrics for weekly_agent_report

WITH daily_data AS (
  SELECT *
  FROM `{project}.{dataset}.daily_agent_summary`
  WHERE agent_id = @agent_id
    AND date BETWEEN @week_start AND @week_end
),

week_metrics AS (
  SELECT
    SUM(call_count) as total_calls,
    COUNT(*) as days_with_calls,
    -- Weighted averages by call_count
    SAFE_DIVIDE(SUM(avg_empathy * call_count), SUM(call_count)) as week_avg_empathy,
    SAFE_DIVIDE(SUM(avg_compliance * call_count), SUM(call_count)) as week_avg_compliance,
    SAFE_DIVIDE(SUM(avg_resolution * call_count), SUM(call_count)) as week_avg_resolution,
    SAFE_DIVIDE(SUM(avg_professionalism * call_count), SUM(call_count)) as week_avg_professionalism,
    SAFE_DIVIDE(SUM(avg_efficiency * call_count), SUM(call_count)) as week_avg_efficiency,
    SAFE_DIVIDE(SUM(avg_de_escalation * call_count), SUM(call_count)) as week_avg_de_escalation,
    SAFE_DIVIDE(SUM(avg_overall * call_count), SUM(call_count)) as week_avg_overall,
    SAFE_DIVIDE(SUM(resolution_rate * call_count), SUM(call_count)) as week_resolution_rate
  FROM daily_data
),

-- Daily breakdown for charts
daily_breakdown AS (
  SELECT ARRAY_AGG(
    STRUCT(date, avg_overall, call_count as calls)
    ORDER BY date
  ) as daily_scores
  FROM daily_data
),

-- Previous week for trend
prev_week AS (
  SELECT
    week_avg_empathy,
    week_avg_compliance,
    week_avg_resolution,
    week_avg_professionalism,
    week_avg_efficiency,
    week_avg_de_escalation,
    week_avg_overall
  FROM `{project}.{dataset}.weekly_agent_report`
  WHERE agent_id = @agent_id
    AND week_start = DATE_SUB(@week_start, INTERVAL 7 DAY)
),

-- Best conversations this week
best_convs AS (
  SELECT ARRAY_AGG(
    STRUCT(conversation_id, overall_score, call_type, situation_summary, DATE(analyzed_at) as date)
    ORDER BY overall_score DESC
    LIMIT 3
  ) as exemplary
  FROM `{project}.{dataset}.coach_analysis`
  WHERE agent_id = @agent_id
    AND DATE(analyzed_at) BETWEEN @week_start AND @week_end
),

-- Worst conversations this week
worst_convs AS (
  SELECT ARRAY_AGG(
    STRUCT(conversation_id, overall_score, call_type, coaching_points as issues, DATE(analyzed_at) as date)
    ORDER BY overall_score ASC
    LIMIT 3
  ) as needs_review
  FROM `{project}.{dataset}.coach_analysis`
  WHERE agent_id = @agent_id
    AND DATE(analyzed_at) BETWEEN @week_start AND @week_end
)

SELECT
  @agent_id as agent_id,
  @week_start as week_start,
  @week_end as week_end,
  CURRENT_TIMESTAMP() as generated_at,
  wm.*,
  (SELECT daily_scores FROM daily_breakdown) as daily_scores,
  (SELECT week_avg_overall FROM prev_week) as prev_week_avg_overall,
  wm.week_avg_empathy - COALESCE((SELECT week_avg_empathy FROM prev_week), wm.week_avg_empathy) as empathy_delta,
  wm.week_avg_compliance - COALESCE((SELECT week_avg_compliance FROM prev_week), wm.week_avg_compliance) as compliance_delta,
  wm.week_avg_overall - COALESCE((SELECT week_avg_overall FROM prev_week), wm.week_avg_overall) as overall_delta,
  (SELECT exemplary FROM best_convs) as exemplary_conversations,
  (SELECT needs_review FROM worst_convs) as needs_review_conversations
FROM week_metrics wm;
```

---

## 9. LLM Summary Generation

### 9.1 Daily Summary Prompt

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DAILY SUMMARY LLM PROMPT                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  SYSTEM PROMPT:                                                            │
│  ═══════════════                                                           │
│                                                                             │
│  You are a coaching analyst for a contact center. Generate a brief daily  │
│  coaching summary for an agent based on their performance metrics.         │
│                                                                             │
│  Your output must be constructive, specific, and actionable.              │
│  Focus on both strengths and areas for improvement.                       │
│                                                                             │
│  ───────────────────────────────────────────────────────────────────────── │
│                                                                             │
│  USER PROMPT:                                                              │
│  ═════════════                                                             │
│                                                                             │
│  Generate a daily coaching summary for this agent.                        │
│                                                                             │
│  ## Agent Information                                                      │
│  - Agent ID: {agent_id}                                                   │
│  - Date: {date}                                                           │
│  - Team: {team}                                                           │
│  - Business Line: {business_line}                                         │
│                                                                             │
│  ## Today's Performance                                                    │
│  - Calls Handled: {call_count}                                            │
│  - Overall Score: {avg_overall}/10 ({trend_direction} from yesterday)     │
│  - Score Change: {overall_delta:+.1f} vs yesterday                        │
│                                                                             │
│  ### Dimension Scores                                                      │
│  - Empathy: {avg_empathy}/10                                              │
│  - Compliance: {avg_compliance}/10                                        │
│  - Resolution: {avg_resolution}/10                                        │
│  - Professionalism: {avg_professionalism}/10                              │
│  - Efficiency: {avg_efficiency}/10                                        │
│  - De-escalation: {avg_de_escalation}/10                                  │
│                                                                             │
│  ### Issues Identified                                                     │
│  {issue_counts_formatted}                                                 │
│                                                                             │
│  ### Best Conversation Today                                              │
│  - ID: {best_conv.conversation_id}                                        │
│  - Score: {best_conv.overall_score}/10                                    │
│  - Type: {best_conv.call_type}                                            │
│  - Summary: {best_conv.summary}                                           │
│  - Key Moment: "{best_conv.key_moment_quote}"                             │
│                                                                             │
│  ### Conversation Needing Attention                                       │
│  - ID: {worst_conv.conversation_id}                                       │
│  - Score: {worst_conv.overall_score}/10                                   │
│  - Type: {worst_conv.call_type}                                           │
│  - Issues: {worst_conv.issues}                                            │
│                                                                             │
│  ───────────────────────────────────────────────────────────────────────── │
│                                                                             │
│  OUTPUT FORMAT (JSON):                                                     │
│  ═════════════════════                                                     │
│                                                                             │
│  {                                                                         │
│    "daily_narrative": "2-3 sentence summary of the day's performance",    │
│    "focus_area": "single dimension to focus on (e.g., 'efficiency')",     │
│    "coaching_advice": "2-3 sentences of specific, actionable advice",     │
│    "key_wins": ["win 1", "win 2"]                                         │
│  }                                                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Weekly Summary Prompt

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WEEKLY SUMMARY LLM PROMPT                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  SYSTEM PROMPT:                                                            │
│  ═══════════════                                                           │
│                                                                             │
│  You are a coaching analyst generating a weekly performance report for    │
│  a contact center agent. Analyze trends, identify patterns, and provide   │
│  actionable recommendations for the coming week.                          │
│                                                                             │
│  ───────────────────────────────────────────────────────────────────────── │
│                                                                             │
│  USER PROMPT:                                                              │
│  ═════════════                                                             │
│                                                                             │
│  Generate a weekly coaching report for this agent.                        │
│                                                                             │
│  ## Agent Information                                                      │
│  - Agent ID: {agent_id}                                                   │
│  - Week: {week_start} to {week_end}                                       │
│  - Team: {team}                                                           │
│                                                                             │
│  ## Week Summary                                                           │
│  - Total Calls: {total_calls}                                             │
│  - Days Active: {days_with_calls}                                         │
│  - Overall Score: {week_avg_overall}/10                                   │
│  - Change vs Last Week: {overall_delta:+.1f}                              │
│                                                                             │
│  ### Dimension Scores & Trends                                            │
│  | Dimension       | Score | vs Last Week |                               │
│  |-----------------|-------|--------------|                               │
│  | Empathy         | {emp} | {emp_delta}  |                               │
│  | Compliance      | {cmp} | {cmp_delta}  |                               │
│  | Resolution      | {res} | {res_delta}  |                               │
│  | Professionalism | {pro} | {pro_delta}  |                               │
│  | Efficiency      | {eff} | {eff_delta}  |                               │
│  | De-escalation   | {des} | {des_delta}  |                               │
│                                                                             │
│  ### Daily Progression                                                     │
│  {daily_scores_formatted}                                                 │
│                                                                             │
│  ### Recurring Issues This Week                                           │
│  {recurring_issues}                                                       │
│                                                                             │
│  ### Exemplary Conversations                                              │
│  {exemplary_conversations_formatted}                                      │
│                                                                             │
│  ### Conversations Needing Review                                         │
│  {needs_review_formatted}                                                 │
│                                                                             │
│  ───────────────────────────────────────────────────────────────────────── │
│                                                                             │
│  OUTPUT FORMAT (JSON):                                                     │
│  ═════════════════════                                                     │
│                                                                             │
│  {                                                                         │
│    "weekly_narrative": "3-5 sentence summary of the week",                │
│    "trend_analysis": "Analysis of what's improving vs declining",         │
│    "action_items": ["action 1", "action 2", "action 3"],                  │
│    "recommended_focus": "Primary area to focus on next week"              │
│  }                                                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.3 Example LLM Output

**Daily Summary Example:**
```json
{
  "daily_narrative": "Alex had a strong day handling 5 calls with an overall score of 8.5/10, up 0.3 from yesterday. Empathy (9.2) and de-escalation (8.8) were standout areas, while efficiency (7.5) remains an area for growth.",

  "focus_area": "efficiency",

  "coaching_advice": "Consider structuring calls with a brief agenda upfront to improve efficiency. The hardship call (conv-123) is an excellent example of balancing thoroughness with time management - review the key moment where you summarized the customer's situation before offering solutions.",

  "key_wins": [
    "Excellent hardship case handling with strong de-escalation",
    "100% compliance on identity verification"
  ]
}
```

**Weekly Summary Example:**
```json
{
  "weekly_narrative": "This was a solid week for Alex with 28 calls handled across 5 days, averaging 8.4/10 overall. The week showed steady improvement in empathy (+0.4) and compliance (+0.2) compared to last week. Efficiency declined slightly (-0.3), primarily due to longer call times on Thursday and Friday.",

  "trend_analysis": "Empathy and de-escalation are trending positively, with Alex showing consistent improvement in validating customer emotions. Compliance remains strong at 9.1. Efficiency is the main concern, dropping from 8.0 to 7.7, particularly on complex hardship cases where calls exceeded 15 minutes.",

  "action_items": [
    "Review the three efficiency-flagged calls to identify time sinks",
    "Practice the 'summarize-before-solve' technique from Monday's exemplary call",
    "Continue the strong empathy approach - it's working well"
  ],

  "recommended_focus": "efficiency"
}
```

---

## 10. RAG Considerations

### 10.1 Does Summary Generation Need RAG?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RAG DECISION FOR SUMMARIES                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   QUESTION: Should we retrieve policy documents for summaries?             │
│                                                                             │
│   ═══════════════════════════════════════════════════════════════════════  │
│                                                                             │
│   PER-CONVERSATION COACHING (existing):                                    │
│   • YES - needs RAG                                                        │
│   • Why: Evaluating compliance requires knowing the policies               │
│   • Example: "Did agent offer hardship program per policy X?"              │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                             │
│   DAILY/WEEKLY SUMMARY (new):                                              │
│   • NO - does NOT need RAG                                                 │
│   • Why: Summarizing pre-computed scores, not evaluating compliance        │
│   • Input: Already-evaluated coaching results with scores                  │
│   • Task: Narrative generation, trend analysis, advice                     │
│                                                                             │
│   ═══════════════════════════════════════════════════════════════════════  │
│                                                                             │
│   EXCEPTION: Future Enhancement                                            │
│   • Could add RAG for training recommendations                             │
│   • "Based on efficiency issues, recommend: Training Module X"             │
│   • NOT in MVP scope                                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Summary: RAG Not Required

| Feature | Needs RAG? | Reason |
|---------|------------|--------|
| Per-conversation coaching | YES | Evaluate against policies |
| Daily summary | NO | Summarize pre-computed scores |
| Weekly summary | NO | Aggregate summaries |
| Training recommendations | FUTURE | Match issues to training modules |

---

## 11. CLI Commands

### 11.1 Command Structure

```bash
# Daily summary for specific agent and date
cc-coach summary daily --agent AGT-001 --date 2026-01-06

# Daily summary for all agents yesterday (batch)
cc-coach summary daily --date yesterday

# Weekly summary for specific agent
cc-coach summary weekly --agent AGT-001 --week 2026-01-06

# Weekly summary (auto-detect last complete week)
cc-coach summary weekly --agent AGT-001 --week last

# Output as JSON
cc-coach summary daily --agent AGT-001 --date today --json
```

### 11.2 CLI Output Example

```
╭─────────────────────────────────────────────────────────────────╮
│          DAILY COACHING SUMMARY - Alex (AGT-001)                │
│                     January 6, 2026                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CALLS: 5          OVERALL: 8.5/10 (↑ 0.3 vs yesterday)        │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Dimension Scores                                        │   │
│  │  ─────────────────────────────────────────────────────── │   │
│  │  Empathy         ████████████████████░░░░  9.2          │   │
│  │  Compliance      █████████████████████░░░  9.5          │   │
│  │  Resolution      ████████████████████░░░░  8.5          │   │
│  │  Professionalism █████████████████████░░░  9.0          │   │
│  │  Efficiency      ███████████████░░░░░░░░░  7.5 ← Focus  │   │
│  │  De-escalation   ████████████████████░░░░  8.8          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  NARRATIVE                                                      │
│  ─────────                                                      │
│  Alex had a strong day handling 5 calls with an overall score  │
│  of 8.5/10, up 0.3 from yesterday. Empathy (9.2) and           │
│  de-escalation (8.8) were standout areas, while efficiency     │
│  (7.5) remains an area for growth.                             │
│                                                                 │
│  COACHING ADVICE                                                │
│  ───────────────                                                │
│  Consider structuring calls with a brief agenda upfront to     │
│  improve efficiency. Review conv-123 as a model for balancing  │
│  thoroughness with time management.                            │
│                                                                 │
│  KEY WINS                                                       │
│  ────────                                                       │
│  ✓ Excellent hardship case handling with strong de-escalation │
│  ✓ 100% compliance on identity verification                   │
│                                                                 │
│  CONVERSATIONS                                                  │
│  ─────────────                                                  │
│  Best:  conv-123 (9.5) - Hardship case with excellent outcome │
│  Review: conv-456 (6.2) - Efficiency issues on complaint call │
│                                                                 │
╰─────────────────────────────────────────────────────────────────╯
```

---

## 12. Implementation Plan

### 12.1 Implementation Order

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    IMPLEMENTATION PHASES                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   PHASE 1: BigQuery Schema                                                 │
│   ════════════════════════                                                 │
│   □ Create daily_agent_summary table                                       │
│   □ Create weekly_agent_report table                                       │
│   □ Add indexes/clustering                                                 │
│                                                                             │
│   PHASE 2: SQL Aggregation Service                                         │
│   ════════════════════════════════                                         │
│   □ Create cc_coach/services/aggregation.py                               │
│   □ Implement daily metrics query                                          │
│   □ Implement weekly metrics query                                         │
│   □ Implement trend calculation                                            │
│                                                                             │
│   PHASE 3: Summary Agent (LLM)                                             │
│   ════════════════════════════                                             │
│   □ Create cc_coach/agents/summary_agent.py                               │
│   □ Implement daily summary prompt                                         │
│   □ Implement weekly summary prompt                                        │
│   □ Add output validation (Pydantic)                                       │
│                                                                             │
│   PHASE 4: Orchestrator                                                    │
│   ════════════════════════                                                 │
│   □ Create cc_coach/services/summary.py                                   │
│   □ Wire aggregation → LLM → storage                                       │
│   □ Add monitoring/tracing                                                 │
│                                                                             │
│   PHASE 5: CLI Commands                                                    │
│   ════════════════════════                                                 │
│   □ Add 'cc-coach summary daily' command                                  │
│   □ Add 'cc-coach summary weekly' command                                 │
│   □ Add display formatting                                                 │
│                                                                             │
│   PHASE 6: Testing & Verification                                          │
│   ════════════════════════════════                                         │
│   □ Generate daily summary for test agent                                  │
│   □ Generate weekly summary for test agent                                 │
│   □ Verify BQ storage                                                      │
│   □ Verify CLI output                                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 12.2 File Structure

```
cc_coach/
├── agents/
│   ├── conversation_coach.py    # Existing per-conversation coach
│   └── summary_agent.py         # NEW: Daily/weekly summary LLM
├── services/
│   ├── coaching.py              # Existing orchestrator
│   ├── aggregation.py           # NEW: SQL aggregation queries
│   └── summary.py               # NEW: Summary orchestrator
├── schemas/
│   ├── coaching_output.py       # Existing
│   ├── daily_summary.py         # NEW: Daily summary schema
│   └── weekly_summary.py        # NEW: Weekly summary schema
├── prompts/
│   ├── coach_prompt.py          # Existing
│   ├── daily_summary_prompt.py  # NEW
│   └── weekly_summary_prompt.py # NEW
└── cli.py                       # Add summary commands
```

### 12.3 Dependencies

| Dependency | Purpose | Already Installed? |
|------------|---------|-------------------|
| google-cloud-bigquery | BQ queries | Yes |
| google-genai | LLM calls | Yes |
| pydantic | Schema validation | Yes |
| rich | CLI formatting | Yes |

No new dependencies required.

---

## 13. Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PERIOD SUMMARY DESIGN SUMMARY                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   WHAT WE'RE BUILDING:                                                     │
│   • Daily agent summaries (compressed from day's coaching)                 │
│   • Weekly agent reports (compressed from week's daily summaries)          │
│                                                                             │
│   DATA FLOW:                                                               │
│   coach_analysis → SQL aggregation → LLM narrative → BQ storage           │
│                                                                             │
│   KEY DECISIONS:                                                           │
│   • RAG not needed (summarizing pre-computed scores)                       │
│   • Weekly builds on daily (progressive compression)                       │
│   • Store both raw metrics AND LLM outputs                                 │
│   • Same model as per-conversation (gemini-2.5-flash)                      │
│                                                                             │
│   TABLES:                                                                  │
│   • daily_agent_summary (partitioned by date)                             │
│   • weekly_agent_report (partitioned by week_start)                       │
│                                                                             │
│   CLI:                                                                     │
│   • cc-coach summary daily --agent X --date Y                             │
│   • cc-coach summary weekly --agent X --week Y                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## References

- [HLD.md - Section 6.4-6.5](./HLD.md) - Original table designs
- [HLD.md - Section 7.5](./HLD.md) - Multi-level coaching architecture
- [adk_runtime_deployment.md](./adk_runtime_deployment.md) - CLI command design
