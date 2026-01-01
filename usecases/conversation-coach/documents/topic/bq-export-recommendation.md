# BigQuery Export Strategy Recommendation

## Summary

**Recommendation**: Use **Native CI Export Only** (KISS approach)

The native `export_insights_data` API provides all necessary data. Our custom `ci_enrichment` table adds no unique value and should be deprecated.

## Comparison

| Feature | Native Export | Custom ci_enrichment |
|---------|--------------|---------------------|
| Customer sentiment (overall) | ✅ `clientSentimentScore` | ✅ `customer_sentiment_score` |
| Agent sentiment (overall) | ✅ `agentSentimentScore` (always 0.0) | ⚠️ NULL |
| **Per-turn sentiment** | ✅ `sentences[].sentimentScore` | ❌ Not captured |
| **Transcript** | ✅ Full transcript | ❌ Not captured |
| **Turn count** | ✅ `turnCount` | ❌ Not captured |
| **Duration** | ✅ `durationNanos` | ❌ Not captured |
| Entities | ✅ With speaker, salience, sentiment | ✅ Basic |
| Topics/Intents | ✅ In `sentences[].intentMatchData` | ✅ Array |
| Labels (metadata) | ✅ Full labels array | ❌ Not captured |
| Conversation ID | ✅ Extract from `conversationName` | ✅ Primary key |
| Issues | ✅ CI Issue Models | ❌ Not captured |
| Highlights | ✅ Smart highlights | ❌ Not captured |

## Key Findings

### 1. Native Export Has More Data
- Per-turn sentiment for each sentence
- Full transcript
- Turn count and duration
- All labels we set during ingestion
- Smart highlights and issues

### 2. Agent Sentiment Limitation
Both exports show agent sentiment as 0.0. This is a **CI limitation**, not a data capture issue. CI only analyzes customer sentiment.

**For agent quality assessment**, we need LLM-based analysis (future CoachAgent), not CI sentiment.

### 3. Export Behavior
- `WRITE_TRUNCATE`: Full refresh (recommended for scheduled exports)
- `WRITE_APPEND`: Creates duplicates (no UPSERT)

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  NATIVE CI EXPORT (ccai_insights_export.conversations)          │
│                                                                 │
│  Contains ALL CI data:                                          │
│  - Sentiment (overall + per-turn)                               │
│  - Transcript                                                   │
│  - Entities, intents, highlights                                │
│  - Labels (agent_id, team, queue, etc.)                        │
│  - Duration, turn count                                         │
│                                                                 │
│  Export: Daily scheduled WRITE_TRUNCATE                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  VIEW: conversation_analytics (SQL View)                        │
│                                                                 │
│  Flattens native export for easy querying:                      │
│  - conversation_id (extracted from name)                        │
│  - agent_id, team, queue (from labels)                         │
│  - customer_sentiment_score                                     │
│  - turn_count, duration_sec                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  FUTURE: coaching_cards (LLM-generated)                         │
│                                                                 │
│  Agent coaching insights from Vertex AI:                        │
│  - Tone analysis                                                │
│  - Compliance issues                                            │
│  - Improvement suggestions                                      │
└─────────────────────────────────────────────────────────────────┘
```

## Migration Actions

### 1. Deprecate Custom Export
- Remove `ci_enrichment` table
- Remove `export_to_bq()` function from pipeline
- Keep `conversation_registry` for pipeline state tracking

### 2. Add Scheduled Native Export
```python
# Daily export job
export_insights_data(
    write_disposition="WRITE_TRUNCATE",
    filter=""  # All conversations
)
```

### 3. Create Analytics View
```sql
CREATE OR REPLACE VIEW `conversation_coach.conversation_analytics` AS
SELECT
  SPLIT(conversationName, '/')[SAFE_OFFSET(5)] as conversation_id,
  agentId as agent_id,
  clientSentimentScore as customer_sentiment_score,
  agentSentimentScore as agent_sentiment_score,
  turnCount as turn_count,
  CAST(durationNanos / 1000000000 AS INT64) as duration_sec,
  transcript,
  languageCode,
  medium,
  -- Extract labels
  (SELECT value FROM UNNEST(labels) WHERE key = 'team') as team,
  (SELECT value FROM UNNEST(labels) WHERE key = 'queue') as queue,
  (SELECT value FROM UNNEST(labels) WHERE key = 'site') as site,
  (SELECT value FROM UNNEST(labels) WHERE key = 'call_outcome') as call_outcome,
  TIMESTAMP_SECONDS(loadTimestampUtc) as loaded_at
FROM `ccai_insights_export.conversations`
```

## Cost Impact

- **Reduced complexity**: Less code to maintain
- **No change in CI costs**: Same data, different export method
- **Faster queries**: Native export is optimized

## Per-Turn Sentiment Query Example

```sql
-- Get negative customer turns for toxic call analysis
SELECT
  SPLIT(conversationName, '/')[SAFE_OFFSET(5)] as conversation_id,
  s.sentence,
  CAST(s.sentimentScore AS FLOAT64) as sentiment,
  s.participantRole
FROM `ccai_insights_export.conversations`,
     UNNEST(sentences) as s
WHERE s.participantRole = 'END_USER'
  AND CAST(s.sentimentScore AS FLOAT64) < -0.5
ORDER BY sentiment ASC
```
