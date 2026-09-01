"""app/utils/logging.py — Structured logging configuration.

Provides a consistent logging setup across the application.
Use get_logger(__name__) in every module.
"""
from __future__ import annotations

import logging
import sys
from typing import Optional

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with a structured formatter.

    Should be called once at application startup.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    global _configured
    if _configured:
        return

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)

    _configured = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a named logger.

    Args:
        name: Usually __name__ of the calling module.

    Returns:
        A configured Logger instance.
    """
    return logging.getLogger(name or __name__)
