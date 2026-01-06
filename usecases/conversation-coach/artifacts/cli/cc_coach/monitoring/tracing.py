"""Distributed tracing for Conversation Coach using OpenTelemetry.

Provides tracing with Cloud Trace export, leveraging ADK's built-in
instrumentation plus custom spans for business logic.

Architecture: Direct Export (No Collector)
- Uses OTLP/HTTP to send traces directly to Cloud Trace
- ADK's BatchSpanProcessor handles buffering
- Same code works: Local -> Cloud Run -> ADK Engine
"""

import os
from contextlib import contextmanager
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource

# Environment configuration
ENABLE_TRACING = os.getenv("CC_ENABLE_TRACING", "true").lower() == "true"
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "conversation-coach")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "dev")

# Global tracer instance
_tracer: Optional[trace.Tracer] = None
_provider: Optional[TracerProvider] = None


def setup_tracing(
    service_name: str = SERVICE_NAME,
    enable_cloud_trace: bool = True,
) -> trace.Tracer:
    """Setup OpenTelemetry tracing with Cloud Trace export.

    Works in all environments:
    - Local: Uses service account credentials (GOOGLE_APPLICATION_CREDENTIALS)
    - Cloud Run: Uses default credentials automatically
    - ADK Engine: Uses platform credentials

    Args:
        service_name: Name of the service for trace attribution
        enable_cloud_trace: Whether to export to Cloud Trace

    Returns:
        Configured tracer instance
    """
    global _provider

    if not ENABLE_TRACING:
        # Return no-op tracer
        return trace.get_tracer(service_name)

    # Create resource with service info
    resource = Resource.create({
        "service.name": service_name,
        "service.version": SERVICE_VERSION,
    })

    # Setup provider
    _provider = TracerProvider(resource=resource)

    if enable_cloud_trace:
        try:
            # Use native Cloud Trace exporter (works with service account key)
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            # Get project ID from environment or credentials
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
            if not project_id:
                # Try to get from credentials file
                creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                if creds_file:
                    import json
                    with open(creds_file) as f:
                        creds = json.load(f)
                        project_id = creds.get("project_id")

            exporter = CloudTraceSpanExporter(project_id=project_id)
            _provider.add_span_processor(BatchSpanProcessor(exporter))

            import logging
            logging.getLogger(__name__).info(
                f"Cloud Trace export enabled for project: {project_id}"
            )

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Could not setup Cloud Trace exporter: {e}. "
                "Tracing will work locally but not export to Cloud Trace."
            )

    trace.set_tracer_provider(_provider)
    return trace.get_tracer(service_name)


def get_tracer() -> trace.Tracer:
    """Get or create the global tracer.

    Returns:
        Tracer instance for creating spans
    """
    global _tracer
    if _tracer is None:
        _tracer = setup_tracing()
    return _tracer


def shutdown_tracing():
    """Shutdown tracing and flush any pending spans."""
    global _provider
    if _provider is not None:
        _provider.shutdown()


@contextmanager
def trace_span(
    name: str,
    attributes: Optional[dict] = None,
):
    """Create a traced span with optional attributes.

    Convenience wrapper around tracer.start_as_current_span.

    Args:
        name: Name of the span
        attributes: Optional dict of attributes to set on span

    Yields:
        The span object
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        yield span


def get_current_trace_id() -> Optional[str]:
    """Get the current trace ID as a hex string.

    Returns:
        Trace ID or None if no active span
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, '032x')
    return None


def get_current_span_id() -> Optional[str]:
    """Get the current span ID as a hex string.

    Returns:
        Span ID or None if no active span
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().span_id, '016x')
    return None
