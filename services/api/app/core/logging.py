import logging
import sys

import structlog


def configure_logging(level: str = "INFO", json: bool = False) -> None:
    """Structured logging: JSON lines in prod, readable console output in dev."""
    numeric_level = logging.getLevelName(level.upper())
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=numeric_level, stream=sys.stdout, format="%(message)s")
