"""Error tracking — ship errors to Sentry when ``SENTRY_DSN`` is set.

Off by default: with no DSN the SDK never starts, so local runs and the test
suite send nothing anywhere.

Errors reach Sentry through :func:`report_to_sentry`, a structlog processor,
rather than through the SDK's logging hook. structlog hands stdlib a record
whose message is the whole rendered event dict, timestamp included, so the hook
would title every occurrence differently and nothing would ever group. The
processor titles each event with the log event name instead
(``api.predictions.compute_error``) and tags it with the ``error_id`` the client
was shown — the bridge from a reference a user quotes to the stack trace behind
it. Log records still ride along as breadcrumbs, so an issue shows what the
server was doing just before it failed.
"""

from __future__ import annotations

import logging
import math
import os
import sys
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
import structlog

logger = structlog.get_logger()

DEFAULT_TRACES_SAMPLE_RATE = 0.1

_ERROR_METHODS = frozenset({"error", "exception", "critical"})

# Added by structlog to every event; carried by Sentry's own fields already.
_BOOKKEEPING_KEYS = frozenset({"event", "exc_info", "level", "logger", "timestamp"})


def init_error_tracking() -> bool:
    """Start the Sentry SDK if ``SENTRY_DSN`` is set. Returns whether it started."""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("ENVIRONMENT", "development"),
        # Render sets this to the deployed commit; elsewhere the SDK detects it.
        release=os.getenv("RENDER_GIT_COMMIT") or None,
        traces_sample_rate=_traces_sample_rate(),
        # No `send_default_pii` (deprecated) and no `data_collection`: leaving
        # both unset keeps the SDK's conservative default of no user data,
        # whereas passing a `data_collection` dict opts into collecting every
        # category it does not name.
        #
        # Only the integrations named here. Left on, auto-enabling imports every
        # library the SDK could instrument just to see whether it is installed —
        # torch, transformers, scipy, langgraph — which took boot memory from
        # 134 MB to 502 MB, past the 512 MB Render instance, and undid the lazy
        # imports that keep it small (see ENABLE_LOCAL_MODELS in app/config.py).
        auto_enabling_integrations=False,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=None),
        ],
    )
    return True


def _traces_sample_rate() -> float:
    """``SENTRY_TRACES_SAMPLE_RATE`` as a fraction in [0, 1], else the default.

    A typo in the dashboard must not stop the server from booting, so a bad
    value is logged and replaced rather than raised.
    """
    raw = os.getenv("SENTRY_TRACES_SAMPLE_RATE")
    if raw is None:
        return DEFAULT_TRACES_SAMPLE_RATE
    try:
        rate = float(raw)
    except ValueError:
        rate = math.nan
    if not 0.0 <= rate <= 1.0:
        logger.warning("error_tracking.bad_sample_rate", value=raw, using=DEFAULT_TRACES_SAMPLE_RATE)
        return DEFAULT_TRACES_SAMPLE_RATE
    return rate


def report_to_sentry(_logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: send each error-level event to Sentry.

    Returns the event unchanged, so the log line is still written. A no-op until
    :func:`init_error_tracking` has started the SDK.
    """
    if method_name not in _ERROR_METHODS:
        return event_dict

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("log_event", event_dict.get("event"))
        if "error_id" in event_dict:
            scope.set_tag("error_id", event_dict["error_id"])
        scope.set_context("log", {key: value for key, value in event_dict.items() if key not in _BOOKKEEPING_KEYS})

        error = _exception_of(event_dict.get("exc_info"))
        if error is None:
            sentry_sdk.capture_message(str(event_dict.get("event")), level="error")
        else:
            sentry_sdk.capture_exception(error)
    return event_dict


def _exception_of(exc_info: object) -> BaseException | None:
    """The exception behind structlog's ``exc_info``: an instance, ``True`` or a tuple."""
    if isinstance(exc_info, BaseException):
        return exc_info
    if exc_info is True:
        return sys.exc_info()[1]
    if isinstance(exc_info, tuple) and len(exc_info) == 3:
        return exc_info[1]
    return None
