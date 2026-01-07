"""
Conversation Coach CLI - Main entry point.

Commands:
- init: Initialize BigQuery tables and verify setup
- ingest: Ingest conversations from GCS into CCAI Insights
- registry: Manage conversation registry
- explore: Explore pipeline data for debugging
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from cc_coach.config import get_settings
from cc_coach.models.registry import ConversationRegistry, RegistryStatus
from cc_coach.pipeline import Pipeline
from cc_coach.services.bigquery import BigQueryService
from cc_coach.services.gcs import GCSService, LocalDataService
from cc_coach.services.insights import InsightsService
from cc_coach.services.phrase_matcher import PhraseMatcherService, PHRASE_MATCHERS
from cc_coach.utils.logging import setup_logging

app = typer.Typer(
    name="cc-coach",
    help="Conversation Coach CLI - Pipeline orchestration for CCAI Insights",
    add_completion=False,
)

console = Console()
logger = logging.getLogger(__name__)


# Callback for global options
@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
):
    """Conversation Coach CLI."""
    level = "DEBUG" if debug else ("INFO" if verbose else "WARNING")
    setup_logging(level)


# =============================================================================
# Init Commands
# =============================================================================

@app.command()
def init():
    """Initialize BigQuery dataset and tables."""
    settings = get_settings()
    rprint(f"[bold]Initializing Conversation Coach in project:[/bold] {settings.project_id}")

    bq = BigQueryService(settings)

    with console.status("Creating BigQuery dataset and tables..."):
        tables = bq.ensure_all_tables()

    rprint("[green]Created tables:[/green]")
    for name, table in tables.items():
        rprint(f"  - {table.full_table_id}")

    rprint("\n[bold green]Initialization complete![/bold green]")


@app.command()
def status():
    """Show pipeline status and counts."""
    settings = get_settings()
    bq = BigQueryService(settings)

    rprint(f"\n[bold]Pipeline Status[/bold] - {settings.project_id}")
    rprint("-" * 50)

    try:
        counts = bq.get_status_counts()

        table = Table(title="Conversation Registry by Status")
        table.add_column("Status", style="cyan")
        table.add_column("Count", justify="right")

        total = 0
        for status_val in RegistryStatus:
            count = counts.get(status_val.value, 0)
            total += count
            table.add_row(status_val.value, str(count))

        table.add_row("─" * 15, "─" * 5)
        table.add_row("TOTAL", str(total), style="bold")

        console.print(table)
    except Exception as e:
        rprint(f"[red]Error getting status: {e}[/red]")
        rprint("Have you run 'cc-coach init' yet?")


# =============================================================================
# Ingest Commands
# =============================================================================

ingest_app = typer.Typer(help="Ingest conversations into CCAI Insights")
app.add_typer(ingest_app, name="ingest")


@ingest_app.command("local")
def ingest_local(
    data_dir: Path = typer.Argument(..., help="Local data directory"),
    date_folder: str = typer.Argument(..., help="Date folder (e.g., 2025-12-28)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't make API calls"),
    skip_analysis: bool = typer.Option(False, "--skip-analysis", help="Skip CI analysis"),
):
    """Ingest conversations from local filesystem."""
    settings = get_settings()
    local_svc = LocalDataService(data_dir)
    bq = BigQueryService(settings)
    insights_svc = InsightsService(settings)

    conversations = list(local_svc.iter_conversations(date_folder))
    rprint(f"[bold]Found {len(conversations)} conversations in {date_folder}[/bold]")

    if not conversations:
        rprint("[yellow]No conversations found[/yellow]")
        return

    with console.status("Processing conversations...") as status:
        for i, conv in enumerate(conversations, 1):
            conv_id = conv.conversation_id
            status.update(f"Processing {i}/{len(conversations)}: {conv_id[:8]}...")

            # Create registry entry
            registry = ConversationRegistry(
                conversation_id=conv_id,
                transcript_uri_raw=f"local://{data_dir}/{date_folder}/{conv_id}/transcription.json",
                metadata_uri_raw=f"local://{data_dir}/{date_folder}/{conv_id}/metadata.json",
                has_transcript=True,
                has_metadata=True,
                status=RegistryStatus.NEW,
            )

            if dry_run:
                rprint(f"  [dim]Would ingest:[/dim] {conv_id}")
                continue

            try:
                # Ingest to CCAI Insights
                result = insights_svc.ingest_conversation(
                    conv,
                    run_analysis=not skip_analysis,
                )

                # Update registry
                registry.ci_conversation_name = result["conversation_name"]
                registry.status = RegistryStatus.INGESTED
                registry.ingested_at = datetime.now(timezone.utc)

                if result.get("analysis_name"):
                    registry.ci_analysis_id = result["analysis_name"]
                    registry.status = RegistryStatus.ENRICHED
                    registry.enriched_at = datetime.now(timezone.utc)

                bq.upsert_registry(registry)
                rprint(f"  [green]Ingested:[/green] {conv_id[:8]}...")

            except Exception as e:
                logger.exception(f"Failed to ingest {conv_id}")
                registry.status = RegistryStatus.FAILED
                registry.last_error = str(e)
                registry.retry_count += 1
                bq.upsert_registry(registry)
                rprint(f"  [red]Failed:[/red] {conv_id[:8]}... - {e}")

    rprint("\n[bold green]Ingestion complete![/bold green]")


@ingest_app.command("gcs")
def ingest_gcs(
    date_folder: str = typer.Argument(..., help="Date folder (e.g., 2025-12-28)"),
    bucket: Optional[str] = typer.Option(None, "--bucket", "-b", help="GCS bucket override"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't make API calls"),
    skip_analysis: bool = typer.Option(False, "--skip-analysis", help="Skip CI analysis"),
):
    """Ingest conversations from GCS bucket."""
    settings = get_settings()
    gcs_svc = GCSService(settings)
    bq = BigQueryService(settings)
    insights_svc = InsightsService(settings)

    bucket_name = bucket or settings.gcs_bucket_dev

    with console.status(f"Loading conversations from gs://{bucket_name}/{date_folder}/..."):
        conversations = list(gcs_svc.iter_conversations(date_folder, bucket_name))

    rprint(f"[bold]Found {len(conversations)} conversations[/bold]")

    if not conversations:
        rprint("[yellow]No conversations found[/yellow]")
        return

    for i, conv in enumerate(conversations, 1):
        conv_id = conv.conversation_id
        rprint(f"[{i}/{len(conversations)}] Processing {conv_id[:8]}...")

        # Create registry entry
        registry = ConversationRegistry(
            conversation_id=conv_id,
            transcript_uri_raw=gcs_svc.get_gcs_uri(date_folder, conv_id, "transcription.json", bucket_name),
            metadata_uri_raw=gcs_svc.get_gcs_uri(date_folder, conv_id, "metadata.json", bucket_name),
            has_transcript=True,
            has_metadata=True,
            status=RegistryStatus.NEW,
        )

        if dry_run:
            rprint(f"  [dim]Would ingest:[/dim] {conv_id}")
            continue

        try:
            result = insights_svc.ingest_conversation(conv, run_analysis=not skip_analysis)

            registry.ci_conversation_name = result["conversation_name"]
            registry.status = RegistryStatus.INGESTED
            registry.ingested_at = datetime.now(timezone.utc)

            if result.get("analysis_name"):
                registry.ci_analysis_id = result["analysis_name"]
                registry.status = RegistryStatus.ENRICHED
                registry.enriched_at = datetime.now(timezone.utc)

            bq.upsert_registry(registry)
            rprint(f"  [green]Done:[/green] {result['status']}")

        except Exception as e:
            logger.exception(f"Failed to ingest {conv_id}")
            registry.status = RegistryStatus.FAILED
            registry.last_error = str(e)
            registry.retry_count += 1
            bq.upsert_registry(registry)
            rprint(f"  [red]Failed:[/red] {e}")

    rprint("\n[bold green]Ingestion complete![/bold green]")


# =============================================================================
# Registry Commands
# =============================================================================

registry_app = typer.Typer(help="Manage conversation registry")
app.add_typer(registry_app, name="registry")


@registry_app.command("list")
def registry_list(
    status_filter: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results"),
):
    """List conversations in the registry."""
    settings = get_settings()
    bq = BigQueryService(settings)

    status = RegistryStatus(status_filter) if status_filter else None

    entries = bq.list_registry(status=status, limit=limit)

    table = Table(title="Conversation Registry")
    table.add_column("ID", style="cyan", max_width=12)
    table.add_column("Status", style="bold")
    table.add_column("Has Trans", justify="center")
    table.add_column("Has Meta", justify="center")
    table.add_column("CI Name", max_width=30)
    table.add_column("Updated", style="dim")

    for entry in entries:
        table.add_row(
            entry.conversation_id[:12] + "...",
            entry.status.value,
            "Y" if entry.has_transcript else "",
            "Y" if entry.has_metadata else "",
            (entry.ci_conversation_name or "")[-30:] if entry.ci_conversation_name else "",
            entry.updated_at.strftime("%Y-%m-%d %H:%M") if entry.updated_at else "",
        )

    console.print(table)
    rprint(f"\n[dim]Showing {len(entries)} entries[/dim]")


@registry_app.command("get")
def registry_get(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
):
    """Get details for a specific conversation."""
    settings = get_settings()
    bq = BigQueryService(settings)

    entry = bq.get_registry(conversation_id)

    if not entry:
        rprint(f"[red]Conversation not found: {conversation_id}[/red]")
        raise typer.Exit(1)

    rprint(f"\n[bold]Conversation: {entry.conversation_id}[/bold]")
    rprint("-" * 50)
    rprint(f"Status: [bold]{entry.status.value}[/bold]")
    rprint(f"Has Transcript: {entry.has_transcript}")
    rprint(f"Has Metadata: {entry.has_metadata}")
    rprint(f"CI Conversation: {entry.ci_conversation_name or 'N/A'}")
    rprint(f"CI Analysis: {entry.ci_analysis_id or 'N/A'}")
    rprint(f"Created: {entry.created_at}")
    rprint(f"Updated: {entry.updated_at}")

    if entry.last_error:
        rprint(f"\n[red]Last Error:[/red] {entry.last_error}")


# =============================================================================
# Explore Commands
# =============================================================================

explore_app = typer.Typer(help="Explore pipeline data for debugging")
app.add_typer(explore_app, name="explore")


@explore_app.command("conversation")
def explore_conversation(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
):
    """Explore a conversation's data in CCAI Insights."""
    settings = get_settings()
    insights_svc = InsightsService(settings)
    bq = BigQueryService(settings)

    # Get registry entry first
    registry = bq.get_registry(conversation_id)
    if not registry or not registry.ci_conversation_name:
        rprint(f"[red]Conversation not found or not ingested: {conversation_id}[/red]")
        raise typer.Exit(1)

    # Get from CCAI Insights
    conv = insights_svc.get_conversation(registry.ci_conversation_name)
    if not conv:
        rprint(f"[red]Conversation not found in CCAI Insights[/red]")
        raise typer.Exit(1)

    rprint(f"\n[bold]CCAI Insights Conversation[/bold]")
    rprint(f"Name: {conv.name}")
    rprint(f"Language: {conv.language_code}")
    rprint(f"Medium: {conv.medium.name}")
    rprint(f"Agent ID: {conv.agent_id}")
    rprint(f"Duration: {conv.duration.seconds}s")

    rprint(f"\n[bold]Labels:[/bold]")
    for key, value in conv.labels.items():
        rprint(f"  {key}: {value}")

    rprint(f"\n[bold]Transcript ({len(conv.transcript.transcript_entries)} turns):[/bold]")
    for entry in conv.transcript.transcript_entries[:5]:
        role = entry.role.name
        rprint(f"  [{role}] {entry.text[:80]}...")

    if len(conv.transcript.transcript_entries) > 5:
        rprint(f"  ... and {len(conv.transcript.transcript_entries) - 5} more turns")


@explore_app.command("insights-list")
def explore_insights_list(
    filter_str: Optional[str] = typer.Option(None, "--filter", "-f", help="Filter expression"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results"),
):
    """List conversations in CCAI Insights."""
    settings = get_settings()
    insights_svc = InsightsService(settings)

    conversations = insights_svc.list_conversations(filter_str=filter_str, page_size=limit)

    table = Table(title="CCAI Insights Conversations")
    table.add_column("Name", style="cyan", max_width=50)
    table.add_column("Agent", max_width=10)
    table.add_column("Duration", justify="right")
    table.add_column("Turns", justify="right")

    for conv in conversations[:limit]:
        table.add_row(
            conv.name.split("/")[-1],
            conv.agent_id,
            f"{conv.duration.seconds}s",
            str(len(conv.transcript.transcript_entries)),
        )

    console.print(table)
    rprint(f"\n[dim]Showing {min(len(conversations), limit)} conversations[/dim]")


@explore_app.command("ci-raw")
def explore_ci_raw(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
    show_input: bool = typer.Option(False, "--show-input", "-i", help="Also show what was sent TO CI"),
):
    """
    Show raw CCAI Insights output for a conversation.

    This shows exactly what CI returns after analysis - useful for understanding
    the data flow and debugging.
    """
    from google.protobuf.json_format import MessageToDict

    settings = get_settings()
    insights_svc = InsightsService(settings)
    bq = BigQueryService(settings)

    # Get registry entry first
    registry = bq.get_registry(conversation_id)
    if not registry:
        rprint(f"[red]Conversation not found in registry: {conversation_id}[/red]")
        raise typer.Exit(1)

    if not registry.ci_conversation_name:
        rprint(f"[red]Conversation not yet ingested to CI. Run 'cc-coach pipeline ingest-ci {conversation_id}' first.[/red]")
        raise typer.Exit(1)

    # Show what was sent TO CI (the input)
    if show_input:
        rprint("\n[bold cyan]═══ WHAT WAS SENT TO CI (INPUT) ═══[/bold cyan]")
        conv = insights_svc.get_conversation(registry.ci_conversation_name)
        if conv:
            conv_dict = MessageToDict(conv._pb)
            # Show key fields sent
            rprint(f"\n[bold]Conversation Resource:[/bold]")
            rprint(f"  Name: {conv_dict.get('name')}")
            rprint(f"  Medium: {conv_dict.get('medium')}")
            rprint(f"  Language: {conv_dict.get('languageCode')}")
            rprint(f"  Agent ID: {conv_dict.get('agentId')}")
            rprint(f"  Start Time: {conv_dict.get('startTime')}")
            rprint(f"  Duration: {conv_dict.get('duration')}")

            rprint(f"\n[bold]Labels (from metadata):[/bold]")
            for key, val in conv_dict.get('labels', {}).items():
                rprint(f"  {key}: {val}")

            rprint(f"\n[bold]Data Source:[/bold]")
            rprint(f"  GCS URI: {conv_dict.get('dataSource', {}).get('gcsSource', {}).get('transcriptUri')}")

            rprint(f"\n[bold]Transcript Sample (first 3 turns):[/bold]")
            entries = conv_dict.get('transcript', {}).get('transcriptEntries', [])
            for entry in entries[:3]:
                rprint(f"  [{entry.get('role')}] {entry.get('text', '')[:60]}...")
            if len(entries) > 3:
                rprint(f"  ... and {len(entries) - 3} more turns")

    # Get analysis results (the output)
    if not registry.ci_analysis_id:
        rprint(f"\n[yellow]No analysis yet. Run 'cc-coach pipeline analyze-ci {conversation_id}' to analyze.[/yellow]")
        raise typer.Exit(0)

    rprint("\n[bold green]═══ RAW CI ANALYSIS OUTPUT ═══[/bold green]")

    # Use the Insights client directly to get raw analysis
    from google.cloud import contact_center_insights_v1 as insights
    client = insights.ContactCenterInsightsClient()
    analysis = client.get_analysis(name=registry.ci_analysis_id)

    if not analysis:
        rprint(f"[red]Analysis not found: {registry.ci_analysis_id}[/red]")
        raise typer.Exit(1)

    # Convert to dict for display
    analysis_dict = MessageToDict(analysis._pb)

    rprint(f"\n[bold]Analysis Metadata:[/bold]")
    rprint(f"  Name: {analysis_dict.get('name')}")
    rprint(f"  Request Time: {analysis_dict.get('requestTime')}")
    rprint(f"  Create Time: {analysis_dict.get('createTime')}")

    # Extract call analysis metadata
    call_meta = analysis_dict.get('analysisResult', {}).get('callAnalysisMetadata', {})

    rprint(f"\n[bold]Sentiments (overall per channel):[/bold]")
    for sent in call_meta.get('sentiments', []):
        channel = sent.get('channelTag')
        channel_name = "CUSTOMER" if channel == 1 else "AGENT" if channel == 2 else f"CHANNEL_{channel}"
        score = sent.get('sentimentData', {}).get('score', 'N/A')
        magnitude = sent.get('sentimentData', {}).get('magnitude', 'N/A')
        rprint(f"  {channel_name}: score={score}, magnitude={magnitude}")

    rprint(f"\n[bold]Entities:[/bold]")
    entities = call_meta.get('entities', {})
    if entities:
        for entity_id, entity in entities.items():
            etype = entity.get('type', 'UNKNOWN')
            name = entity.get('displayName')
            salience = entity.get('salience', 0)
            rprint(f"  [{etype}] {name} (salience={salience:.3f})")
    else:
        rprint("  (none detected)")

    rprint(f"\n[bold]Intents/Topics:[/bold]")
    intents = call_meta.get('intents', {})
    if intents:
        for intent_id, intent in intents.items():
            rprint(f"  • {intent.get('displayName')}")
    else:
        rprint("  (none detected)")

    rprint(f"\n[bold]Per-Turn Annotations (sample):[/bold]")
    annotations = call_meta.get('annotations', [])
    sentiment_annotations = [a for a in annotations if 'sentimentData' in a and a['sentimentData']]
    for ann in sentiment_annotations[:5]:
        channel = ann.get('channelTag')
        channel_name = "CUSTOMER" if channel == 1 else "AGENT"
        turn_idx = ann.get('annotationStartBoundary', {}).get('transcriptIndex', '?')
        score = ann.get('sentimentData', {}).get('score', 'N/A')
        rprint(f"  Turn {turn_idx} [{channel_name}]: score={score}")
    if len(sentiment_annotations) > 5:
        rprint(f"  ... and {len(sentiment_annotations) - 5} more sentiment annotations")

    # Option to dump full JSON
    rprint(f"\n[dim]For full JSON output, use: --format json[/dim]")

    # Ask if they want full JSON
    rprint(f"\n[bold]Full Raw JSON:[/bold]")
    rprint(json.dumps(analysis_dict, indent=2))


@explore_app.command("query")
def explore_query(
    sql: str = typer.Argument(..., help="SQL query to execute"),
    output_format: str = typer.Option("table", "--format", "-f", help="Output format: table, json"),
):
    """Execute a BigQuery SQL query."""
    settings = get_settings()
    bq = BigQueryService(settings)

    try:
        results = bq.query(sql)

        if output_format == "json":
            rprint(json.dumps(results, indent=2, default=str))
        else:
            if not results:
                rprint("[yellow]No results[/yellow]")
                return

            table = Table()
            for col in results[0].keys():
                table.add_column(col)

            for row in results:
                table.add_row(*[str(v) for v in row.values()])

            console.print(table)

    except Exception as e:
        rprint(f"[red]Query failed: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Phrase Matcher Commands
# =============================================================================

pm_app = typer.Typer(help="Manage CI phrase matchers")
app.add_typer(pm_app, name="phrase-matcher")


@pm_app.command("list")
def pm_list():
    """List all phrase matchers in CI."""
    settings = get_settings()
    pm_svc = PhraseMatcherService(settings)

    matchers = pm_svc.list_phrase_matchers()

    table = Table(title="CI Phrase Matchers")
    table.add_column("Name", style="cyan", max_width=50)
    table.add_column("Display Name", style="bold")
    table.add_column("Active")
    table.add_column("Rules", justify="right")

    for m in matchers:
        rule_count = len(m.phrase_match_rule_groups) if m.phrase_match_rule_groups else 0
        table.add_row(
            m.name.split("/")[-1],
            m.display_name,
            "Y" if m.active else "N",
            str(rule_count),
        )

    console.print(table)
    rprint(f"\n[dim]Total: {len(matchers)} matchers[/dim]")


@pm_app.command("show-config")
def pm_show_config():
    """Show configured phrase matchers (from code)."""
    table = Table(title="Configured Phrase Matchers")
    table.add_column("Matcher ID", style="cyan")
    table.add_column("Display Name", style="bold")
    table.add_column("Phrases", justify="right")

    for matcher_id, config in PHRASE_MATCHERS.items():
        table.add_row(
            matcher_id,
            config["display_name"],
            str(len(config["phrases"])),
        )

    console.print(table)

    rprint("\n[bold]Phrase Details:[/bold]")
    for matcher_id, config in PHRASE_MATCHERS.items():
        rprint(f"\n[cyan]{config['display_name']}[/cyan]:")
        for phrase in config["phrases"]:
            rprint(f"  • {phrase}")


@pm_app.command("ensure")
def pm_ensure():
    """Create all configured phrase matchers in CI (idempotent)."""
    settings = get_settings()
    pm_svc = PhraseMatcherService(settings)

    rprint("[bold]Ensuring all phrase matchers exist...[/bold]")

    with console.status("Creating phrase matchers..."):
        results = pm_svc.ensure_all_matchers()

    rprint(f"\n[green]Phrase matchers ready: {len(results)}[/green]")
    for matcher_id, matcher in results.items():
        rprint(f"  • {matcher_id}: {matcher.name}")


@pm_app.command("delete-all")
def pm_delete_all(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete ALL phrase matchers from CI (use with caution)."""
    if not confirm:
        rprint("[yellow]This will delete ALL phrase matchers. Use --yes to confirm.[/yellow]")
        raise typer.Exit(1)

    settings = get_settings()
    pm_svc = PhraseMatcherService(settings)

    with console.status("Deleting all phrase matchers..."):
        deleted = pm_svc.delete_all_matchers()

    rprint(f"[red]Deleted {deleted} phrase matchers[/red]")


# =============================================================================
# Config Commands
# =============================================================================

@app.command()
def config():
    """Show current configuration."""
    settings = get_settings()

    rprint("\n[bold]Current Configuration[/bold]")
    rprint("-" * 50)
    rprint(f"Project ID: {settings.project_id}")
    rprint(f"Region: {settings.region}")
    rprint(f"GCS Bucket (dev): {settings.gcs_bucket_dev}")
    rprint(f"BigQuery Dataset: {settings.bq_dataset}")
    rprint(f"BigQuery Location: {settings.bq_location}")
    rprint(f"Insights Location: {settings.insights_location}")
    rprint(f"Insights Parent: {settings.insights_parent}")


# =============================================================================
# Pipeline Commands - Discrete steps for workflow automation
# =============================================================================
pipeline_app = typer.Typer(help="Pipeline commands - discrete steps for processing")
app.add_typer(pipeline_app, name="pipeline")


@pipeline_app.command("register")
def pipeline_register(
    bucket: str = typer.Argument(..., help="GCS bucket name"),
    prefix: str = typer.Argument(..., help="Path prefix (e.g., 2025-12-28/uuid)"),
):
    """
    Step 1: Register conversation files in BigQuery registry.

    Scans the given GCS prefix and registers transcription/metadata files.
    """
    pipeline = Pipeline()

    with console.status(f"Registering files from gs://{bucket}/{prefix}..."):
        result = pipeline.register_conversation_folder(bucket, prefix)

    rprint(f"\n[bold]Registration Result[/bold]")
    rprint("-" * 50)
    rprint(f"Conversation ID: {result['conversation_id']}")
    rprint(f"Files found: {', '.join(result['files_found']) or 'none'}")
    rprint(f"Ready for CI: {'✓' if result['ready_for_ci'] else '✗'}")
    rprint(f"Status: {result['status']}")


@pipeline_app.command("register-all")
def pipeline_register_all(
    bucket: str = typer.Option(None, "--bucket", "-b", help="GCS bucket override"),
    date_folder: str = typer.Argument(..., help="Date folder (e.g., 2025-12-28)"),
):
    """
    Step 1: Register ALL conversations for a date folder.

    Scans GCS bucket for all conversation folders and registers them.
    """
    settings = get_settings()
    bucket = bucket or settings.gcs_bucket_dev
    pipeline = Pipeline()

    from google.cloud import storage
    client = storage.Client(project=settings.project_id)
    bucket_obj = client.bucket(bucket)

    # List all conversation folders
    blobs = bucket_obj.list_blobs(prefix=f"{date_folder}/")
    folders = set()
    for blob in blobs:
        parts = blob.name.split("/")
        if len(parts) >= 2:
            folders.add(f"{parts[0]}/{parts[1]}")

    rprint(f"\n[bold]Registering {len(folders)} conversations[/bold]")
    rprint("-" * 50)

    results = []
    for folder in sorted(folders):
        with console.status(f"Registering {folder}..."):
            result = pipeline.register_conversation_folder(bucket, folder)
            results.append(result)

        status = "✓ ready" if result['ready_for_ci'] else "○ incomplete"
        rprint(f"  {result['conversation_id'][:8]}... {status}")

    ready_count = sum(1 for r in results if r['ready_for_ci'])
    rprint(f"\nTotal: {len(results)} | Ready for CI: {ready_count}")


@pipeline_app.command("ingest-ci")
def pipeline_ingest_ci(
    conversation_id: str = typer.Argument(..., help="Conversation UUID"),
):
    """
    Step 2: Ingest a conversation to CCAI Insights.

    Prerequisites: Conversation must be registered with both files present.
    """
    pipeline = Pipeline()

    rprint(f"\n[bold]Ingesting to CCAI Insights[/bold]")
    rprint("-" * 50)

    try:
        with console.status(f"Ingesting {conversation_id}..."):
            result = pipeline.ingest_to_ci(conversation_id)

        rprint(f"Conversation ID: {result['conversation_id']}")
        rprint(f"CI Name: {result['ci_conversation_name']}")
        rprint(f"Status: {result['status']}")
        if result.get('skipped'):
            rprint("[yellow]Skipped - already exists in CI[/yellow]")

    except Exception as e:
        rprint(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@pipeline_app.command("analyze-ci")
def pipeline_analyze_ci(
    conversation_id: str = typer.Argument(..., help="Conversation UUID"),
):
    """
    Step 3: Run CCAI Insights analysis on a conversation.

    Prerequisites: Conversation must be ingested to CI.
    """
    pipeline = Pipeline()

    rprint(f"\n[bold]Running CI Analysis[/bold]")
    rprint("-" * 50)

    try:
        with console.status(f"Analyzing {conversation_id}... (this may take a minute)"):
            result = pipeline.run_ci_analysis(conversation_id)

        rprint(f"Conversation ID: {result['conversation_id']}")
        rprint(f"Analysis Name: {result['analysis_name']}")
        rprint(f"Status: {result['status']}")
        if result.get('skipped'):
            rprint("[yellow]Skipped - already analyzed[/yellow]")

    except Exception as e:
        rprint(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@pipeline_app.command("export-bq")
def pipeline_export_bq(
    conversation_id: str = typer.Argument(..., help="Conversation UUID"),
):
    """
    Step 4: Export CI analysis results to BigQuery.

    Prerequisites: CI analysis must be complete.
    """
    pipeline = Pipeline()

    rprint(f"\n[bold]Exporting to BigQuery[/bold]")
    rprint("-" * 50)

    try:
        with console.status(f"Exporting {conversation_id}..."):
            result = pipeline.export_ci_to_bq(conversation_id)

        rprint(f"Conversation ID: {result['conversation_id']}")
        rprint(f"Enrichment fields: {', '.join(result['enrichment_fields'])}")
        rprint(f"Status: {result['status']}")

    except Exception as e:
        rprint(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@pipeline_app.command("process")
def pipeline_process(
    conversation_id: str = typer.Argument(..., help="Conversation UUID"),
    skip_analysis: bool = typer.Option(False, "--skip-analysis", help="Skip CI analysis"),
):
    """
    Run full pipeline for a single conversation (Steps 2-4).

    Combines ingest, analyze, and export steps.
    """
    pipeline = Pipeline()

    rprint(f"\n[bold]Processing Conversation[/bold]")
    rprint("-" * 50)

    try:
        with console.status(f"Processing {conversation_id}..."):
            result = pipeline.process_conversation(
                conversation_id,
                run_analysis=not skip_analysis,
            )

        rprint(f"Conversation ID: {result['conversation_id']}")
        rprint(f"Status: {result['status']}")

        if result.get('steps'):
            rprint("\n[bold]Steps executed:[/bold]")
            for step_name, step_result in result['steps'].items():
                status = step_result.get('status', 'unknown')
                rprint(f"  • {step_name}: {status}")

        if result.get('error'):
            rprint(f"[red]Error: {result['error']}[/red]")

    except Exception as e:
        rprint(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@pipeline_app.command("process-all")
def pipeline_process_all(
    status_filter: str = typer.Option("NEW", "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max conversations to process"),
    skip_analysis: bool = typer.Option(False, "--skip-analysis", help="Skip CI analysis"),
):
    """
    Process all pending conversations (Steps 2-4 for batch).
    """
    pipeline = Pipeline()
    bq = BigQueryService()

    # Get pending conversations
    status_enum = RegistryStatus(status_filter) if status_filter else None
    pending = bq.list_registry(status=status_enum, limit=limit)

    # Filter to only those ready for CI
    ready = [r for r in pending if r.has_transcript and r.has_metadata]

    rprint(f"\n[bold]Processing {len(ready)} conversations[/bold]")
    rprint("-" * 50)

    success_count = 0
    fail_count = 0

    for registry in ready:
        with console.status(f"Processing {registry.conversation_id[:8]}..."):
            result = pipeline.process_conversation(
                registry.conversation_id,
                run_analysis=not skip_analysis,
            )

        if result['status'] == 'success':
            success_count += 1
            rprint(f"  ✓ {registry.conversation_id[:8]}... [green]success[/green]")
        else:
            fail_count += 1
            rprint(f"  ✗ {registry.conversation_id[:8]}... [red]failed: {result.get('error', 'unknown')}[/red]")

    rprint(f"\nTotal: {len(ready)} | Success: {success_count} | Failed: {fail_count}")


@pipeline_app.command("reanalyze-all")
def pipeline_reanalyze_all(
    status_filter: str = typer.Option("INGESTED,ENRICHED", "--status", "-s", help="Filter by status (comma-separated)"),
    limit: int = typer.Option(100, "--limit", "-n", help="Max conversations to process"),
):
    """
    Re-analyze and re-export all conversations with new CI config.

    Use this after updating phrase matchers or analysis settings.
    """
    pipeline = Pipeline()
    bq = BigQueryService()
    pm_svc = PhraseMatcherService()

    # Ensure phrase matchers exist first
    rprint("[bold]Step 1: Ensuring phrase matchers exist...[/bold]")
    with console.status("Creating phrase matchers..."):
        pm_results = pm_svc.ensure_all_matchers()
    rprint(f"  Phrase matchers ready: {len(pm_results)}")

    # Get conversations to re-analyze
    statuses = [s.strip() for s in status_filter.split(",")]
    all_convos = []

    for status_str in statuses:
        try:
            status_enum = RegistryStatus(status_str)
            convos = bq.list_registry(status=status_enum, limit=limit)
            all_convos.extend([c for c in convos if c.ci_conversation_name])
        except ValueError:
            rprint(f"[yellow]Unknown status: {status_str}[/yellow]")

    rprint(f"\n[bold]Step 2: Re-analyzing {len(all_convos)} conversations[/bold]")
    rprint("-" * 50)

    success_count = 0
    fail_count = 0

    for registry in all_convos:
        conv_id = registry.conversation_id
        rprint(f"  Processing {conv_id[:8]}...")

        try:
            # Force re-analysis by skipping the "already analyzed" check
            with console.status(f"  Analyzing {conv_id[:8]}..."):
                analysis_result = pipeline.run_ci_analysis(
                    conv_id,
                    skip_if_analyzed=False,  # Force re-analyze
                    use_phrase_matchers=True,
                )

            # Re-export to BQ
            with console.status(f"  Exporting {conv_id[:8]}..."):
                export_result = pipeline.export_ci_to_bq(conv_id)

            success_count += 1
            phrase_count = export_result.get("phrase_match_count", 0)
            flag_count = export_result.get("ci_flag_count", 0)
            rprint(f"    [green]✓[/green] phrases: {phrase_count}, flags: {flag_count}")

        except Exception as e:
            fail_count += 1
            logger.exception(f"Failed to re-analyze {conv_id}")
            rprint(f"    [red]✗ {e}[/red]")

    rprint(f"\n[bold]Complete![/bold] Success: {success_count} | Failed: {fail_count}")


# =============================================================================
# Coach Commands - ADK-based coaching
# =============================================================================

coach_app = typer.Typer(help="Generate coaching feedback using ADK/Gemini")
app.add_typer(coach_app, name="coach")


@coach_app.command("generate")
def coach_generate(
    conversation_id: str = typer.Argument(..., help="Conversation ID to coach"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override (e.g., gemini-2.5-pro)"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    fallback: bool = typer.Option(False, "--fallback", help="Use embedded policy if RAG unavailable"),
):
    """Generate coaching for a single conversation."""
    from cc_coach.services.coaching import CoachingOrchestrator

    rprint(f"[bold blue]Generating coaching for {conversation_id}...[/bold blue]")

    try:
        orchestrator = CoachingOrchestrator(model=model, allow_fallback=fallback)
        result = orchestrator.generate_coaching(conversation_id)

        if output_json:
            rprint(result.model_dump_json(indent=2))
        else:
            _display_coaching_result(result)

        rprint(f"\n[bold green]Coaching saved to BigQuery[/bold green]")

    except Exception as e:
        logger.exception(f"Failed to generate coaching for {conversation_id}")
        rprint(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)
    finally:
        # Ensure traces are flushed
        from cc_coach.monitoring.tracing import shutdown_tracing
        shutdown_tracing()


@coach_app.command("generate-pending")
def coach_generate_pending(
    limit: int = typer.Option(10, "--limit", "-l", help="Max conversations to process"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be processed"),
    fallback: bool = typer.Option(False, "--fallback", help="Use embedded policy if RAG unavailable"),
):
    """Generate coaching for all pending (ENRICHED) conversations."""
    from cc_coach.services.coaching import CoachingOrchestrator

    orchestrator = CoachingOrchestrator(model=model, allow_fallback=fallback)

    # Get pending conversations
    pending = orchestrator.get_pending_conversations(limit=limit)

    if not pending:
        rprint("[yellow]No pending conversations found[/yellow]")
        return

    rprint(f"[bold]Found {len(pending)} pending conversations[/bold]")

    if dry_run:
        for conv_id in pending:
            rprint(f"  Would process: {conv_id}")
        return

    # Process each
    success = 0
    failed = 0

    try:
        for conv_id in pending:
            try:
                rprint(f"Processing {conv_id[:12]}...", end=" ")
                orchestrator.generate_coaching(conv_id)
                rprint("[green]OK[/green]")
                success += 1
            except Exception as e:
                rprint(f"[red]FAILED: {e}[/red]")
                failed += 1

        rprint(f"\n[bold]Complete: {success} success, {failed} failed[/bold]")
    finally:
        # Ensure traces are flushed
        from cc_coach.monitoring.tracing import shutdown_tracing
        shutdown_tracing()


@coach_app.command("get")
def coach_get(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get existing coaching for a conversation."""
    from cc_coach.services.coaching import CoachingOrchestrator

    orchestrator = CoachingOrchestrator()
    result = orchestrator.get_coaching_result(conversation_id)

    if not result:
        rprint(f"[yellow]No coaching found for {conversation_id}[/yellow]")
        raise typer.Exit(1)

    if output_json:
        rprint(json.dumps(result, default=str, indent=2))
    else:
        _display_coaching_from_bq(result)


@coach_app.command("preview")
def coach_preview(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
):
    """Preview what would be sent to the coach (dry run)."""
    from cc_coach.services.coaching import CoachingOrchestrator

    orchestrator = CoachingOrchestrator()

    # Fetch data
    ci_data = orchestrator._fetch_ci_enrichment(conversation_id)
    registry_data = orchestrator._fetch_registry(conversation_id)

    if not ci_data:
        rprint(f"[red]No CI enrichment found for {conversation_id}[/red]")
        raise typer.Exit(1)

    # Build input
    input_data = orchestrator._build_coaching_input(conversation_id, ci_data, registry_data)

    rprint(f"\n[bold]Coaching Input Preview[/bold]")
    rprint("-" * 60)
    rprint(input_data.to_prompt_text())


@coach_app.command("raw")
def coach_raw(
    conversation_id: str = typer.Argument(..., help="Conversation ID"),
    format: str = typer.Option("expanded", "--format", "-f", help="Output format: expanded (psql \\x), json, or table"),
):
    """
    Show raw BQ data for a coaching result.

    Like psql's \\x expanded display - shows each field on its own line.
    Useful for inspecting the full data stored in BigQuery.
    """
    from cc_coach.services.coaching import CoachingOrchestrator

    orchestrator = CoachingOrchestrator()
    result = orchestrator.get_coaching_result(conversation_id)

    if not result:
        rprint(f"[yellow]No coaching found for {conversation_id}[/yellow]")
        raise typer.Exit(1)

    if format == "json":
        rprint(json.dumps(result, default=str, indent=2))
    elif format == "table":
        # Simple key-value table for scalar fields
        table = Table(title=f"coach_analysis: {conversation_id[:20]}...")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        for key, value in result.items():
            if isinstance(value, (list, dict)):
                table.add_row(key, f"[dim]<{type(value).__name__} len={len(value) if isinstance(value, list) else 'obj'}>[/dim]")
            else:
                table.add_row(key, str(value)[:80])
        console.print(table)
    else:  # expanded (default) - psql \x style
        _display_expanded(result, conversation_id)


def _display_expanded(result: dict, conversation_id: str):
    """Display BQ row in psql \\x expanded format."""
    rprint(f"[bold cyan]-[ RECORD: coach_analysis ]-[/bold cyan]")
    rprint(f"[bold cyan]conversation_id:[/bold cyan] {conversation_id}")
    rprint("-" * 80)

    # Group fields by category for readability
    scalar_fields = []
    array_fields = []
    nested_fields = []

    for key, value in result.items():
        if key == "conversation_id":
            continue
        if isinstance(value, dict):
            nested_fields.append((key, value))
        elif isinstance(value, list):
            array_fields.append((key, value))
        else:
            scalar_fields.append((key, value))

    # Scalar fields first
    for key, value in scalar_fields:
        display_val = str(value) if value is not None else "[dim]NULL[/dim]"
        rprint(f"[cyan]{key:30}[/cyan] | {display_val}")

    # Array fields
    if array_fields:
        rprint(f"\n[bold yellow]-[ ARRAY FIELDS ]-[/bold yellow]")
        for key, value in array_fields:
            rprint(f"\n[cyan]{key}[/cyan] ({len(value)} items):")
            if not value:
                rprint("  [dim](empty)[/dim]")
            elif isinstance(value[0], dict):
                # Array of records
                for i, item in enumerate(value):
                    rprint(f"  [dim]─[{i}]─[/dim]")
                    for k, v in item.items():
                        if isinstance(v, list):
                            rprint(f"    {k}: {json.dumps(v, default=str)[:100]}...")
                        else:
                            v_str = str(v)[:100] if v else "[dim]NULL[/dim]"
                            rprint(f"    {k}: {v_str}")
            else:
                # Array of scalars
                for i, item in enumerate(value):
                    rprint(f"  [{i}] {item}")

    # Nested record fields
    if nested_fields:
        rprint(f"\n[bold yellow]-[ NESTED RECORDS ]-[/bold yellow]")
        for key, value in nested_fields:
            rprint(f"\n[cyan]{key}[/cyan]:")
            if value:
                for k, v in value.items():
                    v_str = str(v)[:100] if v else "[dim]NULL[/dim]"
                    rprint(f"  {k}: {v_str}")


def _display_coaching_result(result):
    """Display coaching result in rich format."""
    # Scores table
    scores_table = Table(title="Scores")
    scores_table.add_column("Dimension")
    scores_table.add_column("Score", justify="right")

    # Color code scores
    def score_style(score: int) -> str:
        if score >= 8:
            return "green"
        elif score >= 6:
            return "yellow"
        else:
            return "red"

    scores_table.add_row("Empathy", f"[{score_style(result.empathy_score)}]{result.empathy_score}/10[/]")
    scores_table.add_row("Compliance", f"[{score_style(result.compliance_score)}]{result.compliance_score}/10[/]")
    scores_table.add_row("Resolution", f"[{score_style(result.resolution_score)}]{result.resolution_score}/10[/]")
    scores_table.add_row("Professionalism", f"[{score_style(result.professionalism_score)}]{result.professionalism_score}/10[/]")
    scores_table.add_row("De-escalation", f"[{score_style(result.de_escalation_score)}]{result.de_escalation_score}/10[/]")
    scores_table.add_row("Efficiency", f"[{score_style(result.efficiency_score)}]{result.efficiency_score}/10[/]")
    scores_table.add_row("[bold]Overall[/bold]", f"[bold]{result.overall_score:.1f}/10[/bold]")

    console.print(scores_table)

    # Summary
    rprint(f"\n[bold]Call Type:[/bold] {result.call_type}")
    rprint(f"[bold]Situation:[/bold] {result.situation_summary}")
    rprint(f"[bold]Summary:[/bold] {result.coaching_summary}")

    # Key Moment
    rprint(f"\n[bold]Key Moment[/bold] (Turn {result.key_moment.turn_index}):")
    emoji = "[green]" if result.key_moment.is_positive else "[red]"
    rprint(f"  {emoji}\"{result.key_moment.quote}\"[/]")
    rprint(f"  [dim]{result.key_moment.why_notable}[/dim]")

    # Critical Issues
    if result.critical_issues:
        rprint(f"\n[bold red]Critical Issues:[/bold red]")
        for issue in result.critical_issues:
            rprint(f"  [red]- {issue}[/red]")

    # Coaching points
    rprint(f"\n[bold]Coaching Points:[/bold]")
    for cp in result.coaching_points:
        rprint(f"  {cp.priority}. [bold]{cp.title}[/bold]")
        rprint(f"     {cp.description}")
        if cp.suggested_alternative:
            rprint(f"     [green]Try: {cp.suggested_alternative}[/green]")

    # Strengths
    rprint(f"\n[bold green]Strengths:[/bold green]")
    for s in result.strengths:
        rprint(f"  + {s}")


def _display_coaching_from_bq(result: dict):
    """Display coaching result from BQ row."""
    # Scores table
    scores_table = Table(title="Scores")
    scores_table.add_column("Dimension")
    scores_table.add_column("Score", justify="right")

    def score_style(score) -> str:
        if score is None:
            return "dim"
        if score >= 8:
            return "green"
        elif score >= 6:
            return "yellow"
        else:
            return "red"

    for dim in ["empathy", "compliance", "resolution", "professionalism", "de_escalation", "efficiency"]:
        score = result.get(f"{dim}_score")
        if score is not None:
            scores_table.add_row(dim.replace("_", " ").title(), f"[{score_style(score)}]{score}/10[/]")

    overall = result.get("overall_score")
    if overall:
        scores_table.add_row("[bold]Overall[/bold]", f"[bold]{overall:.1f}/10[/bold]")

    console.print(scores_table)

    # Summary
    rprint(f"\n[bold]Call Type:[/bold] {result.get('call_type', 'N/A')}")
    rprint(f"[bold]Situation:[/bold] {result.get('situation_summary', 'N/A')}")
    rprint(f"[bold]Summary:[/bold] {result.get('coaching_summary', 'N/A')}")

    # Key Moment
    key_moment = result.get("key_moment", {})
    if key_moment:
        rprint(f"\n[bold]Key Moment[/bold] (Turn {key_moment.get('turn_index', '?')}):")
        rprint(f"  \"{key_moment.get('quote', '')}\"")
        rprint(f"  [dim]{key_moment.get('why_notable', '')}[/dim]")

    # Critical Issues
    critical = result.get("critical_issues", [])
    if critical:
        rprint(f"\n[bold red]Critical Issues:[/bold red]")
        for issue in critical:
            rprint(f"  [red]- {issue}[/red]")

    # Coaching points
    points = result.get("coaching_points", [])
    if points:
        rprint(f"\n[bold]Coaching Points:[/bold]")
        for cp in points:
            if isinstance(cp, dict):
                rprint(f"  {cp.get('priority', '?')}. [bold]{cp.get('title', '')}[/bold]")
                rprint(f"     {cp.get('description', '')}")
                if cp.get("suggested_alternative"):
                    rprint(f"     [green]Try: {cp.get('suggested_alternative')}[/green]")

    # Strengths
    strengths = result.get("strengths", [])
    if strengths:
        rprint(f"\n[bold green]Strengths:[/bold green]")
        for s in strengths:
            rprint(f"  + {s}")

    # Metadata
    rprint(f"\n[dim]Model: {result.get('model_version')} | Prompt: {result.get('prompt_version')} | Analyzed: {result.get('analyzed_at')}[/dim]")


# =============================================================================
# RAG Commands - Knowledge Base management
# =============================================================================

rag_app = typer.Typer(help="RAG knowledge base management")
app.add_typer(rag_app, name="rag")


@rag_app.command("ingest")
def rag_ingest(
    documents_path: Optional[Path] = typer.Option(None, "--path", "-p", help="Documents directory path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate only, don't make changes"),
    full_refresh: bool = typer.Option(False, "--full-refresh", help="Re-upload all documents"),
    skip_gcs: bool = typer.Option(False, "--skip-gcs", help="Skip GCS sync (BQ only)"),
):
    """
    Ingest documents from local files to BQ + GCS.

    Scans markdown files in the documents directory, validates YAML frontmatter,
    syncs metadata to BigQuery, and uploads active documents to GCS for Vertex AI
    Search indexing.
    """
    from cc_coach.rag import RAGConfig, DocumentIngester

    config = RAGConfig.from_env()

    # Validate config (GCS/DataStore only required if not skipping GCS)
    errors = config.validate()
    required_errors = [e for e in errors if "GCP_PROJECT_ID" in e]
    gcs_errors = [e for e in errors if "GCS" in e or "DATA_STORE" in e]

    if required_errors:
        for err in required_errors:
            rprint(f"[red]Config error: {err}[/red]")
        raise typer.Exit(1)

    if gcs_errors and not skip_gcs:
        for err in gcs_errors:
            rprint(f"[yellow]Warning: {err}[/yellow]")
        rprint("[yellow]Use --skip-gcs to skip GCS sync and proceed with BQ-only ingestion[/yellow]")
        raise typer.Exit(1)

    if documents_path:
        config.documents_path = documents_path

    ingester = DocumentIngester(config)

    result = ingester.ingest_documents(
        dry_run=dry_run,
        full_refresh=full_refresh,
        skip_gcs=skip_gcs,
    )

    # Only exit with error if there are non-GCS errors
    non_gcs_errors = [e for e in result.errors if e[0] != "gcs_sync"]
    if non_gcs_errors:
        raise typer.Exit(1)


@rag_app.command("ingest-file")
def rag_ingest_file(
    file_path: Path = typer.Argument(..., help="Path to markdown file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate only"),
):
    """Ingest a single document file."""
    from cc_coach.rag import RAGConfig, DocumentIngester

    config = RAGConfig.from_env()
    errors = config.validate()
    if errors:
        for err in errors:
            rprint(f"[red]Config error: {err}[/red]")
        raise typer.Exit(1)

    ingester = DocumentIngester(config)
    success = ingester.ingest_single(file_path, dry_run=dry_run)

    if not success:
        raise typer.Exit(1)


@rag_app.command("search")
def rag_search(
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Search the knowledge base.

    Queries Vertex AI Search and enriches results with BQ metadata.
    Useful for testing retrieval before using in coaching.
    """
    from cc_coach.rag import RAGConfig, RAGRetriever

    config = RAGConfig.from_env()
    errors = config.validate()
    if errors:
        for err in errors:
            rprint(f"[red]Config error: {err}[/red]")
        raise typer.Exit(1)

    retriever = RAGRetriever(config)

    rprint(f"[blue]Searching for:[/blue] {query}")

    result = retriever.search(query, top_k=top_k)

    if not result.documents:
        rprint("[yellow]No results found[/yellow]")
        return

    if output_json:
        docs_json = [d.to_dict() for d in result.documents]
        rprint(json.dumps(docs_json, indent=2))
    else:
        rprint(f"\n[bold]Found {len(result.documents)} results:[/bold]\n")

        for i, doc in enumerate(result.documents, 1):
            # Header with citation
            citation = doc.to_citation()
            score = f"{doc.relevance_score:.2f}" if doc.relevance_score else "N/A"
            rprint(f"[bold cyan]{i}. {citation}[/bold cyan] [dim](score: {score})[/dim]")

            # Snippet
            snippet = doc.snippet[:300] + "..." if len(doc.snippet) > 300 else doc.snippet
            rprint(f"   {snippet}")
            rprint()


@rag_app.command("status")
def rag_status():
    """Show knowledge base status and statistics."""
    from cc_coach.rag import RAGConfig, MetadataStore

    config = RAGConfig.from_env()
    errors = config.validate()
    if errors:
        for err in errors:
            rprint(f"[red]Config error: {err}[/red]")
        raise typer.Exit(1)

    store = MetadataStore(config)

    rprint(f"\n[bold]RAG Knowledge Base Status[/bold]")
    rprint("-" * 50)
    rprint(f"Project: {config.project_id}")
    rprint(f"GCS Bucket: {config.gcs_bucket}")
    rprint(f"Data Store: {config.data_store_id}")
    rprint(f"BQ Table: {config.bq_documents_full_table}")

    try:
        stats = store.get_kb_stats()

        rprint(f"\n[bold]Document Counts:[/bold]")
        stats_table = Table(show_header=False)
        stats_table.add_column("Status", style="cyan")
        stats_table.add_column("Count", justify="right")

        stats_table.add_row("Active", str(stats.get("active_docs", 0)))
        stats_table.add_row("Draft", str(stats.get("draft_docs", 0)))
        stats_table.add_row("Superseded", str(stats.get("superseded_docs", 0)))
        stats_table.add_row("Retired", str(stats.get("retired_docs", 0)))
        stats_table.add_row("Deleted", str(stats.get("deleted_docs", 0)))
        stats_table.add_row("─" * 15, "─" * 5)
        stats_table.add_row("[bold]Total[/bold]", f"[bold]{stats.get('total_docs', 0)}[/bold]")

        console.print(stats_table)

        # By type
        by_type = store.get_docs_by_type()
        if by_type:
            rprint(f"\n[bold]Active Documents by Type:[/bold]")
            type_table = Table(show_header=False)
            type_table.add_column("Type", style="cyan")
            type_table.add_column("Count", justify="right")

            for doc_type, count in by_type.items():
                type_table.add_row(doc_type, str(count))

            console.print(type_table)

    except Exception as e:
        rprint(f"[yellow]Could not fetch stats: {e}[/yellow]")
        rprint("Have you created the BQ tables? Run the SQL in sql/create_kb_tables.sql")


@rag_app.command("validate")
def rag_validate(
    documents_path: Optional[Path] = typer.Option(None, "--path", "-p", help="Documents directory path"),
):
    """
    Validate all documents without making changes.

    Checks YAML frontmatter, required fields, and metadata validity.
    """
    from cc_coach.rag import RAGConfig, DocumentIngester

    config = RAGConfig.from_env()
    if documents_path:
        config.documents_path = documents_path

    ingester = DocumentIngester(config)

    rprint(f"[blue]Validating documents in {config.documents_path}...[/blue]\n")

    result = ingester.ingest_documents(dry_run=True)

    if result.errors:
        rprint(f"\n[red]Validation failed with {len(result.errors)} errors[/red]")
        raise typer.Exit(1)
    else:
        rprint(f"\n[green]All {result.total_files} documents are valid![/green]")


@rag_app.command("list")
def rag_list(
    status_filter: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    doc_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by doc_type"),
    limit: int = typer.Option(50, "--limit", "-n", help="Number of results"),
):
    """List documents in the knowledge base."""
    from cc_coach.rag import RAGConfig, MetadataStore

    config = RAGConfig.from_env()
    errors = config.validate()
    if errors:
        for err in errors:
            rprint(f"[red]Config error: {err}[/red]")
        raise typer.Exit(1)

    store = MetadataStore(config)

    # Build query
    where_clauses = []
    if status_filter:
        where_clauses.append(f"status = '{status_filter}'")
    if doc_type:
        where_clauses.append(f"doc_type = '{doc_type}'")

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    query = f"""
        SELECT doc_id, version, title, doc_type, status, updated_at
        FROM `{config.bq_documents_full_table}`
        WHERE {where_sql}
        ORDER BY doc_type, doc_id, version DESC
        LIMIT {limit}
    """

    result = store.client.query(query).result()
    rows = list(result)

    if not rows:
        rprint("[yellow]No documents found[/yellow]")
        return

    table = Table(title="Knowledge Base Documents")
    table.add_column("Doc ID", style="cyan")
    table.add_column("Version")
    table.add_column("Title", max_width=40)
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Updated", style="dim")

    for row in rows:
        table.add_row(
            row["doc_id"],
            row["version"],
            (row["title"] or "")[:40],
            row["doc_type"],
            row["status"],
            row["updated_at"].strftime("%Y-%m-%d") if row["updated_at"] else "",
        )

    console.print(table)
    rprint(f"\n[dim]Showing {len(rows)} documents[/dim]")


# =============================================================================
# Monitor Commands - System monitoring and metrics
# =============================================================================

monitor_app = typer.Typer(help="Monitor system metrics, logs, and dashboards")
app.add_typer(monitor_app, name="monitor")


@monitor_app.command("summary")
def monitor_summary(
    date: Optional[str] = typer.Option(None, "--date", "-d", help="Date (YYYY-MM-DD), defaults to today"),
):
    """Show monitoring metrics summary for a date."""
    from cc_coach.monitoring.dashboard import Dashboard

    dashboard = Dashboard()
    dashboard.show_summary(date=date)


@monitor_app.command("logs")
def monitor_logs(
    date: Optional[str] = typer.Option(None, "--date", "-d", help="Date (YYYY-MM-DD)"),
    component: Optional[str] = typer.Option(None, "--component", "-c", help="Filter by component"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries to show"),
):
    """Show recent log entries."""
    from cc_coach.monitoring.dashboard import Dashboard

    dashboard = Dashboard()
    dashboard.show_logs(date=date, component=component, limit=limit)


@monitor_app.command("dashboard")
def monitor_dashboard(
    date: Optional[str] = typer.Option(None, "--date", "-d", help="Date (YYYY-MM-DD)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output HTML file path"),
    open_browser: bool = typer.Option(False, "--open", help="Open in browser after generating"),
):
    """Generate HTML dashboard."""
    from cc_coach.monitoring.dashboard import Dashboard
    import webbrowser

    dashboard = Dashboard()
    output_path = dashboard.generate_html(date=date, output_path=output)

    rprint(f"[green]Dashboard generated:[/green] {output_path}")

    if open_browser:
        webbrowser.open(f"file://{output_path}")


@monitor_app.command("metrics")
def monitor_metrics(
    date: Optional[str] = typer.Option(None, "--date", "-d", help="Date (YYYY-MM-DD)"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    save: bool = typer.Option(False, "--save", help="Save metrics to file"),
):
    """Collect and show metrics for a date."""
    from cc_coach.monitoring.metrics import MetricsCollector

    collector = MetricsCollector()
    metrics = collector.collect_metrics(date=date)

    if save:
        saved_path = collector.save_metrics(metrics, date=date)
        rprint(f"[green]Metrics saved to:[/green] {saved_path}")

    if output_json:
        rprint(json.dumps(metrics, indent=2, default=str))
    else:
        # Summary view
        e2e = metrics["e2e"]
        cost = metrics["cost"]

        rprint(f"\n[bold]Metrics for {metrics['date']}[/bold]")
        rprint("-" * 50)

        rprint(f"\n[cyan]E2E Metrics:[/cyan]")
        rprint(f"  Total Requests: {e2e['total_requests']}")
        rprint(f"  Success Rate: {e2e['success_rate']*100:.1f}%")
        rprint(f"  Latency (p50): {e2e['latency_p50_ms']}ms")
        rprint(f"  Latency (p95): {e2e['latency_p95_ms']}ms")

        rprint(f"\n[cyan]Cost:[/cyan]")
        rprint(f"  Gemini Tokens: {cost['gemini_input_tokens']:,} in / {cost['gemini_output_tokens']:,} out")
        rprint(f"  Gemini Cost: ${cost['gemini_cost_usd']:.4f}")
        rprint(f"  Total Estimated: ${cost['total_estimated_usd']:.4f}")

        if metrics["components"]:
            rprint(f"\n[cyan]Components:[/cyan]")
            for name, comp in sorted(metrics["components"].items()):
                rprint(f"  {name}: {comp['success_rate']*100:.0f}% success, {comp['latency_p50_ms']}ms p50")


# =============================================================================
# Summary Commands - Daily and Weekly Agent Summaries
# =============================================================================

summary_app = typer.Typer(help="Generate and view agent coaching summaries")
app.add_typer(summary_app, name="summary")


@summary_app.command("daily")
def summary_daily(
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Specific agent ID"),
    target_date: Optional[str] = typer.Option(None, "--date", "-d", help="Date (YYYY-MM-DD), defaults to yesterday"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Generate daily summary for agent(s)."""
    from datetime import date as date_type, timedelta
    from cc_coach.services.summary import SummaryOrchestrator

    # Default to yesterday
    if target_date:
        dt = date_type.fromisoformat(target_date)
    else:
        dt = date_type.today() - timedelta(days=1)

    orchestrator = SummaryOrchestrator(model=model)

    try:
        if agent_id:
            # Single agent
            rprint(f"[bold blue]Generating daily summary for {agent_id} on {dt}...[/bold blue]")
            summary = orchestrator.generate_daily_summary(agent_id, dt)

            if not summary:
                rprint(f"[yellow]No coaching data for {agent_id} on {dt}[/yellow]")
                return

            if output_json:
                rprint(summary.model_dump_json(indent=2))
            else:
                _display_daily_summary(summary)

            rprint(f"\n[bold green]Daily summary saved to BigQuery[/bold green]")
        else:
            # All agents
            rprint(f"[bold blue]Generating daily summaries for all agents on {dt}...[/bold blue]")
            results = orchestrator.generate_all_daily_summaries(dt)

            for agent_result in results["agents"]:
                status_icon = "[green]OK[/green]" if agent_result["status"] == "success" else "[yellow]skip[/yellow]" if agent_result["status"] == "skipped" else "[red]FAIL[/red]"
                rprint(f"  {agent_result['agent_id']}: {status_icon}")
                if agent_result.get("error"):
                    rprint(f"    [dim]{agent_result['error']}[/dim]")

            rprint(f"\n[bold]Complete: {results['success']} success, {results['skipped']} skipped, {results['failed']} failed[/bold]")

    except Exception as e:
        logger.exception(f"Failed to generate daily summary")
        rprint(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)
    finally:
        from cc_coach.monitoring.tracing import shutdown_tracing
        shutdown_tracing()


@summary_app.command("weekly")
def summary_weekly(
    agent_id: Optional[str] = typer.Option(None, "--agent", "-a", help="Specific agent ID"),
    week_start: Optional[str] = typer.Option(None, "--week", "-w", help="Week start date (Monday, YYYY-MM-DD), defaults to last week"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Generate weekly summary for agent(s)."""
    from datetime import date as date_type, timedelta
    from cc_coach.services.summary import SummaryOrchestrator

    # Default to last week's Monday
    if week_start:
        dt = date_type.fromisoformat(week_start)
    else:
        today = date_type.today()
        # Go back to last Monday
        dt = today - timedelta(days=today.weekday() + 7)

    # Ensure it's a Monday
    if dt.weekday() != 0:
        dt = dt - timedelta(days=dt.weekday())

    orchestrator = SummaryOrchestrator(model=model)

    try:
        if agent_id:
            # Single agent
            rprint(f"[bold blue]Generating weekly summary for {agent_id} week of {dt}...[/bold blue]")
            summary = orchestrator.generate_weekly_summary(agent_id, dt)

            if not summary:
                rprint(f"[yellow]No coaching data for {agent_id} week of {dt}[/yellow]")
                return

            if output_json:
                rprint(summary.model_dump_json(indent=2))
            else:
                _display_weekly_summary(summary)

            rprint(f"\n[bold green]Weekly summary saved to BigQuery[/bold green]")
        else:
            # All agents
            rprint(f"[bold blue]Generating weekly summaries for all agents week of {dt}...[/bold blue]")
            results = orchestrator.generate_all_weekly_summaries(dt)

            for agent_result in results["agents"]:
                status_icon = "[green]OK[/green]" if agent_result["status"] == "success" else "[yellow]skip[/yellow]" if agent_result["status"] == "skipped" else "[red]FAIL[/red]"
                rprint(f"  {agent_result['agent_id']}: {status_icon}")
                if agent_result.get("error"):
                    rprint(f"    [dim]{agent_result['error']}[/dim]")

            rprint(f"\n[bold]Complete: {results['success']} success, {results['skipped']} skipped, {results['failed']} failed[/bold]")

    except Exception as e:
        logger.exception(f"Failed to generate weekly summary")
        rprint(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)
    finally:
        from cc_coach.monitoring.tracing import shutdown_tracing
        shutdown_tracing()


@summary_app.command("get-daily")
def summary_get_daily(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    target_date: Optional[str] = typer.Option(None, "--date", "-d", help="Date (YYYY-MM-DD)"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get existing daily summary for an agent."""
    from datetime import date as date_type, timedelta
    from cc_coach.services.summary import SummaryOrchestrator

    if target_date:
        dt = date_type.fromisoformat(target_date)
    else:
        dt = date_type.today() - timedelta(days=1)

    orchestrator = SummaryOrchestrator()
    result = orchestrator.get_daily_summary(agent_id, dt)

    if not result:
        rprint(f"[yellow]No daily summary found for {agent_id} on {dt}[/yellow]")
        raise typer.Exit(1)

    if output_json:
        rprint(json.dumps(result, default=str, indent=2))
    else:
        _display_daily_summary_from_bq(result)


@summary_app.command("get-weekly")
def summary_get_weekly(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    week_start: Optional[str] = typer.Option(None, "--week", "-w", help="Week start (Monday, YYYY-MM-DD)"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get existing weekly summary for an agent."""
    from datetime import date as date_type, timedelta
    from cc_coach.services.summary import SummaryOrchestrator

    if week_start:
        dt = date_type.fromisoformat(week_start)
    else:
        today = date_type.today()
        dt = today - timedelta(days=today.weekday() + 7)

    orchestrator = SummaryOrchestrator()
    result = orchestrator.get_weekly_summary(agent_id, dt)

    if not result:
        rprint(f"[yellow]No weekly summary found for {agent_id} week of {dt}[/yellow]")
        raise typer.Exit(1)

    if output_json:
        rprint(json.dumps(result, default=str, indent=2))
    else:
        _display_weekly_summary_from_bq(result)


def _display_daily_summary(summary):
    """Display daily summary in rich format."""
    rprint(f"\n[bold]Daily Summary: {summary.agent_id}[/bold]")
    rprint(f"[dim]Date: {summary.date} | Calls: {summary.call_count}[/dim]")
    rprint("-" * 60)

    # Scores
    scores_table = Table(title="Scores", show_header=False)
    scores_table.add_column("Dimension", style="cyan")
    scores_table.add_column("Score", justify="right")

    scores_table.add_row("Empathy", f"{summary.avg_empathy}/10")
    scores_table.add_row("Compliance", f"{summary.avg_compliance}/10")
    scores_table.add_row("Resolution", f"{summary.avg_resolution}/10")
    scores_table.add_row("Professionalism", f"{summary.avg_professionalism}/10")
    scores_table.add_row("Efficiency", f"{summary.avg_efficiency}/10")
    scores_table.add_row("De-escalation", f"{summary.avg_de_escalation}/10")
    scores_table.add_row("Resolution Rate", f"{summary.resolution_rate * 100:.0f}%")

    console.print(scores_table)

    # Narrative
    rprint(f"\n[bold]Summary:[/bold]")
    rprint(f"  {summary.daily_narrative}")

    rprint(f"\n[bold]Focus Area:[/bold] [cyan]{summary.focus_area}[/cyan]")

    if summary.quick_wins:
        rprint(f"\n[bold]Quick Wins:[/bold]")
        for qw in summary.quick_wins:
            rprint(f"  - {qw}")

    if summary.top_issues:
        rprint(f"\n[bold red]Top Issues:[/bold red]")
        for issue in summary.top_issues[:3]:
            rprint(f"  - {issue}")

    if summary.top_strengths:
        rprint(f"\n[bold green]Strengths:[/bold green]")
        for strength in summary.top_strengths[:3]:
            rprint(f"  + {strength}")


def _display_daily_summary_from_bq(result: dict):
    """Display daily summary from BQ row."""
    rprint(f"\n[bold]Daily Summary: {result['agent_id']}[/bold]")
    rprint(f"[dim]Date: {result['date']} | Calls: {result['call_count']}[/dim]")
    rprint("-" * 60)

    # Scores
    rprint(f"\n[cyan]Scores:[/cyan]")
    rprint(f"  Empathy: {result.get('avg_empathy', 'N/A')}/10")
    rprint(f"  Compliance: {result.get('avg_compliance', 'N/A')}/10")
    rprint(f"  Resolution: {result.get('avg_resolution', 'N/A')}/10")
    rprint(f"  Resolution Rate: {result.get('resolution_rate', 0) * 100:.0f}%")

    rprint(f"\n[bold]Summary:[/bold]")
    rprint(f"  {result.get('daily_narrative', 'N/A')}")

    rprint(f"\n[bold]Focus Area:[/bold] [cyan]{result.get('focus_area', 'N/A')}[/cyan]")

    quick_wins = result.get('quick_wins', [])
    if quick_wins:
        rprint(f"\n[bold]Quick Wins:[/bold]")
        for qw in quick_wins:
            rprint(f"  - {qw}")

    rprint(f"\n[dim]Generated: {result.get('generated_at', 'N/A')}[/dim]")


def _display_weekly_summary(summary):
    """Display weekly summary in rich format."""
    rprint(f"\n[bold]Weekly Summary: {summary.agent_id}[/bold]")
    rprint(f"[dim]Week of: {summary.week_start} | Calls: {summary.total_calls}[/dim]")
    rprint("-" * 60)

    # Scores with deltas
    scores_table = Table(title="Week Scores", show_header=True)
    scores_table.add_column("Dimension", style="cyan")
    scores_table.add_column("Score", justify="right")
    scores_table.add_column("Change", justify="right")

    def format_delta(delta):
        if delta is None:
            return "[dim]N/A[/dim]"
        color = "green" if delta > 0 else "red" if delta < 0 else "dim"
        sign = "+" if delta > 0 else ""
        return f"[{color}]{sign}{delta:.1f}[/{color}]"

    scores_table.add_row("Empathy", f"{summary.empathy_score}/10", format_delta(summary.empathy_delta))
    scores_table.add_row("Compliance", f"{summary.compliance_score}/10", format_delta(summary.compliance_delta))
    scores_table.add_row("Resolution", f"{summary.resolution_score}/10", format_delta(summary.resolution_delta))
    scores_table.add_row("Professionalism", f"{summary.professionalism_score}/10", "[dim]N/A[/dim]")
    scores_table.add_row("Efficiency", f"{summary.efficiency_score}/10", "[dim]N/A[/dim]")
    scores_table.add_row("De-escalation", f"{summary.de_escalation_score}/10", "[dim]N/A[/dim]")

    console.print(scores_table)

    # Summary
    rprint(f"\n[bold]Summary:[/bold]")
    rprint(f"  {summary.weekly_summary}")

    rprint(f"\n[bold]Trend Analysis:[/bold]")
    rprint(f"  {summary.trend_analysis}")

    rprint(f"\n[bold]Action Plan:[/bold]")
    rprint(f"  {summary.action_plan}")

    if summary.recommended_training:
        rprint(f"\n[bold yellow]Recommended Training:[/bold yellow]")
        for training in summary.recommended_training:
            rprint(f"  - {training}")

    if summary.top_issues:
        rprint(f"\n[bold red]Top Issues:[/bold red]")
        for issue in summary.top_issues[:3]:
            rprint(f"  - {issue}")

    if summary.top_strengths:
        rprint(f"\n[bold green]Strengths:[/bold green]")
        for strength in summary.top_strengths[:3]:
            rprint(f"  + {strength}")


def _display_weekly_summary_from_bq(result: dict):
    """Display weekly summary from BQ row."""
    rprint(f"\n[bold]Weekly Summary: {result['agent_id']}[/bold]")
    rprint(f"[dim]Week of: {result['week_start']} | Calls: {result['total_calls']}[/dim]")
    rprint("-" * 60)

    # Scores
    rprint(f"\n[cyan]Scores:[/cyan]")
    rprint(f"  Empathy: {result.get('empathy_score', 'N/A')}/10")
    rprint(f"  Compliance: {result.get('compliance_score', 'N/A')}/10")
    rprint(f"  Resolution: {result.get('resolution_score', 'N/A')}/10")

    rprint(f"\n[bold]Summary:[/bold]")
    rprint(f"  {result.get('weekly_summary', 'N/A')}")

    rprint(f"\n[bold]Trend Analysis:[/bold]")
    rprint(f"  {result.get('trend_analysis', 'N/A')}")

    rprint(f"\n[bold]Action Plan:[/bold]")
    rprint(f"  {result.get('action_plan', 'N/A')}")

    training = result.get('recommended_training', [])
    if training:
        rprint(f"\n[bold yellow]Recommended Training:[/bold yellow]")
        for t in training:
            rprint(f"  - {t}")

    rprint(f"\n[dim]Generated: {result.get('generated_at', 'N/A')}[/dim]")


if __name__ == "__main__":
    app()
