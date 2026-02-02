import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """Configure stdlib + structlog for JSON output."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger():
    """Return a structlog logger."""
    return structlog.get_logger()

