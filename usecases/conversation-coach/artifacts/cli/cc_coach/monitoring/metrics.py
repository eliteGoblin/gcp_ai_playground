"""Metrics aggregation and real-time export for AI system monitoring.

Provides two complementary metrics approaches:
1. Log-based aggregation: Reads JSONL logs and computes summaries
2. Real-time OTEL export: Exports metrics directly to Cloud Monitoring

Real-time metrics exported (via OpenTelemetry):
- cc_coach_requests_total: Counter of coaching requests
- cc_coach_request_duration_ms: Histogram of E2E latency
- cc_coach_model_latency_ms: Histogram of model call latency
- cc_coach_tokens_total: Counter of tokens (input/output)
- cc_coach_cost_micro_usd: Counter of cost in micro-USD
- cc_coach_errors_total: Counter of errors by type
- cc_coach_rag_requests_total: Counter of RAG requests
"""

import json
import os
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from cc_coach.monitoring.logging import DEFAULT_LOG_DIR, read_logs

# ============================================================================
# Real-time OTEL Metrics
# ============================================================================

# Environment configuration for OTEL metrics
ENABLE_OTEL_METRICS = os.getenv("CC_ENABLE_METRICS", "true").lower() == "true"
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "conversation-coach")
OTEL_SERVICE_VERSION = os.getenv("SERVICE_VERSION", "dev")

# Global meter and instruments (lazy initialized)
_meter = None
_provider = None
_request_counter = None
_request_duration = None
_model_latency = None
_token_counter = None
_cost_counter = None
_error_counter = None
_rag_counter = None


def setup_otel_metrics(
    service_name: str = OTEL_SERVICE_NAME,
    enable_cloud_monitoring: bool = True,
):
    """Setup OpenTelemetry metrics with Cloud Monitoring export.

    Args:
        service_name: Name of the service for metric attribution
        enable_cloud_monitoring: Whether to export to Cloud Monitoring

    Returns:
        Configured meter instance
    """
    global _provider, _meter
    global _request_counter, _request_duration, _model_latency
    global _token_counter, _cost_counter, _error_counter, _rag_counter

    if not ENABLE_OTEL_METRICS:
        return None

    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        import logging
        logging.getLogger(__name__).warning(
            "OpenTelemetry SDK not installed. Real-time metrics disabled."
        )
        return None

    # Create resource with service info
    resource = Resource.create({
        "service.name": service_name,
        "service.version": OTEL_SERVICE_VERSION,
    })

    if enable_cloud_monitoring:
        try:
            from opentelemetry.exporter.cloud_monitoring import (
                CloudMonitoringMetricsExporter,
            )
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

            # Get project ID
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
            if not project_id:
                creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                if creds_file and os.path.exists(creds_file):
                    with open(creds_file) as f:
                        creds = json.load(f)
                        project_id = creds.get("project_id")

            if not project_id:
                import logging
                logging.getLogger(__name__).warning(
                    "No project ID found. Cloud Monitoring export disabled."
                )
                _provider = MeterProvider(resource=resource)
            else:
                # Create exporter and reader
                exporter = CloudMonitoringMetricsExporter(project_id=project_id)
                reader = PeriodicExportingMetricReader(
                    exporter,
                    export_interval_millis=15000,  # Export every 15 seconds
                )
                _provider = MeterProvider(resource=resource, metric_readers=[reader])

                import logging
                logging.getLogger(__name__).info(
                    f"Cloud Monitoring metrics enabled for project: {project_id}"
                )

        except ImportError:
            import logging
            logging.getLogger(__name__).warning(
                "opentelemetry-exporter-gcp-monitoring not installed. "
                "Real-time Cloud Monitoring export disabled."
            )
            _provider = MeterProvider(resource=resource)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Could not setup Cloud Monitoring exporter: {e}. "
                "Metrics will not be exported."
            )
            _provider = MeterProvider(resource=resource)
    else:
        _provider = MeterProvider(resource=resource)

    metrics.set_meter_provider(_provider)
    _meter = metrics.get_meter(service_name, OTEL_SERVICE_VERSION)

    # Create metric instruments
    _request_counter = _meter.create_counter(
        name="cc_coach_requests_total",
        description="Total coaching requests",
        unit="1",
    )

    _request_duration = _meter.create_histogram(
        name="cc_coach_request_duration_ms",
        description="E2E request duration in milliseconds",
        unit="ms",
    )

    _model_latency = _meter.create_histogram(
        name="cc_coach_model_latency_ms",
        description="Model call latency in milliseconds",
        unit="ms",
    )

    _token_counter = _meter.create_counter(
        name="cc_coach_tokens_total",
        description="Total tokens used",
        unit="1",
    )

    _cost_counter = _meter.create_counter(
        name="cc_coach_cost_micro_usd",
        description="Cost in micro-USD (USD * 1,000,000)",
        unit="1",
    )

    _error_counter = _meter.create_counter(
        name="cc_coach_errors_total",
        description="Total errors by type",
        unit="1",
    )

    _rag_counter = _meter.create_counter(
        name="cc_coach_rag_requests_total",
        description="RAG retrieval requests",
        unit="1",
    )

    return _meter


def get_otel_meter():
    """Get or create the global OTEL meter.

    Returns:
        Meter instance or None if not available
    """
    global _meter
    if _meter is None and ENABLE_OTEL_METRICS:
        setup_otel_metrics()
    return _meter


def shutdown_otel_metrics():
    """Shutdown OTEL metrics and flush any pending exports."""
    global _provider
    if _provider is not None:
        _provider.shutdown()


# Convenience functions for recording OTEL metrics

def record_request(success: bool, call_type: str = "unknown"):
    """Record a coaching request to OTEL metrics.

    Args:
        success: Whether the request succeeded
        call_type: Type of call (hardship, collections, etc.)
    """
    global _request_counter
    if _request_counter is None:
        get_otel_meter()
    if _request_counter:
        _request_counter.add(
            1,
            {"success": str(success).lower(), "call_type": call_type}
        )


def record_duration(duration_ms: float, component: str = "e2e"):
    """Record request duration to OTEL metrics.

    Args:
        duration_ms: Duration in milliseconds
        component: Component name (e2e, model, rag, etc.)
    """
    global _request_duration, _model_latency
    if _request_duration is None:
        get_otel_meter()
    if component == "e2e" and _request_duration:
        _request_duration.record(duration_ms, {"component": component})
    elif component == "model" and _model_latency:
        _model_latency.record(duration_ms, {"component": component})


def record_tokens(input_tokens: int, output_tokens: int, model: str = "gemini"):
    """Record token usage to OTEL metrics.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model name
    """
    global _token_counter
    if _token_counter is None:
        get_otel_meter()
    if _token_counter:
        _token_counter.add(input_tokens, {"type": "input", "model": model})
        _token_counter.add(output_tokens, {"type": "output", "model": model})


def record_cost(cost_usd: float, model: str = "gemini"):
    """Record cost to OTEL metrics.

    Args:
        cost_usd: Cost in USD
        model: Model name
    """
    global _cost_counter
    if _cost_counter is None:
        get_otel_meter()
    if _cost_counter:
        # Convert to micro-USD for precision (x1,000,000)
        micro_usd = int(cost_usd * 1_000_000)
        _cost_counter.add(micro_usd, {"model": model})


def record_error(error_type: str, component: str = "unknown"):
    """Record an error to OTEL metrics.

    Args:
        error_type: Type of error
        component: Component where error occurred
    """
    global _error_counter
    if _error_counter is None:
        get_otel_meter()
    if _error_counter:
        _error_counter.add(1, {"error_type": error_type, "component": component})


def record_rag_request(success: bool, docs_retrieved: int, fallback_used: bool):
    """Record RAG retrieval request to OTEL metrics.

    Args:
        success: Whether retrieval succeeded
        docs_retrieved: Number of documents retrieved
        fallback_used: Whether fallback policy was used
    """
    global _rag_counter
    if _rag_counter is None:
        get_otel_meter()
    if _rag_counter:
        _rag_counter.add(
            1,
            {
                "success": str(success).lower(),
                "fallback_used": str(fallback_used).lower(),
                "docs_retrieved": str(min(docs_retrieved, 10)),
            }
        )


# ============================================================================
# Log-based Metrics Aggregation (Original Implementation)
# ============================================================================


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
