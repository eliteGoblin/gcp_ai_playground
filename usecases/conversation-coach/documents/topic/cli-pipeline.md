# Conversation Coach CLI - Pipeline Guide

## Overview

The `cc-coach` CLI provides a production-grade pipeline for processing contact center conversations through CCAI Insights and BigQuery.

## Architecture

```
GCS (raw data)
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Register                                           │
│  - Scan GCS for transcription.json + metadata.json          │
│  - Create/update conversation_registry in BigQuery          │
│  - Check if both files present (ready for CI)               │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Ingest to CI                                       │
│  - Convert transcript to CCAI JSON format                   │
│  - Upload to GCS (ccai-transcripts/)                        │
│  - Create conversation in CCAI Insights                     │
│  - Update registry with ci_conversation_name                │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Analyze                                            │
│  - Trigger CCAI Insights analysis                           │
│  - Wait for completion (synchronous)                        │
│  - Store analysis_id in registry                            │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: Export to BQ                                       │
│  - Fetch analysis results from CI                           │
│  - Extract: sentiment, entities, topics/intents             │
│  - Insert into ci_enrichment table                          │
│  - Update registry status to ENRICHED                       │
└─────────────────────────────────────────────────────────────┘
```

## Installation

```bash
cd /home/parallels/devel/gcp_ml_playground/usecases/conversation-coach/artifacts/cli

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install CLI
pip install -e ".[dev]"
```

## Authentication

The CLI uses a service account key for authentication:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/vertex-ai-demo-key.json
```

Required IAM roles for the service account:
- `roles/bigquery.dataEditor`
- `roles/bigquery.jobUser`
- `roles/contactcenterinsights.editor`
- `roles/storage.objectAdmin` (on the GCS bucket)

## Commands

### Initialize Infrastructure

```bash
cc-coach init
```

Creates BigQuery tables:
- `conversation_registry` - Pipeline state tracking
- `ci_enrichment` - CCAI Insights analysis results
- `coaching_cards` - AI coaching outputs (future)

### Check Status

```bash
cc-coach status
```

Shows conversation counts by pipeline status:
- NEW: Registered but not processed
- INGESTED: Sent to CI, awaiting analysis
- ENRICHED: CI analysis complete, exported to BQ
- FAILED: Processing error

### Pipeline Commands

#### Step 1: Register Conversations

```bash
# Register all conversations for a date
cc-coach pipeline register-all 2025-12-28

# Register a single conversation folder
cc-coach pipeline register vertexdemo-481519-cc-dev 2025-12-28/uuid
```

#### Step 2: Ingest to CCAI Insights

```bash
cc-coach pipeline ingest-ci <conversation-id>
```

#### Step 3: Run CI Analysis

```bash
cc-coach pipeline analyze-ci <conversation-id>
```

#### Step 4: Export to BigQuery

```bash
cc-coach pipeline export-bq <conversation-id>
```

#### Combined Processing

```bash
# Process a single conversation (Steps 2-4)
cc-coach pipeline process <conversation-id>

# Process all pending conversations
cc-coach pipeline process-all --status NEW --limit 10
```

### Exploration Commands

```bash
# List conversations in registry
cc-coach registry list --status ENRICHED --limit 20

# Get conversation details
cc-coach registry get <conversation-id>

# Run arbitrary BigQuery queries
cc-coach explore query "SELECT * FROM conversation_coach.ci_enrichment LIMIT 5"

# List conversations in CCAI Insights
cc-coach explore insights-list --limit 10
```

## BigQuery Tables

### conversation_registry

| Column | Type | Description |
|--------|------|-------------|
| conversation_id | STRING | Primary key (UUID) |
| transcript_uri_raw | STRING | GCS URI for transcription.json |
| metadata_uri_raw | STRING | GCS URI for metadata.json |
| has_transcript | BOOLEAN | Transcript file present |
| has_metadata | BOOLEAN | Metadata file present |
| status | STRING | Pipeline status |
| ci_conversation_name | STRING | CCAI Insights resource name |
| ci_analysis_id | STRING | CCAI analysis resource name |
| created_at | TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | Last update time |
| ingested_at | TIMESTAMP | When ingested to CI |
| enriched_at | TIMESTAMP | When CI export completed |

### ci_enrichment

| Column | Type | Description |
|--------|------|-------------|
| conversation_id | STRING | FK to registry |
| ci_conversation_name | STRING | CCAI resource name |
| customer_sentiment_score | FLOAT | Customer sentiment (-1 to 1) |
| customer_sentiment_magnitude | FLOAT | Sentiment magnitude |
| entities | RECORD[] | Extracted entities |
| topics | STRING[] | Detected intents/topics |
| analysis_completed_at | TIMESTAMP | When analysis finished |

## Pipeline Status Flow

```
NEW → INGESTED → ENRICHED → COACHED
        ↓           ↓         ↓
      FAILED      FAILED    FAILED
```

## Data Flow

1. **Raw Data** (`gs://bucket/date/uuid/`):
   - `transcription.json` - Conversation transcript
   - `metadata.json` - Call metadata

2. **CCAI Format** (`gs://bucket/ccai-transcripts/`):
   - Converted JSON in CCAI JsonConversationInput format

3. **BigQuery**:
   - `conversation_registry` - State tracking
   - `ci_enrichment` - Analysis results

## Future Enhancements

- [ ] Cloud Run deployment for event-driven processing
- [ ] GCS trigger → Cloud Run for real-time ingestion
- [ ] DLP integration for PII redaction
- [ ] CoachAgent for AI coaching card generation
- [ ] Weekly aggregation pipeline
