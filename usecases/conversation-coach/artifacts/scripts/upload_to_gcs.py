#!/usr/bin/env python3
"""
Upload dev conversation data to GCS.

Usage:
    python upload_to_gcs.py --date 2025-12-28 --validate
    python upload_to_gcs.py --date 2025-12-28 --dry-run
    python upload_to_gcs.py --date 2025-12-28
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "dev"
BUCKET = "vertexdemo-481519-cc-dev"


def validate_conversations(date_folder: Path) -> bool:
    """Run schema validation on all conversations."""
    validate_script = Path(__file__).parent / "validate_data.py"
    result = subprocess.run(
        [sys.executable, str(validate_script), "--data-dir", str(date_folder)],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        return False
    return True


def list_files_to_upload(date_folder: Path) -> list[tuple[Path, str]]:
    """
    List all files to upload with their GCS destinations.
    Returns list of (local_path, gcs_path) tuples.
    """
    files = []
    date_str = date_folder.name

    for conv_dir in sorted(date_folder.iterdir()):
        if conv_dir.is_dir():
            conv_id = conv_dir.name
            for json_file in conv_dir.glob("*.json"):
                gcs_path = f"gs://{BUCKET}/{date_str}/{conv_id}/{json_file.name}"
                files.append((json_file, gcs_path))

    return files


def upload_file(local_path: Path, gcs_path: str, dry_run: bool = False) -> bool:
    """Upload a single file to GCS."""
    if dry_run:
        print(f"[DRY RUN] Would upload: {local_path} -> {gcs_path}")
        return True

    result = subprocess.run(
        ["gsutil", "cp", str(local_path), gcs_path],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f"Uploaded: {local_path.name} -> {gcs_path}")
        return True
    else:
        print(f"FAILED: {local_path}")
        print(f"  Error: {result.stderr}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Upload dev data to GCS")
    parser.add_argument("--date", required=True, help="Date folder to upload (e.g., 2025-12-28)")
    parser.add_argument("--validate", action="store_true", help="Validate before upload")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded")
    args = parser.parse_args()

    date_folder = DATA_DIR / args.date

    if not date_folder.exists():
        print(f"ERROR: Date folder not found: {date_folder}")
        sys.exit(1)

    print(f"Source: {date_folder}")
    print(f"Target: gs://{BUCKET}/{args.date}/")
    print("-" * 60)

    # Validate if requested
    if args.validate:
        print("\nValidating data...")
        if not validate_conversations(date_folder):
            print("\nValidation failed. Aborting upload.")
            sys.exit(1)
        print("\nValidation passed. Proceeding with upload.\n")

    # Get files to upload
    files = list_files_to_upload(date_folder)
    print(f"Files to upload: {len(files)}")
    print("-" * 60)

    # Upload files
    success_count = 0
    for local_path, gcs_path in files:
        if upload_file(local_path, gcs_path, args.dry_run):
            success_count += 1

    print("-" * 60)
    print(f"Uploaded: {success_count}/{len(files)} files")

    if success_count == len(files):
        print("\nUpload complete!")
        if not args.dry_run:
            print(f"\nVerify with: gsutil ls gs://{BUCKET}/{args.date}/")
        sys.exit(0)
    else:
        print(f"\n{len(files) - success_count} file(s) failed to upload")
        sys.exit(1)


if __name__ == "__main__":
    main()
