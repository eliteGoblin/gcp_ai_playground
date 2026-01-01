# Conversation Coach - Data Formats

## Overview

This document describes the data formats used in the Conversation Coach pipeline:

1. **Internal Format** - Our human-readable format for raw data storage
2. **CCAI Format** - Google's required format for Conversational Insights API

The CLI automatically converts from Internal → CCAI format during ingestion.

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SOURCE: Raw conversation data                                               │
│  Location: gs://bucket/YYYY-MM-DD/uuid/                                     │
│  Files:                                                                      │
│    - transcription.json (Internal Format)                                   │
│    - metadata.json (Internal Format)                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ cc-coach pipeline ingest-ci
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CONVERTED: CCAI-compatible transcript                                       │
│  Location: gs://bucket/ccai-transcripts/uuid.json                           │
│  Format: Google CCAI JsonConversationInput                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ CCAI Insights API
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ANALYSIS: CCAI Insights results                                             │
│  Contains: Sentiment, intents, entities                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Internal Format (transcription.json)

Our human-readable format with additional metadata for pipeline tracking.

### Schema

```json
{
  "conversation_id": "uuid",
  "channel": "VOICE | CHAT | EMAIL",
  "language": "en-AU",
  "started_at": "ISO8601 timestamp",
  "ended_at": "ISO8601 timestamp",
  "duration_sec": 508,
  "turns": [
    {
      "turn_index": 0,
      "speaker": "AGENT | CUSTOMER",
      "text": "Message text...",
      "ts_offset_sec": 0
    }
  ]
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `conversation_id` | string | Yes | UUID for the conversation |
| `channel` | string | Yes | Communication channel: VOICE, CHAT, EMAIL |
| `language` | string | Yes | BCP-47 language code (e.g., "en-AU") |
| `started_at` | string | Yes | ISO8601 timestamp when call started |
| `ended_at` | string | Yes | ISO8601 timestamp when call ended |
| `duration_sec` | integer | Yes | Total duration in seconds |
| `turns` | array | Yes | Ordered list of conversation turns |

### Turn Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `turn_index` | integer | Yes | Zero-based turn index |
| `speaker` | string | Yes | Who spoke: "AGENT" or "CUSTOMER" |
| `text` | string | Yes | The spoken/written text |
| `ts_offset_sec` | integer | Yes | Seconds from call start |

### Example

```json
{
  "conversation_id": "2b6f5c61-9e3a-4e47-8b8c-3f0c5f6c2d0e",
  "channel": "VOICE",
  "language": "en-AU",
  "started_at": "2025-12-28T14:20:02+11:00",
  "ended_at": "2025-12-28T14:28:30+11:00",
  "duration_sec": 508,
  "turns": [
    {
      "turn_index": 0,
      "speaker": "AGENT",
      "text": "Good afternoon, Example Loans support...",
      "ts_offset_sec": 0
    },
    {
      "turn_index": 1,
      "speaker": "CUSTOMER",
      "text": "Yeah, hi. Your app is saying my repayment failed...",
      "ts_offset_sec": 6
    }
  ]
}
```

---

## 2. Internal Format (metadata.json)

Call metadata for labeling and filtering in CCAI Insights.

### Schema

```json
{
  "conversation_id": "uuid",
  "call_timestamp": "ISO8601 timestamp",
  "agent_id": "L5512",
  "team": "LOAN_TEAM_1",
  "queue": "SUPPORT",
  "site": "SYD",
  "business_line": "LOANS",
  "direction": "INBOUND | OUTBOUND",
  "call_outcome": "RESOLVED_WITH_ACTION | ESCALATED | ..."
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `conversation_id` | string | Yes | Must match transcription.json |
| `call_timestamp` | string | Yes | ISO8601 timestamp |
| `agent_id` | string | Yes | Agent identifier |
| `team` | string | Yes | Team name |
| `queue` | string | Yes | Call queue |
| `site` | string | Yes | Site location code |
| `business_line` | string | Yes | Business line (LOANS, CREDIT_CARDS, etc.) |
| `direction` | string | Yes | INBOUND or OUTBOUND |
| `call_outcome` | string | Yes | Outcome classification |

### Example

```json
{
  "conversation_id": "2b6f5c61-9e3a-4e47-8b8c-3f0c5f6c2d0e",
  "call_timestamp": "2025-12-28T14:20:02+11:00",
  "agent_id": "L5512",
  "team": "LOAN_TEAM_1",
  "queue": "SUPPORT",
  "site": "SYD",
  "business_line": "LOANS",
  "direction": "INBOUND",
  "call_outcome": "RESOLVED_WITH_ACTION"
}
```

---

## 3. CCAI Format (Google's Required Format)

Google Conversational Insights requires a specific JSON format. The CLI converts automatically.

**Reference**: https://cloud.google.com/contact-center/insights/docs/conversation-data-format

### Schema

```json
{
  "conversation_info": {
    "categories": [
      {"display_name": "Category Name"}
    ]
  },
  "entries": [
    {
      "text": "Message text...",
      "role": "AGENT | CUSTOMER | AUTOMATED_AGENT | END_USER",
      "userId": "1",
      "startTimestampUsec": "1234567890000000"
    }
  ]
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `conversation_info` | object | No | Optional metadata |
| `conversation_info.categories` | array | No | Custom categories for topic detection |
| `entries` | array | Yes | Chronologically ordered messages |

### Entry Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | The message text |
| `role` | string | Yes | One of: AGENT, CUSTOMER, AUTOMATED_AGENT, END_USER |
| `userId` | string | Yes | Participant identifier (same user = same ID) |
| `startTimestampUsec` | string | Yes | Microseconds since Unix epoch (as string) |

### Example (What CLI Generates)

```json
{
  "entries": [
    {
      "text": "Good afternoon, Example Loans support...",
      "role": "AGENT",
      "userId": "2",
      "startTimestampUsec": "1766892002000000"
    },
    {
      "text": "Yeah, hi. Your app is saying my repayment failed...",
      "role": "CUSTOMER",
      "userId": "1",
      "startTimestampUsec": "1766892008000000"
    }
  ]
}
```

---

## 4. Format Conversion

The CLI handles conversion in `cc_coach/services/insights.py`:

### Conversion Logic

```python
# insights.py:_upload_ccai_transcript()

# Internal format → CCAI format mapping:
# - turns[].speaker "AGENT"    → role "AGENT"
# - turns[].speaker "CUSTOMER" → role "CUSTOMER"
# - userId: CUSTOMER=1, AGENT=2
# - ts_offset_sec → startTimestampUsec (microseconds from epoch)
```

### Key Transformations

| Internal Format | CCAI Format | Notes |
|-----------------|-------------|-------|
| `turns` | `entries` | Array rename |
| `speaker: "AGENT"` | `role: "AGENT"` | Direct mapping |
| `speaker: "CUSTOMER"` | `role: "CUSTOMER"` | Direct mapping |
| (derived) | `userId: "1"` | CUSTOMER = 1 |
| (derived) | `userId: "2"` | AGENT = 2 |
| `ts_offset_sec` + `started_at` | `startTimestampUsec` | Calculated: epoch + offset in microseconds |

### Channel Mapping (CCAI API)

When creating the CCAI conversation, channels are assigned:

| userId | Channel Tag | Role |
|--------|-------------|------|
| 1 | Channel 1 | CUSTOMER |
| 2 | Channel 2 | AGENT |

This is why CI analysis shows `channelTag: 1` for customer sentiment.

---

## 5. Storage Locations

| Format | Location | Purpose |
|--------|----------|---------|
| Internal (raw) | `gs://bucket/YYYY-MM-DD/uuid/transcription.json` | Original data |
| Internal (raw) | `gs://bucket/YYYY-MM-DD/uuid/metadata.json` | Original metadata |
| CCAI (converted) | `gs://bucket/ccai-transcripts/uuid.json` | Uploaded to CI |

---

## 6. Generating Test Data

To generate test data in the Internal Format:

```python
# Example: Generate a test conversation
import json
from datetime import datetime, timezone
import uuid

conversation = {
    "conversation_id": str(uuid.uuid4()),
    "channel": "VOICE",
    "language": "en-AU",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "ended_at": datetime.now(timezone.utc).isoformat(),
    "duration_sec": 300,
    "turns": [
        {
            "turn_index": 0,
            "speaker": "AGENT",
            "text": "Hello, how can I help you today?",
            "ts_offset_sec": 0
        },
        {
            "turn_index": 1,
            "speaker": "CUSTOMER",
            "text": "I have a question about my account.",
            "ts_offset_sec": 5
        }
    ]
}

# Save as transcription.json
with open("transcription.json", "w") as f:
    json.dump(conversation, f, indent=2)
```

---

## 7. Validation

The CLI validates data before processing. Common errors:

| Error | Cause | Fix |
|-------|-------|-----|
| "Missing conversation_id" | UUID not in transcription.json | Add conversation_id field |
| "Failed to deserialize" | Wrong CCAI format | Check role values, timestamps as strings |
| "GCS source not provided" | Transcript not in GCS | Ensure file is uploaded before CI call |

---

## References

- [CCAI Insights Data Format](https://cloud.google.com/contact-center/insights/docs/conversation-data-format)
- [CCAI Insights API Reference](https://cloud.google.com/contact-center/insights/docs/reference/rest)
