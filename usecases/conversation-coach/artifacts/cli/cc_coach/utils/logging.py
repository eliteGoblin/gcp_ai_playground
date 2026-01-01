"""Logging configuration for Conversation Coach CLI."""

import logging
import sys

from rich.console import Console
from rich.logging import RichHandler


def setup_logging(level: str = "INFO") -> None:
    """
    Configure logging with rich output.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    console = Console(stderr=True)

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                tracebacks_show_locals=True,
            )
        ],
    )

    # Reduce noise from Google Cloud libraries
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
