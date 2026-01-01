#!/usr/bin/env python3
"""
Validate conversation data against JSON schemas.

Usage:
    python validate_data.py --data-dir ../data/dev/2025-12-28
    python validate_data.py --file ../data/dev/2025-12-28/<UUID>/metadata.json --type metadata
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
    from jsonschema import validate, ValidationError
except ImportError:
    print("ERROR: jsonschema not installed. Run: pip install jsonschema")
    sys.exit(1)


SCHEMA_DIR = Path(__file__).parent.parent / "schemas"


def load_schema(schema_type: str) -> dict:
    """Load a JSON schema by type (transcription or metadata)."""
    schema_file = SCHEMA_DIR / f"{schema_type}.schema.json"
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema not found: {schema_file}")
    with open(schema_file) as f:
        return json.load(f)


def validate_file(file_path: Path, schema_type: str) -> tuple[bool, str]:
    """
    Validate a single JSON file against its schema.
    Returns (is_valid, error_message).
    """
    try:
        with open(file_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"

    schema = load_schema(schema_type)

    try:
        validate(instance=data, schema=schema)
        return True, ""
    except ValidationError as e:
        return False, f"{e.json_path}: {e.message}"


def validate_conversation(conv_dir: Path) -> dict:
    """
    Validate a conversation directory (metadata.json + transcription.json).
    Returns validation results.
    """
    results = {
        "conversation_id": conv_dir.name,
        "valid": True,
        "errors": []
    }

    metadata_file = conv_dir / "metadata.json"
    transcription_file = conv_dir / "transcription.json"

    # Validate metadata
    if metadata_file.exists():
        is_valid, error = validate_file(metadata_file, "metadata")
        if not is_valid:
            results["valid"] = False
            results["errors"].append(f"metadata.json: {error}")
    else:
        results["valid"] = False
        results["errors"].append("metadata.json: File missing")

    # Validate transcription
    if transcription_file.exists():
        is_valid, error = validate_file(transcription_file, "transcription")
        if not is_valid:
            results["valid"] = False
            results["errors"].append(f"transcription.json: {error}")
    else:
        results["valid"] = False
        results["errors"].append("transcription.json: File missing")

    # Cross-validate: conversation_id must match
    if metadata_file.exists() and transcription_file.exists():
        with open(metadata_file) as f:
            meta_id = json.load(f).get("conversation_id")
        with open(transcription_file) as f:
            trans_id = json.load(f).get("conversation_id")
        if meta_id != trans_id:
            results["valid"] = False
            results["errors"].append(
                f"conversation_id mismatch: metadata={meta_id}, transcription={trans_id}"
            )

    return results


def validate_date_folder(date_dir: Path) -> list[dict]:
    """Validate all conversations in a date folder."""
    results = []
    for conv_dir in sorted(date_dir.iterdir()):
        if conv_dir.is_dir():
            results.append(validate_conversation(conv_dir))
    return results


def main():
    parser = argparse.ArgumentParser(description="Validate conversation data against JSON schemas")
    parser.add_argument("--data-dir", type=Path, help="Date folder to validate (e.g., data/dev/2025-12-28)")
    parser.add_argument("--file", type=Path, help="Single file to validate")
    parser.add_argument("--type", choices=["metadata", "transcription"], help="Schema type for single file")
    args = parser.parse_args()

    if args.file:
        if not args.type:
            # Infer type from filename
            if "metadata" in args.file.name:
                args.type = "metadata"
            elif "transcription" in args.file.name:
                args.type = "transcription"
            else:
                print("ERROR: Cannot infer schema type. Use --type")
                sys.exit(1)

        is_valid, error = validate_file(args.file, args.type)
        if is_valid:
            print(f"VALID: {args.file}")
            sys.exit(0)
        else:
            print(f"INVALID: {args.file}")
            print(f"  Error: {error}")
            sys.exit(1)

    elif args.data_dir:
        if not args.data_dir.exists():
            print(f"ERROR: Directory not found: {args.data_dir}")
            sys.exit(1)

        results = validate_date_folder(args.data_dir)

        valid_count = sum(1 for r in results if r["valid"])
        total_count = len(results)

        print(f"\nValidation Results: {valid_count}/{total_count} valid\n")
        print("-" * 60)

        for r in results:
            status = "VALID" if r["valid"] else "INVALID"
            print(f"{status}: {r['conversation_id']}")
            for error in r["errors"]:
                print(f"  - {error}")

        print("-" * 60)

        if valid_count == total_count:
            print("\nAll conversations valid!")
            sys.exit(0)
        else:
            print(f"\n{total_count - valid_count} conversation(s) have errors")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
