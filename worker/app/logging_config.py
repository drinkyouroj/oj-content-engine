"""
Centralized logging configuration for the OJ Content Engine worker.

Produces structured JSON logs so journalctl and log aggregators can parse
every line. Each log entry includes timestamp, level, logger name, message,
and any extra fields passed via the ``extra`` kwarg.

Call ``setup_logging()`` once at process startup — before any other imports
that create loggers.

Environment variables:
    LOG_LEVEL  — root log level (default: INFO). Accepts DEBUG, INFO,
                 WARNING, ERROR, CRITICAL.
    LOG_FORMAT — "json" (default) or "text" for human-readable dev output.
"""

from __future__ import annotations

import logging
import os
import sys

from pythonjsonlogger.json import JsonFormatter


#: Fields included in every JSON log line
_JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

#: Human-readable format for local development
_TEXT_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s — %(message)s"

#: Date format matching ISO-8601 for journalctl compatibility
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging() -> None:
    """Configure the root logger with structured JSON output.

    Reads LOG_LEVEL and LOG_FORMAT from environment. Safe to call multiple
    times — clears existing handlers before adding new ones.

    Typical usage::

        from worker.app.logging_config import setup_logging
        setup_logging()
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = os.environ.get("LOG_FORMAT", "json").lower()

    root = logging.getLogger()
    root.setLevel(level)

    # Clear any existing handlers (safe for re-entry)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if log_format == "text":
        formatter = logging.Formatter(_TEXT_FORMAT, datefmt=_DATE_FORMAT)
    else:
        formatter = JsonFormatter(
            _JSON_FORMAT,
            datefmt=_DATE_FORMAT,
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )

    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("arq.worker").setLevel(max(level, logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
