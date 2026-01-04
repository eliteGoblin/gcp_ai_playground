"""Document ingestion pipeline for RAG knowledge base.

Handles:
1. Scanning local markdown files
2. Parsing YAML frontmatter and validating metadata
3. Syncing to BigQuery (metadata + raw content)
4. Syncing active documents to GCS (for Vertex AI Search indexing)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from google.cloud import storage
from rich.console import Console
from rich.table import Table

from cc_coach.rag.config import RAGConfig
from cc_coach.rag.metadata import MetadataStore
from cc_coach.rag.parser import ParsedDocument, parse_document

console = Console()


@dataclass
class IngestResult:
    """Result of document ingestion."""

    total_files: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[tuple[str, str]] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class DocumentIngester:
    """Document ingestion pipeline for RAG knowledge base."""

    def __init__(self, config: RAGConfig):
        """Initialize ingester.

        Args:
            config: RAG configuration
        """
        self.config = config
        self.metadata_store = MetadataStore(config)
        self._storage_client: Optional[storage.Client] = None

    @property
    def storage_client(self) -> storage.Client:
        """Lazy-load GCS client."""
        if self._storage_client is None:
            self._storage_client = storage.Client(project=self.config.project_id)
        return self._storage_client

    def scan_documents(self, base_path: Path) -> list[Path]:
        """Scan for markdown documents.

        Args:
            base_path: Base directory to scan

        Returns:
            List of markdown file paths
        """
        if not base_path.exists():
            raise FileNotFoundError(f"Documents directory not found: {base_path}")

        # Find all .md files recursively
        md_files = list(base_path.rglob("*.md"))

        # Exclude common non-document files
        excluded_patterns = ["README.md", "CHANGELOG.md", "LICENSE.md"]
        md_files = [
            f for f in md_files
            if f.name not in excluded_patterns
        ]

        return sorted(md_files)

    def ingest_documents(
        self,
        base_path: Optional[Path] = None,
        dry_run: bool = False,
        full_refresh: bool = False,
        skip_gcs: bool = False,
    ) -> IngestResult:
        """Ingest documents from local files to BQ + GCS.

        Args:
            base_path: Base directory containing documents (default: config.documents_path)
            dry_run: If True, only validate without making changes
            full_refresh: If True, re-upload all documents regardless of checksum
            skip_gcs: If True, skip GCS sync (useful when bucket is not available)

        Returns:
            IngestResult with counts and errors
        """
        result = IngestResult()

        if base_path is None:
            base_path = self.config.documents_path

        # Scan for documents
        console.print(f"[blue]Scanning documents in {base_path}...[/blue]")
        try:
            md_files = self.scan_documents(base_path)
        except FileNotFoundError as e:
            result.errors.append(("scan", str(e)))
            return result

        result.total_files = len(md_files)
        console.print(f"[blue]Found {result.total_files} markdown files[/blue]")

        # Get existing checksums for change detection (unless full refresh)
        existing_checksums = {}
        if not full_refresh and not dry_run:
            existing_checksums = self.metadata_store.get_all_checksums()

        # Parse and validate each document
        parsed_docs: list[ParsedDocument] = []
        for file_path in md_files:
            try:
                doc = parse_document(file_path, base_path)
                parsed_docs.append(doc)
            except (ValueError, FileNotFoundError) as e:
                result.errors.append((str(file_path), str(e)))
                console.print(f"[red]Error parsing {file_path}: {e}[/red]")

        if dry_run:
            console.print(f"\n[yellow]Dry run - no changes made[/yellow]")
            self._print_summary(parsed_docs, result)
            return result

        # Sync to BQ
        console.print(f"\n[blue]Syncing to BigQuery...[/blue]")
        for doc in parsed_docs:
            try:
                # Check if we need to update
                if not full_refresh and doc.metadata.uuid in existing_checksums:
                    if existing_checksums[doc.metadata.uuid] == doc.metadata.checksum:
                        result.skipped += 1
                        continue

                # Upsert to BQ
                was_updated = self.metadata_store.upsert_document(
                    doc.metadata, doc.raw_content
                )
                if was_updated:
                    if doc.metadata.uuid in existing_checksums:
                        result.updated += 1
                    else:
                        result.inserted += 1
                else:
                    result.skipped += 1

            except Exception as e:
                result.errors.append((doc.metadata.file_path, str(e)))
                console.print(
                    f"[red]Error upserting {doc.metadata.doc_id}: {e}[/red]"
                )

        # Sync active documents to GCS (unless skipped)
        if skip_gcs:
            console.print(f"\n[yellow]Skipping GCS sync (--skip-gcs flag set)[/yellow]")
        else:
            console.print(f"\n[blue]Syncing active documents to GCS...[/blue]")
            try:
                self._sync_to_gcs(parsed_docs)
            except Exception as e:
                console.print(f"[red]GCS sync failed: {e}[/red]")
                console.print("[yellow]BQ ingestion completed but GCS sync skipped[/yellow]")
                result.errors.append(("gcs_sync", str(e)))

        self._print_summary(parsed_docs, result)
        return result

    def _sync_to_gcs(self, parsed_docs: list[ParsedDocument]) -> None:
        """Sync active documents to GCS for Vertex AI Search indexing.

        Only documents with status='active' are synced.
        Documents removed from active status are deleted from GCS.

        Args:
            parsed_docs: List of parsed documents
        """
        bucket = self.storage_client.bucket(self.config.gcs_bucket)

        # Get active document UUIDs
        active_docs = [d for d in parsed_docs if d.metadata.status == "active"]
        active_uuids = {d.metadata.uuid for d in active_docs}

        # Upload active documents
        # Note: Using .txt extension with text/plain MIME type because
        # Vertex AI Search doesn't support text/markdown
        for doc in active_docs:
            blob_name = f"{self.config.gcs_prefix}/{doc.metadata.uuid}.txt"
            blob = bucket.blob(blob_name)

            # Upload raw content as plain text
            blob.upload_from_string(
                doc.raw_content,
                content_type="text/plain",
            )
            console.print(
                f"  [green]Uploaded[/green] {doc.metadata.doc_id} v{doc.metadata.version} "
                f"-> {blob_name}"
            )

        # List existing blobs and remove any that are no longer active
        prefix = f"{self.config.gcs_prefix}/"
        existing_blobs = list(bucket.list_blobs(prefix=prefix))

        for blob in existing_blobs:
            # Extract UUID from blob name (format: kb/{uuid}.txt or kb/{uuid}.md for legacy)
            blob_name = blob.name
            if blob_name.endswith(".txt") or blob_name.endswith(".md"):
                # Handle both .txt and .md extensions
                uuid = blob_name.replace(prefix, "").replace(".txt", "").replace(".md", "")
                if uuid not in active_uuids:
                    blob.delete()
                    console.print(f"  [yellow]Removed[/yellow] {blob_name} (no longer active)")

    def _print_summary(
        self, parsed_docs: list[ParsedDocument], result: IngestResult
    ) -> None:
        """Print ingestion summary table."""
        console.print("\n[bold]Ingestion Summary[/bold]")

        # Stats table
        stats_table = Table(show_header=False)
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Count", style="green")

        stats_table.add_row("Total files scanned", str(result.total_files))
        stats_table.add_row("Documents inserted", str(result.inserted))
        stats_table.add_row("Documents updated", str(result.updated))
        stats_table.add_row("Documents skipped (unchanged)", str(result.skipped))
        stats_table.add_row("Errors", str(len(result.errors)))

        console.print(stats_table)

        # Documents by status
        if parsed_docs:
            status_counts = {}
            for doc in parsed_docs:
                status = doc.metadata.status
                status_counts[status] = status_counts.get(status, 0) + 1

            console.print("\n[bold]Documents by Status[/bold]")
            status_table = Table(show_header=True)
            status_table.add_column("Status", style="cyan")
            status_table.add_column("Count", style="green")

            for status, count in sorted(status_counts.items()):
                status_table.add_row(status, str(count))

            console.print(status_table)

        # Errors
        if result.errors:
            console.print("\n[bold red]Errors[/bold red]")
            for file_path, error in result.errors:
                console.print(f"  [red]{file_path}:[/red] {error}")

    def ingest_single(
        self,
        file_path: Path,
        base_path: Optional[Path] = None,
        dry_run: bool = False,
    ) -> bool:
        """Ingest a single document.

        Args:
            file_path: Path to the document
            base_path: Base path for relative path computation
            dry_run: If True, only validate without making changes

        Returns:
            True if successful, False if error
        """
        if base_path is None:
            base_path = self.config.documents_path

        try:
            doc = parse_document(file_path, base_path)

            console.print(f"[green]Parsed successfully:[/green] {doc.metadata.doc_id}")
            console.print(f"  Title: {doc.metadata.title}")
            console.print(f"  Version: {doc.metadata.version}")
            console.print(f"  Status: {doc.metadata.status}")
            console.print(f"  UUID: {doc.metadata.uuid}")
            console.print(f"  Checksum: {doc.metadata.checksum[:12]}...")

            if dry_run:
                console.print("\n[yellow]Dry run - no changes made[/yellow]")
                return True

            # Upsert to BQ
            was_changed = self.metadata_store.upsert_document(
                doc.metadata, doc.raw_content
            )

            if was_changed:
                console.print("[green]Document upserted to BigQuery[/green]")
            else:
                console.print("[blue]Document unchanged, skipped[/blue]")

            # Sync to GCS if active
            if doc.metadata.status == "active":
                bucket = self.storage_client.bucket(self.config.gcs_bucket)
                blob_name = f"{self.config.gcs_prefix}/{doc.metadata.uuid}.md"
                blob = bucket.blob(blob_name)
                blob.upload_from_string(
                    doc.raw_content,
                    content_type="text/markdown",
                )
                console.print(f"[green]Uploaded to GCS:[/green] {blob_name}")

            return True

        except (ValueError, FileNotFoundError) as e:
            console.print(f"[red]Error: {e}[/red]")
            return False
