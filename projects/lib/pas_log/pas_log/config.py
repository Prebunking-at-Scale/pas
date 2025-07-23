import logging
import os
import sys
from typing import Any

import structlog

# from pythonjsonlogger.json import JsonFormatter
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer


def processor_gcp_severity(_: Any, __: Any, events: Any) -> Any:
    """Processor for structlog.
    GCP uses severity instead of log level.
    """
    if level := events.get("level"):
        events["severity"] = level.upper()
    return events


def processor_gcp_message(_: Any, __: Any, events: Any) -> Any:
    """Processor for structlog.
    GCP displays a "message" field, not an "event" field.
    """
    if event := events.get("event"):
        events["message"] = event
        del events["event"]
    return events


def pas_setup_structlog() -> int:
    """Sets up logging and structlog."""

    # get log levels from environment. bit impolite, using _NAME_TO_LEVEL.
    # ROOT_LOG_LEVEL is for the root logger, which libraries like to attach to.
    _root_log_level = os.getenv("ROOT_LOG_LEVEL", "warn").upper()
    ROOT_LOG_LEVEL = logging.getLevelName(_root_log_level)

    # APP_LOG_LEVEL is for our application. The "structlog" logger is used
    # throughout the application, so we don't have to mix logs.
    _app_log_level = os.getenv("APP_LOG_LEVEL", "info").upper()
    APP_LOG_LEVEL = logging.getLevelName(_app_log_level)

    # wrap the root logger in json handling
    handler = logging.StreamHandler(sys.stdout)
    # handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(ROOT_LOG_LEVEL)

    # If we're outputting to a tty, using ConsoleRenderer gives us a prettier print.
    structlog_renderer: JSONRenderer | ConsoleRenderer
    if sys.stdout.isatty():
        structlog_renderer = structlog.dev.ConsoleRenderer(event_key="message")
    else:
        structlog_renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            structlog.processors.UnicodeDecoder(),
            processor_gcp_severity,
            processor_gcp_message,
            structlog_renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(APP_LOG_LEVEL),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return APP_LOG_LEVEL
