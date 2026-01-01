# Production Features - Deferred for Now

This document captures CI features that are valuable for production scale but won't be implemented in the current MVP phase due to training data requirements.

---

## 1. CI Quality AI / QA Scorecard

### What It Does
Auto-answers custom questions for each conversation, producing consistent quality scores.

### How It Works
1. You create a scorecard with up to 50 questions
2. You provide 2,000+ manually labeled conversations as training examples
3. CI calibrates the model (4-8 hours)
4. CI auto-answers questions for new conversations

### Sample Scorecard Configuration

```yaml
Scorecard: "Collections Compliance v1"

Questions:
  - id: Q1
    text: "Did agent verify customer identity?"
    type: yes_no
    tag: Compliance

  - id: Q2
    text: "Did agent inform customer of right to dispute?"
    type: yes_no
    tag: Compliance

  - id: Q3
    text: "Did agent mention hardship options?"
    type: yes_no
    tag: Compliance

  - id: Q4
    text: "Did agent use threatening language?"
    type: yes_no
    tag: Compliance

  - id: Q5
    text: "Rate agent's empathy"
    type: scale_1_5
    tag: Customer_Experience

  - id: Q6
    text: "Was the call resolved?"
    type: multiple_choice
    choices: [Yes, No, Partial]
    tag: Resolution

  - id: Q7
    text: "Did agent follow proper closing script?"
    type: yes_no
    tag: Process

Tags:
  - Compliance: Q1, Q2, Q3, Q4
  - Customer_Experience: Q5
  - Resolution: Q6, Q7
```

### Sample Output (Per-Conversation)

```json
{
  "conversation_id": "a1b2c3d4-toxic-agent-test-0001",

  "qa_scorecard": {
    "scorecard_name": "Collections Compliance v1",
    "overall_score": 2.1,

    "answers": [
      {
        "question_id": "Q1",
        "question": "Did agent verify customer identity?",
        "answer": "Yes",
        "confidence": 0.92,
        "tag": "Compliance"
      },
      {
        "question_id": "Q2",
        "question": "Did agent inform customer of right to dispute?",
        "answer": "No",
        "confidence": 0.88,
        "tag": "Compliance"
      },
      {
        "question_id": "Q3",
        "question": "Did agent mention hardship options?",
        "answer": "No",
        "confidence": 0.95,
        "tag": "Compliance"
      },
      {
        "question_id": "Q4",
        "question": "Did agent use threatening language?",
        "answer": "Yes",
        "confidence": 0.97,
        "tag": "Compliance"
      },
      {
        "question_id": "Q5",
        "question": "Rate agent's empathy",
        "answer": "1",
        "confidence": 0.85,
        "tag": "Customer_Experience"
      },
      {
        "question_id": "Q6",
        "question": "Was the call resolved?",
        "answer": "No",
        "confidence": 0.91,
        "tag": "Resolution"
      }
    ],

    "tag_scores": {
      "Compliance": 1.5,
      "Customer_Experience": 1.0,
      "Resolution": 2.0
    }
  }
}
```

### Requirements
- **Training Data**: 2,000+ conversations with manual labels for each question
- **Calibration Time**: 4-8 hours per scorecard
- **Maintenance**: Re-calibration needed when questions change

### Why Deferred
- We have ~8 test conversations, need 2,000+ for training
- Manual labeling effort required
- ADK LLM coach can do similar scoring without training data

### When to Implement
- When you have accumulated 2,000+ conversations
- When you want deterministic scoring (same input = same output every time)
- When you need to reduce LLM costs at high volume
- When audit requires consistent, reproducible scores

### Migration Path
1. Accumulate conversations over time
2. Use ADK coach outputs as initial labels
3. QA team reviews/corrects labels
4. Train CI Scorecard on corrected labels
5. CI Scorecard handles first-pass scoring
6. ADK Coach handles edge cases + detailed coaching

---

## 2. CI Topic Model

### What It Does
Automatically categorizes conversations by call driver/topic.

### How It Works
1. You provide 1,000+ conversations (minimum)
2. CI trains a topic model (can take hours)
3. CI auto-generates topic names via Gemini
4. New conversations get topic labels

### Sample Topics (Auto-Generated)

```
Topic Model: "Collections Call Drivers v1"

Generated Topics:
├── Payment Plan Request (32%)
│   Description: "Customer inquiring about setting up payment arrangements"
│
├── Hardship Claim (28%)
│   Description: "Customer reporting financial difficulty due to job loss, medical, etc."
│
├── Dispute/Not My Debt (18%)
│   Description: "Customer disputing the validity of the debt"
│
├── Account Inquiry (12%)
│   Description: "Customer asking about balance, payment history, or account status"
│
└── Complaint (10%)
    Description: "Customer expressing dissatisfaction with service or treatment"
```

### Sample Output (Per-Conversation)

```json
{
  "conversation_id": "a1b2c3d4-toxic-agent-test-0001",

  "topic_model": {
    "model_name": "Collections Call Drivers v1",
    "primary_topic": {
      "name": "Hardship Claim",
      "confidence": 0.85
    },
    "secondary_topics": [
      {"name": "Payment Plan Request", "confidence": 0.45},
      {"name": "Complaint", "confidence": 0.30}
    ]
  }
}
```

### Requirements
- **Training Data**: 1,000+ conversations minimum (10,000 recommended)
- **Training Time**: Several hours
- **Granularity Options**: more_coarse, coarse, standard, fine, more_fine

### Why Deferred
- We have ~8 test conversations, need 1,000+ minimum
- Primary value is aggregate analytics (dashboard), not per-conversation coaching
- ADK LLM can categorize calls without training data

### When to Implement
- When you have 1,000+ conversations
- When you want aggregate call driver analytics on dashboard
- When you need trend analysis ("Hardship calls up 20% this week")

### Use Cases (When Implemented)

**Dashboard Analytics**:
```
┌─────────────────────────────────────────────────────────────────┐
│  Top Call Drivers This Week                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Payment Plans ████████████████████████████████ 32%             │
│  Hardship      ████████████████████████████ 28%                 │
│  Disputes      ██████████████████ 18%                           │
│  Inquiries     ████████████ 12%                                 │
│  Complaints    ██████████ 10%                                   │
│                                                                  │
│  Trend: Hardship calls ↑ 20% vs last week                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Weekly Coach Context**:
```
"This week, 40% of your calls were hardship-related.
Consider reviewing the hardship handling playbook."
```

---

## 3. Comparison: Current vs Future CI Features

| Feature | Current (Phase 1) | Future (Prod) |
|---------|-------------------|---------------|
| **Sentiment** | ✅ Enabled | ✅ Keep |
| **Summary** | ✅ Enabled | ✅ Keep |
| **Entities** | ✅ Enabled | ✅ Keep |
| **Phrase Matcher** | 🔜 Adding | ✅ Keep |
| **QA Scorecard** | ❌ Deferred | ✅ Add at 2000+ convos |
| **Topic Model** | ❌ Deferred | ✅ Add at 1000+ convos |

---

## 4. Future Schema Fields (When Implemented)

### ci_enrichment table additions

```python
# Add when QA Scorecard is implemented
("qa_scorecard_name", "STRING"),
("qa_overall_score", "FLOAT"),
("qa_answers", "JSON"),  # Full question/answer pairs
("qa_tag_scores", "JSON"),  # Scores by tag (Compliance, CX, etc.)

# Add when Topic Model is implemented
("topic_model_name", "STRING"),
("primary_topic", "STRING"),
("primary_topic_confidence", "FLOAT"),
("secondary_topics", "JSON"),  # Array of {topic, confidence}
```

---

## 5. Documentation Links

- [Quality AI Basics](https://cloud.google.com/contact-center/insights/docs/qai-basics)
- [Quality AI Setup Guide](https://cloud.google.com/contact-center/insights/docs/qai-setup-guide)
- [Quality AI Best Practices](https://cloud.google.com/contact-center/insights/docs/qai-best-practices)
- [Topic Modeling Overview](https://cloud.google.com/contact-center/insights/docs/topic-modeling-overview)
- [Topic Modeling How-To](https://cloud.google.com/contact-center/insights/docs/topic-modeling)
