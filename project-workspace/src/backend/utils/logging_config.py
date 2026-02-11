"""Logging Configuration for WSB Analysis Tool

This module provides centralized logging configuration using structlog with JSON output.
Supports the 4-tier error handling strategy by capturing DEBUG through CRITICAL levels
with full stack traces for errors.

Usage:
    >>> from backend.utils.logging_config import setup_logging
    >>> setup_logging()
    >>> import structlog
    >>> logger = structlog.get_logger()
    >>> logger.info("analysis_started", run_id=123, phase="acquisition")
    >>> logger.error("api_call_failed", exc_info=True, ticker="AAPL")
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Any, Dict

import structlog


def setup_logging(log_dir: str = "logs", log_filename: str = "backend.log") -> None:
    """Configure structlog with JSON renderer and file output.

    Sets up both Python stdlib logging and structlog to write JSON-formatted
    log entries to logs/backend.log. Creates the logs directory if it doesn't exist.

    Args:
        log_dir: Directory for log files, relative to current working directory (default: "logs")
        log_filename: Name of the log file (default: "backend.log")

    Log entry format (JSON):
        {
            "event": "message text",
            "level": "info|debug|warning|error|critical",
            "timestamp": "2026-02-10T12:34:56.789Z",
            "logger": "module.name",
            ...additional context fields...
        }

    For ERROR and CRITICAL levels with active exceptions:
        {
            "event": "message text",
            "level": "error",
            "timestamp": "2026-02-10T12:34:56.789Z",
            "exception": "Full traceback...",
            ...
        }

    Example:
        >>> setup_logging()
        >>> logger = structlog.get_logger(__name__)
        >>> logger.info("server_started", port=8000, host="localhost")
        >>> try:
        ...     risky_operation()
        ... except Exception:
        ...     logger.error("operation_failed", exc_info=True, operation="risky")
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Full path to log file
    log_file = log_path / log_filename

    # Shared processors for structlog
    shared_processors = [
        # Add log level to event dict
        structlog.stdlib.add_log_level,
        # Add logger name
        structlog.stdlib.add_logger_name,
        # Add timestamp in ISO 8601 format (UTC)
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Add exception info for ERROR/CRITICAL when exc_info=True
        structlog.processors.format_exc_info,
        # Render stack info if present
        structlog.processors.StackInfoRenderer(),
    ]

    # Configure structlog to pass to stdlib logging
    structlog.configure(
        processors=shared_processors + [
            # Pass to stdlib logging
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        # Use stdlib logger as the final destination
        logger_factory=structlog.stdlib.LoggerFactory(),
        # Wrapper class for compatibility with stdlib logging
        wrapper_class=structlog.stdlib.BoundLogger,
        # Cache loggers for performance
        cache_logger_on_first_use=True,
    )

    # Configure Python stdlib logging with structlog's ProcessorFormatter
    # This formatter applies the final JSON rendering
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    # File handler for logs/backend.log
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Optional: Also log to console for development visibility
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()  # Clear any existing handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def get_logger(name: str = None):
    """Get a configured structlog logger instance.

    Convenience wrapper around structlog.get_logger() for consistent usage.

    Args:
        name: Logger name (typically __name__). If None, returns root logger.

    Returns:
        Configured structlog logger ready for use (BoundLoggerLazyProxy)

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("task_started", task_id="task-001-001-01")
    """
    return structlog.get_logger(name)
