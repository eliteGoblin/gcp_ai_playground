# Conversation Coach CLI

Local orchestration CLI for the CCAI Insights + AI Coaching pipeline.

## Features

- **Ingest conversations** from local filesystem or GCS into CCAI Insights
- **Manage conversation registry** in BigQuery (idempotent UPSERT)
- **Explore pipeline data** for debugging and verification
- **Production-grade code** with type hints, Pydantic models, and unit tests

## Installation

```bash
# From the cli directory
pip install -e ".[dev]"
```

## Quick Start

```bash
# 1. Initialize BigQuery tables
cc-coach init

# 2. Check pipeline status
cc-coach status

# 3. Ingest conversations from local data
cc-coach ingest local ../data/dev 2025-12-28

# 4. Ingest from GCS bucket
cc-coach ingest gcs 2025-12-28

# 5. Explore registry
cc-coach registry list
cc-coach registry get <conversation-id>

# 6. Explore CCAI Insights data
cc-coach explore insights-list
cc-coach explore conversation <conversation-id>

# 7. Run arbitrary BigQuery queries
cc-coach explore query "SELECT status, COUNT(*) FROM conversation_coach.conversation_registry GROUP BY status"
```

## Configuration

Environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `CC_PROJECT_ID` | `vertexdemo-481519` | GCP Project ID |
| `CC_REGION` | `us-central1` | GCP Region |
| `CC_GCS_BUCKET_DEV` | `vertexdemo-481519-cc-dev` | Dev data bucket |
| `CC_BQ_DATASET` | `conversation_coach` | BigQuery dataset |
| `CC_BQ_LOCATION` | `US` | BigQuery location |
| `CC_INSIGHTS_LOCATION` | `us-central1` | CCAI Insights location |
| `CC_LOG_LEVEL` | `INFO` | Logging level |

## Commands

### `cc-coach init`
Initialize BigQuery dataset and tables.

### `cc-coach status`
Show pipeline status with conversation counts by status.

### `cc-coach ingest local <data-dir> <date-folder>`
Ingest conversations from local filesystem.

Options:
- `--dry-run`: Don't make API calls
- `--skip-analysis`: Skip CCAI Insights analysis

### `cc-coach ingest gcs <date-folder>`
Ingest conversations from GCS bucket.

Options:
- `--bucket, -b`: GCS bucket override
- `--dry-run`: Don't make API calls
- `--skip-analysis`: Skip CCAI Insights analysis

### `cc-coach registry list`
List conversations in the registry.

Options:
- `--status, -s`: Filter by status (NEW, INGESTED, ENRICHED, etc.)
- `--limit, -n`: Number of results

### `cc-coach registry get <conversation-id>`
Get details for a specific conversation.

### `cc-coach explore conversation <conversation-id>`
Explore a conversation's data in CCAI Insights.

### `cc-coach explore insights-list`
List conversations in CCAI Insights.

Options:
- `--filter, -f`: Filter expression
- `--limit, -n`: Number of results

### `cc-coach explore query <sql>`
Execute a BigQuery SQL query.

Options:
- `--format, -f`: Output format (table, json)

## Pipeline Status Flow

```
NEW → INGESTED → ENRICHED → COACHED
         ↓           ↓         ↓
       FAILED      FAILED    FAILED
```

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=cc_coach --cov-report=html

# Type checking
mypy cc_coach

# Linting
ruff check cc_coach
```

## Architecture

```
cc_coach/
├── cli.py              # Typer CLI entry point
├── config.py           # Pydantic Settings
├── models/
│   ├── conversation.py # Transcription, Metadata models
│   └── registry.py     # ConversationRegistry model
├── services/
│   ├── bigquery.py     # BigQuery operations (UPSERT, queries)
│   ├── gcs.py          # GCS operations
│   └── insights.py     # CCAI Insights API
└── utils/
    └── logging.py      # Rich logging setup
```

## BigQuery Tables

| Table | Purpose |
|-------|---------|
| `conversation_registry` | Pipeline state tracking (idempotency) |
| `ci_enrichment` | CCAI Insights analysis results |
| `coaching_cards` | AI-generated coaching outputs |

## Future Enhancements

- [ ] Cloud Run deployment for scheduled processing
- [ ] DLP integration for PII redaction
- [ ] CoachAgent integration (Vertex AI Agent Engine)
- [ ] Weekly aggregation job
