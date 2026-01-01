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


if __name__ == "__main__":
    app()
