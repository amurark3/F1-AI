"""
Structured Logging Configuration
=================================
Provides ``setup_logging()`` which configures structlog for the entire
application.  Call once during server startup (in ``main.py`` lifespan).

Modes
-----
- **Development** (``ENVIRONMENT != "production"``): Pretty, colored console
  output via ``ConsoleRenderer`` for easy local debugging.
- **Production** (``ENVIRONMENT == "production"``): Machine-parseable JSON
  lines via ``JSONRenderer`` for log aggregation services.

Third-party library noise (httpx, chromadb, sentence_transformers) is
silenced to WARNING level so application logs stay readable.
"""

import os
import logging
import structlog


def setup_logging() -> None:
    """Configure structlog and stdlib logging for the application."""

    env = os.getenv("ENVIRONMENT", "development").lower()
    is_production = env == "production"

    # Shared processors applied to every log event
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_production:
        # JSON lines for machine parsing
        renderer = structlog.processors.JSONRenderer()
    else:
        # Pretty colored console output for local development
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            # Prepare event dict for stdlib or structlog rendering
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib logging through structlog so third-party library logs
    # are also formatted consistently.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Silence noisy third-party libraries
    for noisy_lib in ("httpx", "chromadb", "sentence_transformers", "httpcore"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)
