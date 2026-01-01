# CCAI Insights - Technical Notes

## 1. Current Create Analysis Code

Location: `cc_coach/services/insights.py:189`

```python
def create_analysis(
    self,
    conversation_name: str,
) -> insights.Analysis:
    """
    Trigger analysis on a conversation.
    """
    request = insights.CreateAnalysisRequest(
        parent=conversation_name,
        analysis=insights.Analysis(),  # Empty = use defaults
    )

    operation = self.client.create_analysis(request=request)
    logger.info(f"Started analysis for {conversation_name}")

    # Wait for completion (blocking)
    result = operation.result()
    logger.info(f"Analysis complete: {result.name}")
    return result
```

**Current behavior**: Uses default annotators. The `Analysis()` object is empty, so CI runs with default settings.

---

## 2. Available Features (AnnotatorSelector)

You can enable/disable specific annotators by setting `analysis.annotator_selector`:

| Annotator | Field | Default | Description |
|-----------|-------|---------|-------------|
| **Sentiment** | `run_sentiment_annotator` | True | Per-turn and overall sentiment |
| **Entity** | `run_entity_annotator` | True | Named entity extraction |
| **Intent** | `run_intent_annotator` | True | Intent/topic detection |
| **Interruption** | `run_interruption_annotator` | True | Detect speaker interruptions |
| **Silence** | `run_silence_annotator` | True | Detect silence periods (audio only) |
| **Phrase Matcher** | `run_phrase_matcher_annotator` | False | Custom phrase detection |
| **Issue Model** | `run_issue_model_annotator` | False | Custom issue classification |
| **Summarization** | `run_summarization_annotator` | False | AI-generated summary |
| **QA Scorecard** | `run_qa_annotator` | False | Quality assurance scoring |

### Example: Enable Summarization

```python
from google.cloud import contact_center_insights_v1 as insights

request = insights.CreateAnalysisRequest(
    parent=conversation_name,
    analysis=insights.Analysis(
        annotator_selector=insights.AnnotatorSelector(
            run_sentiment_annotator=True,
            run_entity_annotator=True,
            run_intent_annotator=True,
            run_summarization_annotator=True,
            summarization_config=insights.AnnotatorSelector.SummarizationConfig(
                summarization_model=insights.AnnotatorSelector.SummarizationConfig.SummarizationModel.BASELINE_MODEL_V2_0
            ),
        )
    ),
)
```

### Summarization Models

| Model | Value | Notes |
|-------|-------|-------|
| BASELINE_MODEL | 1 | Original model |
| BASELINE_MODEL_V2_0 | 2 | Improved model |

---

## 3. Raw Input Payload (CreateAnalysisRequest)

### Minimal (current)

```json
{
  "parent": "projects/38797000650/locations/us-central1/conversations/a1b2c3d4-toxic-agent-test-0001",
  "analysis": {}
}
```

### With Annotator Selection

```json
{
  "parent": "projects/38797000650/locations/us-central1/conversations/a1b2c3d4-toxic-agent-test-0001",
  "analysis": {
    "annotatorSelector": {
      "runSentimentAnnotator": true,
      "runEntityAnnotator": true,
      "runIntentAnnotator": true,
      "runInterruptionAnnotator": true,
      "runSilenceAnnotator": false,
      "runSummarizationAnnotator": true,
      "summarizationConfig": {
        "summarizationModel": "BASELINE_MODEL_V2_0"
      }
    }
  }
}
```

---

## 4. Raw Output Example (Analysis Result)

Conversation: `a1b2c3d4-toxic-agent-test-0001` (toxic debt collection call)

### Summary

| Field | Value |
|-------|-------|
| Turn Count | 39 |
| Duration | 628s |
| Overall Customer Sentiment | -1.0 (very negative) |
| Annotations | 41 (19 sentiment, 22 entity) |
| Entities | 2 |
| Intents | 0 |

### Conversation Object (input stored in CI)

```json
{
  "name": "projects/38797000650/locations/us-central1/conversations/a1b2c3d4-toxic-agent-test-0001",
  "dataSource": {
    "gcsSource": {
      "transcriptUri": "gs://vertexdemo-481519-cc-dev/ccai-transcripts/a1b2c3d4-toxic-agent-test-0001.json"
    }
  },
  "createTime": "2025-12-29T00:29:16.550796635Z",
  "agentId": "M7741",
  "labels": {
    "agent_id": "M7741",
    "call_outcome": "UNRESOLVED",
    "direction": "OUTBOUND",
    "business_line": "COLLECTIONS",
    "queue": "HARDSHIP",
    "team": "COLLECTIONS_TEAM_3",
    "site": "MEL"
  },
  "medium": "PHONE_CALL",
  "languageCode": "en-AU",
  "turnCount": 39,
  "duration": "628s",
  "transcript": {
    "transcriptSegments": [
      {
        "text": "This is Marcus from Apex Collections...",
        "channelTag": 2,
        "segmentParticipant": {
          "role": "HUMAN_AGENT",
          "userId": "2"
        }
      },
      {
        "text": "Yes, this is Michael. What's this about?",
        "channelTag": 1,
        "segmentParticipant": {
          "role": "END_USER",
          "userId": "1"
        },
        "sentiment": {}
      }
    ]
  }
}
```

### Analysis Result (CI output)

```json
{
  "name": "projects/.../analyses/13848965911864781366",
  "createTime": "2025-12-29T00:29:38.972719Z",
  "analysisResult": {
    "callAnalysisMetadata": {
      "annotations": [
        {
          "channelTag": 1,
          "annotationStartBoundary": {
            "transcriptIndex": 3
          },
          "annotationEndBoundary": {
            "transcriptIndex": 3
          },
          "sentimentData": {
            "magnitude": 0.5,
            "score": -0.5
          }
        },
        {
          "channelTag": 1,
          "annotationStartBoundary": {
            "transcriptIndex": 5
          },
          "sentimentData": {
            "magnitude": 1.0,
            "score": -1.0
          }
        }
      ],
      "entities": {
        "entity_1": {
          "displayName": "human being",
          "type": "PERSON",
          "salience": 0.294
        },
        "entity_2": {
          "displayName": "Chen",
          "type": "PERSON",
          "salience": 0.152
        }
      },
      "sentiments": [
        {
          "channelTag": 1,
          "sentimentData": {
            "magnitude": 1.0,
            "score": -1.0
          }
        }
      ],
      "intents": {}
    },
    "endTime": "2025-12-29T00:29:38.938830Z"
  }
}
```

---

## 5. Key Observations

### What CI Provides

| Feature | Customer (Channel 1) | Agent (Channel 2) |
|---------|---------------------|-------------------|
| **Overall Sentiment** | Yes (-1.0 to +1.0) | No (always 0.0) |
| **Per-turn Sentiment** | Yes (in annotations) | No |
| **Entity Extraction** | Yes | Yes |
| **Intent Detection** | Limited (need custom models) | N/A |

### What CI Does NOT Provide

- **Agent sentiment analysis** - CI only analyzes customer sentiment
- **Agent tone/quality assessment** - Need LLM for this
- **Compliance checking** - Need custom phrase matchers or LLM
- **Call summarization** - Available but requires enabling

### Channel Mapping

| Channel | Role | UserId |
|---------|------|--------|
| 1 | END_USER (Customer) | 1 |
| 2 | HUMAN_AGENT (Agent) | 2 |

---

## 6. Enabling Additional Features

### A. Summarization

Requires enabling in annotator_selector:

```python
annotator_selector=insights.AnnotatorSelector(
    run_summarization_annotator=True,
    summarization_config=insights.AnnotatorSelector.SummarizationConfig(
        summarization_model=insights.AnnotatorSelector.SummarizationConfig.SummarizationModel.BASELINE_MODEL_V2_0
    ),
)
```

Output appears in: `conversation.latest_summary`

### B. Phrase Matchers (Custom Compliance)

1. Create phrase matcher in CI console or via API
2. Reference in analysis:

```python
annotator_selector=insights.AnnotatorSelector(
    run_phrase_matcher_annotator=True,
    phrase_matchers=["projects/.../phraseMatchers/compliance-phrases"],
)
```

### C. Issue Models (Custom Classification)

1. Create issue model in CI console
2. Reference in analysis:

```python
annotator_selector=insights.AnnotatorSelector(
    run_issue_model_annotator=True,
    issue_models=["projects/.../issueModels/call-types"],
)
```

---

## 7. Full Raw Output File

Complete CI output saved to: `/tmp/ci_full_output.json` (42KB)

To regenerate:
```bash
source .venv/bin/activate
export GOOGLE_APPLICATION_CREDENTIALS=/home/parallels/.config/gcloud/vertex-ai-demo-key.json
python3 -c "
from google.cloud import contact_center_insights_v1 as insights
from google.protobuf.json_format import MessageToDict
import json

client = insights.ContactCenterInsightsClient()
request = insights.GetConversationRequest(
    name='projects/38797000650/locations/us-central1/conversations/a1b2c3d4-toxic-agent-test-0001',
    view=insights.ConversationView.FULL
)
conv = client.get_conversation(request=request)
print(json.dumps(MessageToDict(conv._pb), indent=2))
"
```

---

## 8. Recommendations

### For MVP (Current)
- Default annotators are sufficient
- Customer sentiment + entities + topics working

### For Production
1. **Enable Summarization** - Useful for call notes
2. **Create Phrase Matchers** - For compliance keywords
3. **Consider Issue Models** - For call categorization

### For Agent Quality (Future)
- CI cannot assess agent behavior
- Use Vertex AI / Gemini for agent coaching
- Analyze: tone, empathy, compliance, professionalism

---

## 9. Test Case Comparison: Toxic vs Exemplary Agent

### Overview

| Metric | Toxic Agent | Exemplary Agent |
|--------|-------------|-----------------|
| Conversation ID | `a1b2c3d4-toxic-agent-test-0001` | `e5f6g7h8-exemplary-agent-test-0001` |
| Customer Sentiment | **-1.0** (very negative) | **+1.0** (very positive) |
| Turn Count | 39 | 29 |
| Duration | 630s | 825s |
| Outcome | UNRESOLVED | RESOLVED_WITH_ACTION |
| Per-turn sentiments | 18 (all negative) | 13 (negative→positive journey) |

### Toxic Agent: Per-Turn Sentiment

Customer remains consistently negative throughout:

| Turn | Sentiment |
|------|-----------|
| 3 | -0.5 |
| 5-37 | -1.0 (consistently) |

### Exemplary Agent: Per-Turn Sentiment Journey

Shows successful de-escalation:

| Turn | Sentiment | Notes |
|------|-----------|-------|
| 1 | -1.0 | Customer starts angry (45min wait) |
| 5 | -1.0 | Still upset (cancer diagnosis) |
| 7 | -1.0 | Frustrated with previous agent |
| 9 | -0.5 | Starting to calm |
| 11 | **+0.5** | First positive shift! |
| 15 | **+1.0** | Appreciating help |
| 21-27 | **+1.0** | Full positive, grateful |

### Key Differences in Agent Behavior

**Toxic Agent (Marcus)**:
- Dismisses customer's hardship
- Uses threatening language ("legal action")
- No empathy or flexibility
- Escalates conflict

**Exemplary Agent (Sarah)**:
- Acknowledges customer's situation
- Offers hardship hold (90 days)
- Waives $150 in fees
- Provides financial counselling referral
- Escalates previous agent's misconduct

---

## 10. Enabling Summarization

### Prerequisite: Enable Dialogflow API

Summarization requires Dialogflow API. Enable it in GCP Console:

```
https://console.developers.google.com/apis/api/dialogflow.googleapis.com/overview?project=vertexdemo-481519
```

Or via gcloud (needs serviceusage.services.enable permission):
```bash
gcloud services enable dialogflow.googleapis.com --project=vertexdemo-481519
```

### Updated Code (insights.py)

```python
def create_analysis(
    self,
    conversation_name: str,
    enable_summarization: bool = True,
) -> insights.Analysis:
    annotator_selector = None
    if enable_summarization:
        annotator_selector = insights.AnnotatorSelector(
            run_sentiment_annotator=True,
            run_entity_annotator=True,
            run_intent_annotator=True,
            run_summarization_annotator=True,
            summarization_config=insights.AnnotatorSelector.SummarizationConfig(
                summarization_model=insights.AnnotatorSelector.SummarizationConfig.SummarizationModel.BASELINE_MODEL_V2_0
            ),
        )

    request = insights.CreateAnalysisRequest(
        parent=conversation_name,
        analysis=insights.Analysis(
            annotator_selector=annotator_selector,
        ),
    )
    # ... rest of method
```

### After Enabling Dialogflow API

Re-run analysis to get summaries:

```bash
# Delete old analysis
cc-coach explore insights-list  # Find conversation
# Re-analyze
cc-coach pipeline analyze-ci <conversation-id>
```

Summary appears in: `conversation.latest_summary.text`

### Summarization Output Examples

**Toxic Agent (a1b2c3d4-toxic-agent-test-0001):**
```
situation
The customer is in debt to FastCash Loans for $12,847.50, which is 97 days past due.
They are unable to pay due to job loss and medical bills.

action
The agent demanded immediate payment, initially the full amount, then a minimum of $3,000
to avoid legal action, and finally $5,000. The agent refused the customer's offer of $200
and then $500 monthly payments. The agent threatened legal action, wage garnishment, and
property liens.

resolution
N
```

**Exemplary Agent (e5f6g7h8-exemplary-agent-test-0001):**
```
situation
The customer is being harassed by the company with calls and letters and is facing
financial hardship due to his wife's cancer diagnosis and related medical bills. He was
previously misinformed that he needed to pay $2,000 immediately to avoid legal action.
He also mentions $150 in late fees from the last two months.

action
The agent placed the customer's account on a 90-day hardship hold, waiving all fees and
collection activity. The agent also waived $150 in late fees, provided details for a free
financial counselling service, and escalated the issue of misinformation given by a
previous agent.

resolution
Y
```

---

## 11. Local Test Data

All test conversations stored in:
```
artifacts/data/dev/2025-12-28/
├── a1b2c3d4-toxic-agent-test-0001/      # Toxic agent (39 turns, -1.0 sentiment)
├── e5f6g7h8-exemplary-agent-test-0001/  # Exemplary agent (29 turns, +1.0 sentiment)
├── b8d4e2f9.../                          # Payment plan agreed (+0.75)
├── 2b6f5c61.../                          # Loan support (+0.5)
└── ... (7 more conversations)
```
