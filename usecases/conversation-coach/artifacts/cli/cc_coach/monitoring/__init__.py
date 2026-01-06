"""Monitoring module for Conversation Coach.

Provides structured logging, metrics aggregation, cost tracking, tracing, and dashboard.
"""

from cc_coach.monitoring.logging import (
    ComponentLogger,
    get_request_id,
    new_request_context,
    request_id_ctx,
)
from cc_coach.monitoring.cost import CostCalculator
from cc_coach.monitoring.metrics import MetricsCollector
from cc_coach.monitoring.tracing import (
    get_tracer,
    setup_tracing,
    shutdown_tracing,
    trace_span,
    get_current_trace_id,
    get_current_span_id,
)

__all__ = [
    "ComponentLogger",
    "CostCalculator",
    "MetricsCollector",
    "get_request_id",
    "new_request_context",
    "request_id_ctx",
    # Tracing
    "get_tracer",
    "setup_tracing",
    "shutdown_tracing",
    "trace_span",
    "get_current_trace_id",
    "get_current_span_id",
]
