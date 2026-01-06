"""Dashboard visualization for AI system monitoring.

Generates console dashboards and HTML reports from metrics.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cc_coach.monitoring.logging import DEFAULT_LOG_DIR, read_logs
from cc_coach.monitoring.metrics import MetricsCollector


def _make_progress_bar(percentage: float, width: int = 20) -> str:
    """Create a text-based progress bar."""
    filled = int(width * percentage)
    empty = width - filled
    return "█" * filled + "░" * empty


def _format_latency(ms: int) -> str:
    """Format latency for display."""
    if ms >= 1000:
        return f"{ms/1000:.1f}s"
    return f"{ms}ms"


def _format_cost(usd: float) -> str:
    """Format cost for display."""
    if usd < 0.01:
        return f"${usd:.4f}"
    return f"${usd:.2f}"


class Dashboard:
    """Dashboard for monitoring visualization."""

    def __init__(self, log_dir: Optional[Path] = None):
        """Initialize dashboard.

        Args:
            log_dir: Directory containing log files
        """
        self.log_dir = log_dir or DEFAULT_LOG_DIR
        self.collector = MetricsCollector(self.log_dir)
        self.console = Console()

    def show_summary(self, date: Optional[str] = None) -> None:
        """Show metrics summary in console.

        Args:
            date: Date to show (YYYY-MM-DD), defaults to today
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        metrics = self.collector.collect_metrics(date)

        # Build header
        is_today = date == datetime.now().strftime("%Y-%m-%d")
        date_label = f"{date} {'(Today)' if is_today else ''}"

        self.console.print()
        self.console.print(
            Panel(
                f"[bold cyan]CONVERSATION COACH - MONITORING[/bold cyan]\n"
                f"[dim]{date_label}[/dim]",
                expand=False,
            )
        )

        # E2E summary
        e2e = metrics["e2e"]
        success_rate = e2e["success_rate"]
        bar = _make_progress_bar(success_rate)

        e2e_table = Table(show_header=False, box=None, padding=(0, 2))
        e2e_table.add_column("Metric", style="cyan")
        e2e_table.add_column("Value", style="white")

        e2e_table.add_row(
            "E2E Success Rate",
            f"{bar} {success_rate*100:.1f}% ({e2e['success_count']}/{e2e['total_requests']})"
        )
        e2e_table.add_row("Total Requests", str(e2e["total_requests"]))
        e2e_table.add_row("Latency (p50)", _format_latency(e2e["latency_p50_ms"]))
        e2e_table.add_row("Latency (p95)", _format_latency(e2e["latency_p95_ms"]))

        self.console.print(Panel(e2e_table, title="[bold]E2E Metrics[/bold]", border_style="green"))

        # Component health
        if metrics["components"]:
            comp_table = Table(show_header=True, header_style="bold cyan")
            comp_table.add_column("Component", style="white")
            comp_table.add_column("Success Rate", style="white")
            comp_table.add_column("Calls", style="dim")
            comp_table.add_column("Latency (p50)", style="dim")

            for name, comp in sorted(metrics["components"].items()):
                rate = comp["success_rate"]
                bar = _make_progress_bar(rate, 15)
                style = "green" if rate >= 0.95 else "yellow" if rate >= 0.80 else "red"

                comp_table.add_row(
                    name,
                    f"[{style}]{bar}[/{style}] {rate*100:.0f}%",
                    str(comp["total_calls"]),
                    _format_latency(comp["latency_p50_ms"]),
                )

            self.console.print(Panel(comp_table, title="[bold]Component Health[/bold]", border_style="blue"))

        # Cost summary
        cost = metrics["cost"]
        cost_table = Table(show_header=False, box=None, padding=(0, 2))
        cost_table.add_column("Item", style="cyan")
        cost_table.add_column("Value", style="white")

        cost_table.add_row("Gemini Tokens (in)", f"{cost['gemini_input_tokens']:,}")
        cost_table.add_row("Gemini Tokens (out)", f"{cost['gemini_output_tokens']:,}")
        cost_table.add_row("Gemini Cost", _format_cost(cost["gemini_cost_usd"]))
        cost_table.add_row("BigQuery (est)", _format_cost(cost["bigquery_estimated_usd"]))
        cost_table.add_row("[bold]Total[/bold]", f"[bold]{_format_cost(cost['total_estimated_usd'])}[/bold]")

        self.console.print(Panel(cost_table, title="[bold]Cost Summary[/bold]", border_style="yellow"))

        # Recent errors
        if metrics["errors"]:
            error_table = Table(show_header=True, header_style="bold red")
            error_table.add_column("Time", style="dim")
            error_table.add_column("Component", style="white")
            error_table.add_column("Error", style="red")
            error_table.add_column("Conversation", style="dim")

            for err in metrics["errors"][-5:]:
                time_str = err.get("timestamp", "")[:19].replace("T", " ")
                error_table.add_row(
                    time_str[11:16] if time_str else "",
                    err.get("component", ""),
                    err.get("error_type", "Unknown"),
                    err.get("conversation_id", "")[:20] if err.get("conversation_id") else "",
                )

            self.console.print(Panel(error_table, title="[bold]Recent Errors[/bold]", border_style="red"))

        self.console.print()

    def show_logs(
        self,
        date: Optional[str] = None,
        component: Optional[str] = None,
        limit: int = 20,
    ) -> None:
        """Show recent log entries.

        Args:
            date: Date to show
            component: Filter to specific component
            limit: Maximum entries to show
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        logs = read_logs(self.log_dir, date, component)
        logs = logs[-limit:]

        if not logs:
            self.console.print(f"[yellow]No logs found for {date}[/yellow]")
            return

        log_table = Table(show_header=True, header_style="bold cyan")
        log_table.add_column("Time", style="dim", width=8)
        log_table.add_column("Request", style="dim", width=10)
        log_table.add_column("Component", style="white", width=15)
        log_table.add_column("Status", width=8)
        log_table.add_column("Duration", style="dim", width=10)
        log_table.add_column("Details", style="dim")

        for entry in logs:
            time_str = entry.get("timestamp", "")
            time_short = time_str[11:19] if time_str else ""

            success = entry.get("success", False)
            status = "[green]OK[/green]" if success else "[red]FAIL[/red]"

            duration = entry.get("duration_ms", 0)
            duration_str = _format_latency(duration) if duration else ""

            # Build details string
            details = []
            if entry.get("conversation_id"):
                details.append(entry["conversation_id"][:15])
            if entry.get("input_tokens"):
                details.append(f"in:{entry['input_tokens']}")
            if entry.get("output_tokens"):
                details.append(f"out:{entry['output_tokens']}")
            if entry.get("error_type"):
                details.append(f"[red]{entry['error_type']}[/red]")

            log_table.add_row(
                time_short,
                entry.get("request_id", "")[:8],
                entry.get("component", ""),
                status,
                duration_str,
                " ".join(details),
            )

        title = f"Logs for {date}"
        if component:
            title += f" (component: {component})"

        self.console.print(Panel(log_table, title=f"[bold]{title}[/bold]"))

    def generate_html(
        self,
        date: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Generate HTML dashboard.

        Args:
            date: Date to generate for
            output_path: Output file path

        Returns:
            Path to generated HTML file
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        if output_path is None:
            output_path = self.log_dir / f"dashboard_{date}.html"

        metrics = self.collector.collect_metrics(date)
        e2e = metrics["e2e"]
        cost = metrics["cost"]

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Conversation Coach - Monitoring Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               margin: 0; padding: 20px; background: #1a1a2e; color: #eee; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #00d9ff; border-bottom: 2px solid #00d9ff; padding-bottom: 10px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
        .card {{ background: #16213e; border-radius: 8px; padding: 20px; }}
        .card h2 {{ margin-top: 0; color: #00d9ff; font-size: 1.1em; }}
        .metric {{ font-size: 2em; font-weight: bold; color: #fff; }}
        .metric-label {{ color: #888; font-size: 0.9em; }}
        .progress {{ background: #0f3460; border-radius: 4px; height: 20px; overflow: hidden; }}
        .progress-bar {{ height: 100%; background: linear-gradient(90deg, #00d9ff, #00ff88); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #333; }}
        th {{ color: #00d9ff; }}
        .success {{ color: #00ff88; }}
        .error {{ color: #ff4444; }}
        .cost {{ color: #ffcc00; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Conversation Coach - Monitoring</h1>
        <p style="color: #888;">Date: {date} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <div class="grid">
            <div class="card">
                <h2>E2E Success Rate</h2>
                <div class="metric">{e2e['success_rate']*100:.1f}%</div>
                <div class="progress"><div class="progress-bar" style="width: {e2e['success_rate']*100}%"></div></div>
                <p class="metric-label">{e2e['success_count']} / {e2e['total_requests']} requests</p>
            </div>

            <div class="card">
                <h2>Latency (p50 / p95)</h2>
                <div class="metric">{e2e['latency_p50_ms']/1000:.1f}s / {e2e['latency_p95_ms']/1000:.1f}s</div>
                <p class="metric-label">Median / 95th percentile</p>
            </div>

            <div class="card">
                <h2>Today's Cost</h2>
                <div class="metric cost">${cost['total_estimated_usd']:.4f}</div>
                <p class="metric-label">Gemini: ${cost['gemini_cost_usd']:.4f} | BQ: ${cost['bigquery_estimated_usd']:.4f}</p>
            </div>

            <div class="card">
                <h2>Token Usage</h2>
                <div class="metric">{cost['gemini_input_tokens'] + cost['gemini_output_tokens']:,}</div>
                <p class="metric-label">Input: {cost['gemini_input_tokens']:,} | Output: {cost['gemini_output_tokens']:,}</p>
            </div>
        </div>

        <div class="card" style="margin-top: 20px;">
            <h2>Component Health</h2>
            <table>
                <tr><th>Component</th><th>Success Rate</th><th>Calls</th><th>Latency (p50)</th></tr>
                {''.join(f'''<tr>
                    <td>{name}</td>
                    <td class="{'success' if c['success_rate'] >= 0.95 else 'error'}">{c['success_rate']*100:.0f}%</td>
                    <td>{c['total_calls']}</td>
                    <td>{c['latency_p50_ms']}ms</td>
                </tr>''' for name, c in sorted(metrics['components'].items()))}
            </table>
        </div>

        {'<div class="card" style="margin-top: 20px;"><h2>Recent Errors</h2><table><tr><th>Time</th><th>Component</th><th>Error</th></tr>' + ''.join(f'''<tr>
            <td>{e.get('timestamp', '')[:19]}</td>
            <td>{e.get('component', '')}</td>
            <td class="error">{e.get('error_type', '')}</td>
        </tr>''' for e in metrics['errors'][-5:]) + '</table></div>' if metrics['errors'] else ''}
    </div>
</body>
</html>"""

        with open(output_path, "w") as f:
            f.write(html)

        return output_path
