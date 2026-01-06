"""Metrics aggregation for AI system monitoring.

Aggregates log data into metrics summaries for dashboards and analysis.
"""

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from cc_coach.monitoring.logging import DEFAULT_LOG_DIR, read_logs


@dataclass
class ComponentMetrics:
    """Metrics for a single component."""

    total_calls: int = 0
    success_count: int = 0
    error_count: int = 0
    latencies_ms: list[int] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_calls == 0:
            return 0.0
        return self.success_count / self.total_calls

    @property
    def latency_p50(self) -> int:
        """Get p50 (median) latency."""
        if not self.latencies_ms:
            return 0
        return int(statistics.median(self.latencies_ms))

    @property
    def latency_p95(self) -> int:
        """Get p95 latency."""
        if not self.latencies_ms:
            return 0
        if len(self.latencies_ms) < 20:
            return max(self.latencies_ms)
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx]

    @property
    def latency_p99(self) -> int:
        """Get p99 latency."""
        if not self.latencies_ms:
            return 0
        if len(self.latencies_ms) < 100:
            return max(self.latencies_ms)
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[idx]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_calls": self.total_calls,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": round(self.success_rate, 3),
            "latency_p50_ms": self.latency_p50,
            "latency_p95_ms": self.latency_p95,
            "latency_p99_ms": self.latency_p99,
        }


@dataclass
class CostMetrics:
    """Cost metrics aggregation."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_gemini_cost: float = 0.0
    total_bq_cost: float = 0.0
    total_search_cost: float = 0.0

    @property
    def total_cost(self) -> float:
        """Get total cost."""
        return self.total_gemini_cost + self.total_bq_cost + self.total_search_cost

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "gemini_input_tokens": self.total_input_tokens,
            "gemini_output_tokens": self.total_output_tokens,
            "gemini_cost_usd": round(self.total_gemini_cost, 6),
            "bigquery_estimated_usd": round(self.total_bq_cost, 6),
            "vertex_search_usd": round(self.total_search_cost, 6),
            "total_estimated_usd": round(self.total_cost, 6),
        }


class MetricsCollector:
    """Collects and aggregates metrics from log files."""

    def __init__(self, log_dir: Optional[Path] = None):
        """Initialize metrics collector.

        Args:
            log_dir: Directory containing log files
        """
        self.log_dir = log_dir or DEFAULT_LOG_DIR

    def collect_metrics(self, date: Optional[str] = None) -> dict:
        """Collect metrics for a given date.

        Args:
            date: Date string (YYYY-MM-DD), defaults to today

        Returns:
            Metrics summary dictionary
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        logs = read_logs(self.log_dir, date)

        if not logs:
            return self._empty_metrics(date)

        # Aggregate by component
        components: dict[str, ComponentMetrics] = defaultdict(ComponentMetrics)
        cost = CostMetrics()
        errors: list[dict] = []

        for entry in logs:
            component = entry.get("component", "unknown")
            metrics = components[component]

            metrics.total_calls += 1
            if entry.get("success", False):
                metrics.success_count += 1
            else:
                metrics.error_count += 1
                errors.append({
                    "timestamp": entry.get("timestamp"),
                    "component": component,
                    "error_type": entry.get("error_type", "Unknown"),
                    "error": entry.get("error", ""),
                    "conversation_id": entry.get("conversation_id"),
                })

            if "duration_ms" in entry:
                metrics.latencies_ms.append(entry["duration_ms"])

            # Track tokens/cost from model_call or e2e entries
            if "input_tokens" in entry:
                cost.total_input_tokens += entry["input_tokens"]
            if "output_tokens" in entry:
                cost.total_output_tokens += entry["output_tokens"]
            if "cost_usd" in entry:
                cost.total_gemini_cost += entry["cost_usd"]
            if "total_cost_usd" in entry:
                # E2E entry has total cost
                pass  # Already tracked in component entries

        # Build summary
        e2e_metrics = components.get("e2e", ComponentMetrics())

        return {
            "date": date,
            "generated_at": datetime.now().isoformat(),
            "period": "daily",
            "e2e": {
                "total_requests": e2e_metrics.total_calls,
                "success_count": e2e_metrics.success_count,
                "error_count": e2e_metrics.error_count,
                "success_rate": round(e2e_metrics.success_rate, 3),
                "latency_p50_ms": e2e_metrics.latency_p50,
                "latency_p95_ms": e2e_metrics.latency_p95,
                "latency_p99_ms": e2e_metrics.latency_p99,
            },
            "components": {
                name: metrics.to_dict()
                for name, metrics in components.items()
                if name != "e2e"
            },
            "cost": cost.to_dict(),
            "errors": errors[-10:],  # Last 10 errors
        }

    def _empty_metrics(self, date: str) -> dict:
        """Return empty metrics structure."""
        return {
            "date": date,
            "generated_at": datetime.now().isoformat(),
            "period": "daily",
            "e2e": {
                "total_requests": 0,
                "success_count": 0,
                "error_count": 0,
                "success_rate": 0.0,
                "latency_p50_ms": 0,
                "latency_p95_ms": 0,
                "latency_p99_ms": 0,
            },
            "components": {},
            "cost": CostMetrics().to_dict(),
            "errors": [],
        }

    def save_metrics(self, metrics: dict, date: Optional[str] = None) -> Path:
        """Save metrics to JSON file.

        Args:
            metrics: Metrics dictionary
            date: Date string for filename

        Returns:
            Path to saved file
        """
        if date is None:
            date = metrics.get("date", datetime.now().strftime("%Y-%m-%d"))

        output_file = self.log_dir / f"metrics_{date}.json"
        with open(output_file, "w") as f:
            json.dump(metrics, f, indent=2)

        return output_file

    def load_metrics(self, date: Optional[str] = None) -> Optional[dict]:
        """Load metrics from JSON file.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            Metrics dictionary or None if not found
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        metrics_file = self.log_dir / f"metrics_{date}.json"
        if not metrics_file.exists():
            return None

        with open(metrics_file) as f:
            return json.load(f)
