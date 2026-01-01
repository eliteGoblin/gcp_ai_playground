# AI Coach Evaluation Framework

> Design document for measuring and progressively improving the AI Coach system.
> This is a reference for post-MVP evaluation - implementation follows E2E working system.

---

## The Core Challenge: Evaluating an Evaluator

Unlike traditional AI systems with clear ground truth, an AI Coach evaluates subjective human performance. There's no "correct answer" for coaching feedback.

```
Traditional AI:                           AI Coach:
┌─────────┐     ┌────────┐              ┌──────────┐     ┌────────────┐
│ Query   │ ──▶ │ Answer │              │Transcript│ ──▶ │ Assessment │
└─────────┘     └────────┘              └──────────┘     │ + Coaching │
                    │                                    └────────────┘
                    ▼                                          │
              Ground Truth                                     ▼
              (correct answer)                            ??? 🤔
                                                   What's "ground truth"?
```

**Evaluation sources (all imperfect):**
- Expert QA review - expensive, subjective
- Agent improvement over time - lagging indicator, noisy
- Business outcomes - confounded by many factors

---

## Success Definition: Business Terms First

From the book summary - define success in business impact, not "cool demo":

| Business Metric | Definition | How AI Coach Helps |
|----------------|------------|-------------------|
| **QA Coverage** | % of calls reviewed | 2% → 100% (AI reviews all) |
| **Feedback Latency** | Time from call to feedback | 3-5 days → <1 hour |
| **Cost per Review** | Human time + tools | ~$5-10 → ~$0.10 |
| **Compliance Breach Rate** | Violations per 1000 calls | Track reduction |
| **Agent Improvement** | Score trends over time | Track positive trend |

### The Coverage vs Accuracy Tradeoff

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  KEY INSIGHT:                                                        │
│                                                                      │
│  70% accuracy AI at 100% coverage may beat                          │
│  95% accuracy human at 2% coverage                                  │
│                                                                      │
│  Why? Most calls go unreviewed today.                               │
│  A "good enough" AI catches more issues than perfect human sampling.│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4-Layer Metrics Framework

### Layer 1: System Quality (Can We Trust It?)

*"Is the coach's assessment correct?"*

| Metric | What It Measures | Collection Method | Target |
|--------|------------------|-------------------|--------|
| **Human Agreement Rate** | % coach assessments experts agree with | Sample 10-20/week, QA scores same rubric blind | >80% |
| **Consistency Score** | Same input → same output | Run same conversation 3x | <5% variance |
| **Citation Accuracy** | Policy citations are correct | Verify policy_ref against docs | 100% |
| **False Positive Rate** | Flagged violations that aren't | QA reviews flagged convos | <10% |
| **False Negative Rate** | Missed real violations | Audit "clean" conversations | <5% |

**Human Agreement Workflow:**
```
Weekly Calibration:
1. Sample 10-20 conversations (stratified by score buckets)
2. 2+ QA experts score using same rubric (blind to AI output)
3. Compare AI scores vs Expert scores
4. Calculate agreement rate, identify patterns
5. Update prompts/rubric based on systematic disagreements

Agreement Types:
├── Exact: AI score == Expert score
├── Within-1: abs(AI - Expert) <= 1 (for 1-10 scales)
└── Directional: Both agree on good/needs-improvement/critical
```

### Layer 2: Coaching Usefulness (Is It Helpful?)

*"Will agents find this valuable?"*

| Metric | What It Measures | Collection Method | Target |
|--------|------------------|-------------------|--------|
| **Coaching Specificity** | Specific vs generic advice | LLM/human judges "is this actionable?" | >90% |
| **Evidence Quality** | Cites specific transcript moments | Check turn references in output | 100% |
| **Novelty Rate** | Finds issues QA missed | Compare vs human review | Track |
| **Agent Feedback Score** | Agent rates helpfulness | Survey after viewing report | >4.0/5 |
| **Adoption Rate** | % of points agents will apply | Track in interface | >60% |

**Specificity Examples:**

```
BAD (Generic):
┌─────────────────────────────────────────────────────────────────┐
│ "Show more empathy to customers experiencing hardship"          │
│                                                                  │
│ ❌ No specific moment cited                                      │
│ ❌ No suggested alternative phrasing                             │
│ ❌ Could apply to any call                                       │
└─────────────────────────────────────────────────────────────────┘

GOOD (Specific):
┌─────────────────────────────────────────────────────────────────┐
│ "At turn 13, when Mr Chen mentioned his wife's dialysis, you    │
│  immediately pivoted to payment options.                         │
│                                                                  │
│  Try: 'I'm sorry to hear about your wife's situation. That      │
│  must be incredibly stressful. Before we discuss payment, is    │
│  there anything urgent I can help with today?'"                  │
│                                                                  │
│ ✅ Cites specific turn                                           │
│ ✅ Identifies exact behavior                                     │
│ ✅ Provides alternative phrasing                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Layer 3: Business Impact (Does It Work?)

*"Are agents actually improving?"*

| Metric | What It Measures | Collection Method | Target |
|--------|------------------|-------------------|--------|
| **Agent Score Trend** | Empathy/compliance over weeks | Track by agent_id over time | Positive |
| **Repeat Issues Rate** | Same issue flagged repeatedly | Track issue_types by agent | Decreasing |
| **Compliance Breach Rate** | Org-wide violation % | Aggregate from coach_analysis | Decreasing |
| **Customer Sentiment** | CI sentiment by agent | Aggregate from ci_enrichment | Improving |
| **Escalation Rate** | Calls with escalation triggers | Track ci_flags by agent | Decreasing |

**Agent Improvement Visualization:**
```
Agent M7741 - Empathy Score Over Time:

Score
 10 │
  9 │                                              ●
  8 │                                    ●    ●
  7 │                         ●    ●
  6 │              ●    ●
  5 │    ●    ●                                        ← Coaching started
  4 │
    └────┴────┴────┴────┴────┴────┴────┴────┴────▶ Week
        W1   W2   W3   W4   W5   W6   W7   W8
```

### Layer 4: Operational Health (System Status)

*"Is the system running well?"*

| Metric | What It Measures | Collection Method | Target |
|--------|------------------|-------------------|--------|
| **Latency P50/P95** | Time to generate coaching | Pipeline timestamps | P95 <30s |
| **Cost per Conversation** | LLM + infra cost | Token usage + compute | <$0.10 |
| **Throughput** | Conversations/hour | Pipeline metrics | >100/hr |
| **Error Rate** | Failed generations | Pipeline error logs | <1% |
| **Staleness** | Call end → coaching available | Timestamp comparison | <24hr |

---

## Progressive Evaluation Roadmap

### Phase 1: MVP Demo (Current)
Focus: *Get it working E2E*

```
Evaluation: Manual spot-checks only
├── Review 5-10 coaching outputs manually
├── Check coaching makes sense for transcript
├── Verify policy citations exist
└── No formal metrics yet
```

### Phase 2: Pilot (Post-Demo)
Focus: *Establish baselines*

```
Evaluation: Weekly calibration
├── Sample 20 conversations/week for QA review
├── Calculate initial agreement rate
├── Track latency and error rates
├── Collect qualitative feedback
└── Iterate on prompts based on disagreements
```

### Phase 3: Production (Scale)
Focus: *Continuous improvement flywheel*

```
Evaluation: Full framework
├── Automatic evals on 100% (Tier 1)
├── Sampled human review 5-10% (Tier 2)
├── Deep dive on anomalies (Tier 3)
├── Weekly metrics dashboard
└── Monthly calibration reviews
```

---

## Tiered Evaluation Approach

The evaluation paradox: We build AI to replace expensive human QA, but need expensive human QA to evaluate the AI.

**Solution: Focus human effort where it matters most**

```
┌─────────────────────────────────────────────────────────────────────┐
│ TIER 1: Automatic (100% of conversations)                          │
│ ├── Consistency checks (same input → same output?)                 │
│ ├── Format validation (required fields populated?)                 │
│ ├── Citation verification (policy_ref exists?)                     │
│ ├── LLM-as-judge for specificity                                   │
│ └── CI signal correlation (phrase_match → compliance_issue?)       │
├─────────────────────────────────────────────────────────────────────┤
│ TIER 2: Sampled Human Review (5-10% of conversations)              │
│ ├── Random sample from each score bucket                           │
│ ├── Oversample edge cases (score=1 or score=10)                    │
│ ├── Oversample flagged conversations                               │
│ └── Weekly calibration sessions                                     │
├─────────────────────────────────────────────────────────────────────┤
│ TIER 3: Deep Dive (Triggered by anomalies)                         │
│ ├── Agent disputes coaching                                         │
│ ├── Score dramatically different from CI signals                   │
│ ├── Repeat violations after coaching                                │
│ └── System errors or timeouts                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Continuous Improvement Flywheel

```
                    ┌─────────────────┐
                    │ 1. Generate     │
                    │    Coaching     │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ 2a. QA Sample │  │ 2b. Agent     │  │ 2c. Automatic │
│     Review    │  │    Feedback   │  │     Evals     │
│               │  │               │  │               │
│ 10-20/week    │  │ Survey after  │  │ LLM-as-judge  │
│ Expert score  │  │ viewing       │  │ Consistency   │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │ 3. Analyze Disagreements│
              │    & Failure Modes      │
              │                         │
              │ • Where AI != human     │
              │ • What issues missed?   │
              │ • Generic vs specific?  │
              └────────────┬────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │ 4. Update System        │
              │                         │
              │ • Refine prompts        │
              │ • Add examples to RAG   │
              │ • Adjust rubric         │
              │ • Add phrase matchers   │
              └────────────┬────────────┘
                           │
                           └───────────▶ Back to Step 1
```

---

## Launch Readiness Checklist

### MVP/Demo (Minimum Bar)

- [ ] Human agreement rate >70% (on 20 conversation sample)
- [ ] All compliance flags have evidence citations
- [ ] Coaching points are specific (not generic platitudes)
- [ ] Latency <60s for 95% of conversations
- [ ] No hallucinated policy citations (100% accuracy)

### Production (Nice to Have)

- [ ] Human agreement rate >85%
- [ ] Agent feedback score >4.0/5.0
- [ ] Measurable agent improvement trend over 4 weeks
- [ ] Cost <$0.10 per conversation
- [ ] Latency <30s P95

---

## Future: Evaluation Data Model

When ready to implement formal evaluation tracking:

### coach_calibration table
```
calibration_id      STRING (REQUIRED)
conversation_id     STRING
calibration_date    DATE

# AI scores
ai_empathy_score         INTEGER
ai_compliance_score      INTEGER
ai_overall_score         INTEGER
ai_issue_count           INTEGER

# Expert scores
expert_empathy_score     INTEGER
expert_compliance_score  INTEGER
expert_overall_score     INTEGER
expert_issue_count       INTEGER
expert_id                STRING

# Agreement metrics
empathy_agreement        STRING  -- exact/within1/disagree
compliance_agreement     STRING
issues_agreement         FLOAT   -- Jaccard similarity

# Notes
disagreement_notes       STRING
action_taken             STRING  -- prompt_updated, rubric_changed
```

### coach_feedback table
```
feedback_id         STRING (REQUIRED)
conversation_id     STRING
agent_id            STRING
feedback_date       TIMESTAMP

helpfulness_score   INTEGER  -- 1-5
specificity_score   INTEGER  -- 1-5
will_apply          BOOLEAN

comments            STRING
coaching_point_id   STRING  -- which point feedback is about
```

---

## Summary: Mental Model

1. **Start with business value** - coverage × accuracy, not just accuracy
2. **Layer your metrics** - system quality → usefulness → business impact → operations
3. **Tier your evaluation** - auto checks for all, human review for sample, deep dive for anomalies
4. **Build the flywheel** - generate → evaluate → analyze → improve → repeat
5. **Progressive rollout** - spot checks (MVP) → calibration (pilot) → full framework (prod)

**Key insight**: Don't block on perfect evaluation. Get E2E working, then progressively add rigor.

---

## References

- Book: "Quick read summary (highlights)" on AI system evaluation
- Related: `design/solution_roadmap.md` - implementation plan
- Related: `cc_coach/schemas/coach_analysis.json` - output schema
