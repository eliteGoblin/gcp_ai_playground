# How To: BigQuery Schema Migration

This document covers schema management and migration strategies for the Conversation Coach BigQuery tables.

## Schema-as-Code Overview

Our schemas are defined in JSON files under `cc_coach/schemas/`:

```
cc_coach/schemas/
├── __init__.py              # Schema loader utilities
├── coach_analysis.json      # Per-conversation coaching output
├── daily_agent_summary.json # Daily aggregation per agent
└── weekly_agent_report.json # Weekly report per agent
```

### Using Schema Definitions

```python
from cc_coach.schemas import (
    load_schema,           # Get raw JSON schema
    get_bq_schema,         # Get BigQuery SchemaField list
    get_schema_metadata,   # Get table config (clustering, partition)
    get_schema_version,    # Get schema version string
    compare_schemas,       # Compare schema to existing table
)

# Load and use schema
fields = get_bq_schema("coach_analysis")
metadata = get_schema_metadata("coach_analysis")
version = get_schema_version("coach_analysis")

print(f"Schema version: {version}")
print(f"Clustering: {metadata.get('clustering_fields')}")
```

---

## BigQuery Schema Migration Strategies

Unlike relational databases with tools like Alembic, BigQuery has specific constraints:

### What BigQuery Allows

| Operation | Supported | Notes |
|-----------|-----------|-------|
| Add new columns | Yes | Always safe |
| Remove columns | No | Must recreate table |
| Rename columns | No | Must recreate table |
| Change column type | Limited | Only widening (STRING -> longer STRING) |
| Add nested fields to RECORD | Yes | Safe |
| Change NULLABLE to REQUIRED | No | Must recreate table |
| Change REQUIRED to NULLABLE | Yes | Safe |

### Migration Strategy by Scenario

#### Scenario 1: Adding New Columns (Safe)

This is the most common case and is fully supported:

```python
from google.cloud import bigquery
from cc_coach.schemas import get_bq_schema

client = bigquery.Client()
table_ref = f"{project}.{dataset}.coach_analysis"

# Get existing table
table = client.get_table(table_ref)

# Get new schema (with additional fields)
new_fields = get_bq_schema("coach_analysis")

# Update the schema (only adds new fields)
table.schema = new_fields
client.update_table(table, ["schema"])
print("Schema updated successfully")
```

#### Scenario 2: Breaking Changes (Requires Table Recreation)

For changes like column removal, type changes, or renaming:

```python
from google.cloud import bigquery

client = bigquery.Client()
project = "your-project"
dataset = "cc_coach"
table_name = "coach_analysis"

# Step 1: Create new table with new schema
new_table_name = f"{table_name}_v2"
new_table = bigquery.Table(
    f"{project}.{dataset}.{new_table_name}",
    schema=get_bq_schema("coach_analysis")
)
client.create_table(new_table)

# Step 2: Copy data with transformation
copy_query = f"""
INSERT INTO `{project}.{dataset}.{new_table_name}`
SELECT
    conversation_id,
    agent_id,
    -- Add column mappings here
    -- new_column_name AS old_column_name (if renamed)
    -- CAST expressions (if type changed)
FROM `{project}.{dataset}.{table_name}`
"""
client.query(copy_query).result()

# Step 3: Validate row counts match
validation_query = f"""
SELECT
    (SELECT COUNT(*) FROM `{project}.{dataset}.{table_name}`) as old_count,
    (SELECT COUNT(*) FROM `{project}.{dataset}.{new_table_name}`) as new_count
"""
result = list(client.query(validation_query).result())[0]
assert result.old_count == result.new_count, "Row count mismatch!"

# Step 4: Rename tables (atomic swap)
# Delete old (or rename to _backup)
client.delete_table(f"{project}.{dataset}.{table_name}")
# Rename new to original name
# Note: BQ doesn't have rename, so we copy and delete
copy_to_original = f"""
CREATE TABLE `{project}.{dataset}.{table_name}` AS
SELECT * FROM `{project}.{dataset}.{new_table_name}`
"""
client.query(copy_to_original).result()
client.delete_table(f"{project}.{dataset}.{new_table_name}")
```

---

## Pre-Deployment Schema Validation

Before deploying schema changes, validate compatibility:

```python
from google.cloud import bigquery
from cc_coach.schemas import compare_schemas

client = bigquery.Client()
table = client.get_table("project.dataset.coach_analysis")

# Compare against new schema definition
result = compare_schemas("coach_analysis", table)

if result["compatible"]:
    print("Schema change is safe (additive only)")
    print(f"New fields: {result['new_fields']}")
else:
    print("WARNING: Breaking changes detected!")
    print(f"Removed fields: {result['removed_fields']}")
    print(f"Type changes: {result['type_changes']}")
    print("Manual migration required.")
```

---

## Schema Versioning Convention

Schema files include a version field:

```json
{
  "$id": "coach_analysis",
  "version": "2.0.0",
  ...
}
```

### Semantic Versioning for Schemas

| Version Bump | Meaning | Migration |
|--------------|---------|-----------|
| Patch (1.0.1) | Description/doc changes only | None |
| Minor (1.1.0) | New optional columns added | Auto (additive) |
| Major (2.0.0) | Breaking changes | Manual migration |

### Tracking Applied Versions

Consider adding a schema_versions table:

```sql
CREATE TABLE IF NOT EXISTS `project.dataset.schema_versions` (
    table_name STRING NOT NULL,
    schema_version STRING NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    applied_by STRING,
    migration_notes STRING
);

-- Record migration
INSERT INTO `project.dataset.schema_versions`
(table_name, schema_version, applied_by, migration_notes)
VALUES
('coach_analysis', '2.0.0', 'deploy_script', 'Added evidence-based assessments');
```

---

## Production Migration Workflow

### 1. Development

```bash
# Edit schema JSON file
vim cc_coach/schemas/coach_analysis.json

# Bump version
# Update version field: "version": "2.1.0"

# Validate locally
python -c "from cc_coach.schemas import get_bq_schema; print(get_bq_schema('coach_analysis'))"
```

### 2. Pre-Production Validation

```python
# In CI/CD or manual check
from cc_coach.schemas import compare_schemas

result = compare_schemas("coach_analysis", existing_table)
if not result["compatible"]:
    raise ValueError(f"Breaking change detected: {result}")
```

### 3. Apply Migration

```bash
# For safe (additive) changes
python -c "
from cc_coach.services.bigquery import BigQueryService
svc = BigQueryService()
svc.update_table_schema('coach_analysis')
"

# For breaking changes - use manual process above
```

### 4. Post-Migration Validation

```sql
-- Verify new columns exist
SELECT column_name, data_type
FROM `project.dataset.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'coach_analysis'
ORDER BY ordinal_position;

-- Spot check data
SELECT * FROM `project.dataset.coach_analysis` LIMIT 5;
```

---

## Backfill Strategies

When adding new columns that require historical data:

### Option 1: NULL for Historical (Fast)

New columns are NULL for existing rows. Only new inserts have values.

```python
# Just add column - existing rows have NULL
table.schema = new_fields
client.update_table(table, ["schema"])
```

### Option 2: Default Value Backfill

```sql
-- After adding column
UPDATE `project.dataset.coach_analysis`
SET new_column = 'default_value'
WHERE new_column IS NULL;
```

### Option 3: Computed Backfill

```sql
-- Backfill based on existing data
UPDATE `project.dataset.coach_analysis`
SET compliance_breach_count = (
    ARRAY_LENGTH(
        ARRAY(SELECT x FROM UNNEST(issue_types) x WHERE x LIKE 'THREAT_%' OR x LIKE 'MISSING_%' OR x = 'HARASSMENT' OR x = 'PRIVACY_VIOLATION')
    )
)
WHERE compliance_breach_count IS NULL;
```

---

## Comparison: BigQuery vs Alembic

| Feature | Alembic (SQL DBs) | BigQuery |
|---------|-------------------|----------|
| Migration files | Python scripts with up/down | JSON schema + manual scripts |
| Version tracking | alembic_version table | Custom schema_versions table |
| Rollback | Automatic downgrade() | Manual (keep backup tables) |
| Column removal | ALTER TABLE DROP | Table recreation |
| Online migration | Depends on DB | Always online for adds |
| Cost | Compute time | Storage + query costs |

### Why We Don't Use Alembic-Style Tool

1. **BigQuery limitations**: Most DDL changes require table recreation
2. **Scale**: We have few tables, infrequent schema changes
3. **Safety**: BigQuery's additive-only schema updates prevent accidents
4. **Simplicity**: JSON schema + manual migration is sufficient for our needs

---

## Best Practices

1. **Always add columns as NULLABLE** - Required columns need table recreation
2. **Use JSON type for flexible nested data** - Avoids schema changes for nested additions
3. **Test in dev dataset first** - `cc_coach_dev.coach_analysis`
4. **Keep backup before breaking changes** - `coach_analysis_backup_20250101`
5. **Document migrations** - Update schema_versions table
6. **Version your schema files** - Use semantic versioning
7. **Validate before deploy** - Use `compare_schemas()` function

---

## CLI Integration (Future)

Consider adding CLI commands:

```bash
# Validate schema against live table
cc-coach schema validate coach_analysis

# Apply safe schema changes
cc-coach schema apply coach_analysis

# Compare schemas
cc-coach schema diff coach_analysis

# Show current schema version
cc-coach schema version coach_analysis
```
