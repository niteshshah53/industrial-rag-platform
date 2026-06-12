"""
Logging configuration for the Industrial RAG Platform.

Provides two formatters:
  - JSONFormatter   — structured JSON output for production / log aggregation
  - ColoredFormatter — human-readable coloured output for local development

Usage:
    from app.core.logging import configure_logging, get_logger

    # Called once at application startup (in main.py lifespan)
    configure_logging()

    # Use in any module
    logger = get_logger(__name__)
    logger.info("Processing document", extra={"document_id": doc_id, "request_id": req_id})

All extra keyword arguments passed to log methods (request_id, document_id,
latency_ms, etc.) are included in the JSON output automatically.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Attributes that are part of the standard LogRecord and should not be
# re-emitted as extra fields in the JSON output.
_STANDARD_LOG_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Every log entry includes a standard set of fields plus any extras
    passed via the `extra` parameter. This format is suitable for
    ingestion by log aggregation systems (e.g. Datadog, Loki, CloudWatch).

    Example output:
        {
            "timestamp": "2026-06-12T14:32:01.234Z",
            "level": "INFO",
            "service": "industrial-rag",
            "logger": "app.services.ingestion_service",
            "location": "ingestion_service:87",
            "message": "Document ingestion complete",
            "document_id": "a3f2b1c0",
            "chunk_count": 42,
            "duration_ms": 1840
        }
    """

    SERVICE_NAME = "industrial-rag"

    def format(self, record: logging.LogRecord) -> str:
        # Ensure message is rendered (handles % formatting in log calls)
        record.message = record.getMessage()

        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": self.SERVICE_NAME,
            "logger": record.name,
            "location": f"{record.module}:{record.lineno}",
            "message": record.message,
        }

        # Append any extra fields (request_id, document_id, latency_ms, etc.)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_ATTRS and not key.startswith("_"):
                log_entry[key] = value

        # Append formatted exception if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class ColoredFormatter(logging.Formatter):
    """
    Human-readable formatter with ANSI colour coding for local development.

    Colours by level:
      DEBUG    → Cyan
      INFO     → Green
      WARNING  → Yellow
      ERROR    → Red
      CRITICAL → Magenta (bold)
    """

    _LEVEL_COLORS: dict[str, str] = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[1;35m",
    }
    _RESET = "\033[0m"
    _DIM = "\033[2m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._LEVEL_COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname:<8}{self._RESET}"
        record.name = f"{self._DIM}{record.name}{self._RESET}"
        return super().format(record)


def configure_logging(settings: Any = None) -> None:
    """
    Configure the root logger based on application settings.

    Must be called once during application startup. Subsequent calls are
    safe but will replace existing handlers.

    Args:
        settings: A Settings instance. If None, reads from get_settings().
    """
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level, logging.INFO))

    # Replace any existing handlers to avoid duplicate log output when
    # configure_logging is called multiple times (e.g. during testing).
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if settings.log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            ColoredFormatter(
                fmt="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers that produce excessive output
    # at INFO level when processing requests.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("qdrant_client").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.

    Args:
        name: Typically __name__ from the calling module.

    Returns:
        A standard Python Logger instance. All extra fields passed to
        log methods are included in JSON output automatically.

    Example:
        logger = get_logger(__name__)
        logger.info("Retrieval complete", extra={
            "request_id": req_id,
            "retrieved_count": 5,
            "filtered_count": 3,
            "top_score": 0.812,
        })
    """
    return logging.getLogger(name)
