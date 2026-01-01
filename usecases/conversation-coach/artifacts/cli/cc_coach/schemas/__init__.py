"""
BigQuery Schema-as-Code module.

This module provides schema definitions as JSON files and utilities to convert
them to BigQuery SchemaField objects. This enables:
- Version control of schema changes
- Programmatic schema creation and updates
- Schema validation before deployment
- Documentation generation from schema definitions

Usage:
    from cc_coach.schemas import load_schema, get_bq_schema

    # Load the JSON schema
    schema_def = load_schema("coach_analysis")

    # Get BigQuery SchemaField list
    bq_fields = get_bq_schema("coach_analysis")

    # Create table with schema
    from google.cloud import bigquery
    table = bigquery.Table(table_ref, schema=bq_fields)
"""

import json
from pathlib import Path
from typing import Any, Optional

from google.cloud import bigquery


# Schema directory
SCHEMA_DIR = Path(__file__).parent


def load_schema(schema_name: str) -> dict[str, Any]:
    """
    Load a schema definition from JSON file.

    Args:
        schema_name: Name of the schema (without .json extension)

    Returns:
        Schema definition dictionary

    Raises:
        FileNotFoundError: If schema file doesn't exist
    """
    schema_path = SCHEMA_DIR / f"{schema_name}.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path) as f:
        return json.load(f)


def list_schemas() -> list[str]:
    """
    List all available schema names.

    Returns:
        List of schema names (without .json extension)
    """
    return [p.stem for p in SCHEMA_DIR.glob("*.json")]


def _field_to_bq_schema(field: dict[str, Any]) -> bigquery.SchemaField:
    """
    Convert a JSON field definition to BigQuery SchemaField.

    Handles nested RECORD types recursively.

    Args:
        field: Field definition dictionary

    Returns:
        BigQuery SchemaField object
    """
    name = field["name"]
    field_type = field["type"]
    mode = field.get("mode", "NULLABLE")
    description = field.get("description", "")

    # Handle nested RECORD types
    if field_type == "RECORD" and "fields" in field:
        nested_fields = [_field_to_bq_schema(f) for f in field["fields"]]
        return bigquery.SchemaField(
            name=name,
            field_type=field_type,
            mode=mode,
            description=description,
            fields=nested_fields,
        )

    return bigquery.SchemaField(
        name=name,
        field_type=field_type,
        mode=mode,
        description=description,
    )


def get_bq_schema(schema_name: str) -> list[bigquery.SchemaField]:
    """
    Get BigQuery schema fields from a schema definition.

    Args:
        schema_name: Name of the schema (without .json extension)

    Returns:
        List of BigQuery SchemaField objects

    Example:
        >>> fields = get_bq_schema("coach_analysis")
        >>> table = bigquery.Table(table_ref, schema=fields)
    """
    schema_def = load_schema(schema_name)
    return [_field_to_bq_schema(f) for f in schema_def["fields"]]


def get_schema_metadata(schema_name: str) -> dict[str, Any]:
    """
    Get BigQuery table metadata from schema definition.

    Args:
        schema_name: Name of the schema

    Returns:
        Dictionary with table_name, clustering_fields, partition settings
    """
    schema_def = load_schema(schema_name)
    return schema_def.get("bigquery", {})


def get_schema_version(schema_name: str) -> str:
    """
    Get the version string from a schema definition.

    Args:
        schema_name: Name of the schema

    Returns:
        Version string (e.g., "2.0.0")
    """
    schema_def = load_schema(schema_name)
    return schema_def.get("version", "unknown")


def compare_schemas(
    schema_name: str,
    existing_table: bigquery.Table,
) -> dict[str, Any]:
    """
    Compare a JSON schema definition with an existing BigQuery table.

    Args:
        schema_name: Name of the schema
        existing_table: BigQuery Table object to compare against

    Returns:
        Dictionary with:
        - 'compatible': bool - True if new schema is additive only
        - 'new_fields': list - Fields in JSON not in table
        - 'removed_fields': list - Fields in table not in JSON
        - 'type_changes': list - Fields with different types
    """
    new_fields = get_bq_schema(schema_name)
    existing_field_names = {f.name for f in existing_table.schema}
    new_field_names = {f.name for f in new_fields}

    # Find differences
    added = new_field_names - existing_field_names
    removed = existing_field_names - new_field_names

    # Check for type changes (simplified - top level only)
    existing_types = {f.name: f.field_type for f in existing_table.schema}
    new_types = {f.name: f.field_type for f in new_fields}

    type_changes = []
    for name in existing_field_names & new_field_names:
        if existing_types[name] != new_types[name]:
            type_changes.append({
                "field": name,
                "old_type": existing_types[name],
                "new_type": new_types[name],
            })

    # Compatible if only adding fields (BigQuery allows this)
    compatible = len(removed) == 0 and len(type_changes) == 0

    return {
        "compatible": compatible,
        "new_fields": list(added),
        "removed_fields": list(removed),
        "type_changes": type_changes,
    }


# Available schemas
AVAILABLE_SCHEMAS = [
    # Pipeline tables (data flow order)
    "conversation_registry",  # Central registry - tracks lifecycle
    "ci_enrichment",          # CI analysis output - input to ADK Coach
    # ADK Coach output tables
    "coach_analysis",         # Per-conversation coaching
    "daily_agent_summary",    # Daily rollup by agent
    "weekly_agent_report",    # Weekly report by agent
]


__all__ = [
    "load_schema",
    "list_schemas",
    "get_bq_schema",
    "get_schema_metadata",
    "get_schema_version",
    "compare_schemas",
    "AVAILABLE_SCHEMAS",
]
