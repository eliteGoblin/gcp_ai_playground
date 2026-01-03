"""Document parser for YAML frontmatter and markdown content.

Parses markdown documents with YAML frontmatter format:
---
doc_id: POL-002
title: Prohibited Language Guidelines
version: 1.1.0
status: active
doc_type: policy
business_lines: [COLLECTIONS]
...
---
# Document Content
...
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml

from cc_coach.rag.config import (
    REQUIRED_METADATA_FIELDS,
    VALID_DOC_TYPES,
    VALID_STATUSES,
    generate_uuid,
)


@dataclass
class DocumentMetadata:
    """Parsed document metadata from YAML frontmatter."""

    # Required fields
    doc_id: str
    title: str
    version: str
    status: str
    doc_type: str

    # Generated fields
    uuid: str = ""
    file_path: str = ""
    checksum: str = ""

    # Optional scope fields
    business_lines: list[str] = field(default_factory=list)
    queues: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)

    # Optional audit fields
    author: Optional[str] = None
    approved_by: Optional[str] = None
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    last_reviewed: Optional[date] = None

    # Status tracking
    status_reason: Optional[str] = None
    superseded_by: Optional[str] = None


@dataclass
class ParsedDocument:
    """Complete parsed document with metadata and content."""

    metadata: DocumentMetadata
    body: str
    raw_content: str


def compute_checksum(content: str) -> str:
    """Compute SHA-256 checksum of content.

    Args:
        content: Full document content including frontmatter

    Returns:
        Hex-encoded SHA-256 hash
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and body from markdown content.

    Args:
        content: Full markdown content with YAML frontmatter

    Returns:
        Tuple of (metadata dict, body string)

    Raises:
        ValueError: If frontmatter is missing or invalid
    """
    # Match YAML frontmatter between --- delimiters
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        raise ValueError("Document must have YAML frontmatter between --- delimiters")

    yaml_content = match.group(1)
    body = match.group(2)

    try:
        metadata = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML frontmatter: {e}")

    if not isinstance(metadata, dict):
        raise ValueError("YAML frontmatter must be a dictionary")

    return metadata, body


def validate_metadata(metadata: dict[str, Any]) -> list[str]:
    """Validate document metadata.

    Args:
        metadata: Parsed metadata dictionary

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Check required fields
    missing_fields = REQUIRED_METADATA_FIELDS - set(metadata.keys())
    if missing_fields:
        errors.append(f"Missing required fields: {', '.join(sorted(missing_fields))}")

    # Validate status
    status = metadata.get("status")
    if status and status not in VALID_STATUSES:
        errors.append(
            f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )

    # Validate doc_type
    doc_type = metadata.get("doc_type")
    if doc_type and doc_type not in VALID_DOC_TYPES:
        errors.append(
            f"Invalid doc_type '{doc_type}'. Must be one of: {', '.join(sorted(VALID_DOC_TYPES))}"
        )

    # Validate version format (semantic versioning)
    version = metadata.get("version")
    if version:
        if not re.match(r"^\d+\.\d+\.\d+$", version):
            errors.append(
                f"Invalid version format '{version}'. Must be semantic version (e.g., 1.0.0)"
            )

    # Validate doc_id format
    doc_id = metadata.get("doc_id")
    if doc_id:
        if not re.match(r"^[A-Z]+-\d+$", doc_id):
            errors.append(
                f"Invalid doc_id format '{doc_id}'. Must be PREFIX-NUMBER (e.g., POL-001)"
            )

    # Validate array fields
    for field_name in ["business_lines", "queues", "regions"]:
        value = metadata.get(field_name)
        if value is not None and not isinstance(value, list):
            errors.append(f"{field_name} must be a list")

    # Validate date fields
    for field_name in ["effective_date", "expiry_date", "last_reviewed"]:
        value = metadata.get(field_name)
        if value is not None and not isinstance(value, date):
            # Try to parse string date
            if isinstance(value, str):
                try:
                    # YAML should parse dates, but handle string case
                    pass
                except ValueError:
                    errors.append(f"{field_name} must be a valid date (YYYY-MM-DD)")
            else:
                errors.append(f"{field_name} must be a valid date")

    # Validate superseded status has superseded_by
    if status == "superseded" and not metadata.get("superseded_by"):
        errors.append("superseded_by is required when status is 'superseded'")

    return errors


def parse_document(file_path: Path, base_path: Optional[Path] = None) -> ParsedDocument:
    """Parse a markdown document with YAML frontmatter.

    Args:
        file_path: Path to the markdown file
        base_path: Base path for computing relative file_path (default: file's parent)

    Returns:
        ParsedDocument with metadata and content

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If parsing fails or metadata is invalid
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")

    raw_content = file_path.read_text(encoding="utf-8")
    metadata_dict, body = parse_frontmatter(raw_content)

    # Validate metadata
    errors = validate_metadata(metadata_dict)
    if errors:
        raise ValueError(f"Invalid metadata in {file_path}:\n" + "\n".join(f"  - {e}" for e in errors))

    # Compute relative file path
    if base_path:
        relative_path = str(file_path.relative_to(base_path))
    else:
        relative_path = str(file_path)

    # Generate deterministic UUID
    doc_uuid = generate_uuid(relative_path, metadata_dict["version"])

    # Build metadata object
    metadata = DocumentMetadata(
        # Required fields
        doc_id=metadata_dict["doc_id"],
        title=metadata_dict["title"],
        version=metadata_dict["version"],
        status=metadata_dict["status"],
        doc_type=metadata_dict["doc_type"],
        # Generated fields
        uuid=doc_uuid,
        file_path=relative_path,
        checksum=compute_checksum(raw_content),
        # Optional scope fields
        business_lines=metadata_dict.get("business_lines", []),
        queues=metadata_dict.get("queues", []),
        regions=metadata_dict.get("regions", []),
        # Optional audit fields
        author=metadata_dict.get("author"),
        approved_by=metadata_dict.get("approved_by"),
        effective_date=metadata_dict.get("effective_date"),
        expiry_date=metadata_dict.get("expiry_date"),
        last_reviewed=metadata_dict.get("last_reviewed"),
        # Status tracking
        status_reason=metadata_dict.get("status_reason"),
        superseded_by=metadata_dict.get("superseded_by"),
    )

    return ParsedDocument(
        metadata=metadata,
        body=body,
        raw_content=raw_content,
    )


def extract_section_from_snippet(snippet: str) -> str:
    """Extract section header from a text snippet.

    Looks for markdown headers (## Section) in the snippet and extracts
    the section name for citation purposes.

    Args:
        snippet: Text snippet from Vertex AI Search

    Returns:
        Section name if found, "General" otherwise
    """
    # Match ## or ### headers
    match = re.search(r"^#{2,3}\s+(.+?)$", snippet, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "General"
