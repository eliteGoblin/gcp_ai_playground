"""Structured logging for AI system monitoring.

Provides component-level logging with timing, request correlation, and JSON output.
Supports both local file logging and Cloud Logging export.
"""

import json
import logging
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Request context for correlation across components
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
conversation_id_ctx: ContextVar[str] = ContextVar("conversation_id", default="")

# Default log directory
DEFAULT_LOG_DIR = Path(__file__).parent.parent.parent / "log_files"

# Cloud Logging configuration
ENABLE_CLOUD_LOGGING = os.getenv("CC_ENABLE_CLOUD_LOGGING", "true").lower() == "true"
CLOUD_LOG_NAME = "conversation-coach"

# Initialize Cloud Logging client (lazy)
_cloud_logging_client = None
_cloud_logger = None


def _get_cloud_logger():
    """Get or create Cloud Logging client (lazy initialization)."""
    global _cloud_logging_client, _cloud_logger

    if not ENABLE_CLOUD_LOGGING:
        return None

    if _cloud_logger is not None:
        return _cloud_logger

    try:
        from google.cloud import logging as cloud_logging

        _cloud_logging_client = cloud_logging.Client()
        _cloud_logger = _cloud_logging_client.logger(CLOUD_LOG_NAME)
        return _cloud_logger
    except Exception as e:
        logging.getLogger(__name__).warning(f"Cloud Logging not available: {e}")
        return None


def new_request_context(conversation_id: Optional[str] = None) -> str:
    """Start new request with correlation ID.

    Args:
        conversation_id: Optional conversation ID to associate with this request

    Returns:
        Generated request ID
    """
    request_id = str(uuid.uuid4())[:8]
    request_id_ctx.set(request_id)
    if conversation_id:
        conversation_id_ctx.set(conversation_id)
    return request_id


def get_request_id() -> str:
    """Get current request ID."""
    return request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    """Set current request ID.

    Args:
        request_id: Request ID to set for correlation
    """
    request_id_ctx.set(request_id)


@dataclass
class ComponentResult:
    """Result container for component execution."""

    success: bool = False
    error: Optional[str] = None
    error_type: Optional[str] = None
    data: dict = field(default_factory=dict)

    def __setitem__(self, key: str, value: Any) -> None:
        """Allow dict-like assignment for additional data."""
        self.data[key] = value

    def __getitem__(self, key: str) -> Any:
        """Allow dict-like access."""
        return self.data.get(key)


class ComponentLogger:
    """Structured logging for AI system components.

    Logs component execution with timing, success/failure, and custom metrics.
    Writes to both console (via standard logging) and JSON file.
    """

    def __init__(
        self,
        service: str = "conversation-coach",
        log_dir: Optional[Path] = None,
        enable_file_logging: bool = True,
    ):
        """Initialize the component logger.

        Args:
            service: Service name for log labels
            log_dir: Directory for log files (default: log_files/)
            enable_file_logging: Whether to write to JSON file
        """
        self.service = service
        self.log_dir = log_dir or DEFAULT_LOG_DIR
        self.enable_file_logging = enable_file_logging
        self._component_results: dict[str, dict] = {}
        self._total_cost_usd: float = 0.0

        # Ensure log directory exists
        if self.enable_file_logging:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def component(self, name: str, **context):
        """Log component execution with timing.

        Args:
            name: Component name (e.g., 'data_fetch', 'model_call')
            **context: Additional context to include in log

        Yields:
            ComponentResult object to populate with results
        """
        import time

        start = time.time()
        result = ComponentResult()

        try:
            yield result
            result.success = True
        except Exception as e:
            result.error = str(e)
            result.error_type = type(e).__name__
            raise
        finally:
            duration_ms = int((time.time() - start) * 1000)
            self._log_component(name, duration_ms, result, context)

    def _log_component(
        self,
        component: str,
        duration_ms: int,
        result: ComponentResult,
        context: dict,
    ) -> None:
        """Write structured log entry for component."""
        request_id = request_id_ctx.get()
        conversation_id = conversation_id_ctx.get()

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "conversation_id": conversation_id,
            "severity": "ERROR" if result.error else "INFO",
            "component": component,
            "success": result.success,
            "duration_ms": duration_ms,
        }

        # Add error info if present
        if result.error:
            entry["error"] = result.error
            entry["error_type"] = result.error_type

        # Add component-specific data
        entry.update(result.data)

        # Add any extra context
        entry.update(context)

        # Store for E2E summary
        self._component_results[component] = {
            "success": result.success,
            "duration_ms": duration_ms,
            **result.data,
        }

        # Track cost if present
        if "cost_usd" in result.data:
            self._total_cost_usd += result.data["cost_usd"]

        # Write to file
        self._write_log(entry)

    def log_e2e_result(
        self,
        conversation_id: str,
        success: bool,
        total_duration_ms: int,
        error: Optional[str] = None,
    ) -> None:
        """Log end-to-end coaching result.

        Args:
            conversation_id: Conversation that was coached
            success: Whether coaching completed successfully
            total_duration_ms: Total elapsed time
            error: Error message if failed
        """
        request_id = request_id_ctx.get()

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "conversation_id": conversation_id,
            "severity": "ERROR" if not success else "INFO",
            "component": "e2e",
            "success": success,
            "duration_ms": total_duration_ms,
            "total_cost_usd": self._total_cost_usd,
            "components": self._component_results,
        }

        if error:
            entry["error"] = error

        self._write_log(entry)

        # Reset for next request
        self._component_results = {}
        self._total_cost_usd = 0.0

    def _write_log(self, entry: dict) -> None:
        """Write log entry to JSONL file and Cloud Logging."""
        # Write to local file
        if self.enable_file_logging:
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_file = self.log_dir / f"coach_{date_str}.jsonl"

            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")

        # Write to Cloud Logging
        cloud_logger = _get_cloud_logger()
        if cloud_logger:
            try:
                # Map severity
                severity = entry.get("severity", "INFO")

                # Log structured entry
                cloud_logger.log_struct(
                    entry,
                    severity=severity,
                    labels={
                        "service": self.service,
                        "component": entry.get("component", "unknown"),
                        "request_id": entry.get("request_id", ""),
                    },
                )
            except Exception as e:
                logging.getLogger(__name__).debug(f"Cloud Logging write failed: {e}")

    def get_log_file_path(self, date: Optional[str] = None) -> Path:
        """Get path to log file for a given date.

        Args:
            date: Date string (YYYY-MM-DD), defaults to today

        Returns:
            Path to log file
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"coach_{date}.jsonl"


def read_logs(
    log_dir: Optional[Path] = None,
    date: Optional[str] = None,
    component: Optional[str] = None,
) -> list[dict]:
    """Read log entries from file.

    Args:
        log_dir: Directory containing logs
        date: Date to read (YYYY-MM-DD), defaults to today
        component: Filter to specific component

    Returns:
        List of log entries
    """
    log_dir = log_dir or DEFAULT_LOG_DIR
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    log_file = log_dir / f"coach_{date}.jsonl"

    if not log_file.exists():
        return []

    entries = []
    with open(log_file) as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                if component is None or entry.get("component") == component:
                    entries.append(entry)

    return entries
