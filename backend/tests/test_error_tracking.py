"""Tests for app.error_tracking — shipping errors to Sentry.

Two contracts matter:

* **Off unless configured.** With no ``SENTRY_DSN`` the SDK is never started,
  so local runs and the test suite send nothing anywhere.
* **One event per logged error, grouped by its event name.** Errors reach
  Sentry through a structlog processor, which titles each event with the log
  event name (``api.predictions.compute_error``) and tags it with the
  ``error_id`` the client was shown. That tag is the bridge from a reference a
  user quotes to the stack trace behind it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING

import pytest
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.transport import Transport
import structlog

from app import error_tracking
from app.api import errors
from app.logging_config import setup_logging

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sentry_sdk.envelope import Envelope


class _Recorder:
    """Stands in for ``sentry_sdk`` and remembers what would have been sent."""

    def __init__(self) -> None:
        self.inits: list[dict] = []
        self.exceptions: list[BaseException | None] = []
        self.messages: list[tuple[str, str]] = []
        self.tags: dict[str, object] = {}
        self.contexts: dict[str, dict] = {}

    def init(self, **kwargs) -> None:
        self.inits.append(kwargs)

    def capture_exception(self, error=None) -> None:
        self.exceptions.append(error)

    def capture_message(self, message: str, level: str) -> None:
        self.messages.append((message, level))

    def new_scope(self):
        recorder = self

        class _Scope:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def set_tag(self, key, value):
                recorder.tags[key] = value

            def set_context(self, key, value):
                recorder.contexts[key] = value

        return _Scope()


@pytest.fixture
def sentry(monkeypatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(error_tracking, "sentry_sdk", recorder)
    return recorder


# ---------------------------------------------------------------------------
# init_error_tracking
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("dsn", ["", "   "])
def test_nothing_starts_without_a_dsn(sentry, monkeypatch, dsn):
    monkeypatch.setenv("SENTRY_DSN", dsn)

    assert error_tracking.init_error_tracking() is False
    assert sentry.inits == []


@pytest.mark.unit
def test_a_dsn_starts_the_sdk_without_personal_data(sentry, monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.sentry.io/2")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "4151544")
    monkeypatch.delenv("SENTRY_TRACES_SAMPLE_RATE", raising=False)

    assert error_tracking.init_error_tracking() is True

    (options,) = sentry.inits
    assert options["dsn"] == "https://key@o1.ingest.sentry.io/2"
    assert options["environment"] == "production"
    assert options["release"] == "4151544"
    # Unset on purpose: the SDK's default collects no user data, while a
    # `data_collection` dict would opt into every category it omits.
    assert "send_default_pii" not in options
    assert "data_collection" not in options
    assert options["traces_sample_rate"] == error_tracking.DEFAULT_TRACES_SAMPLE_RATE


@pytest.mark.unit
def test_log_records_are_breadcrumbs_never_events(sentry, monkeypatch):
    """The processor already files each error; the logging hook must not file it again."""
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.sentry.io/2")

    error_tracking.init_error_tracking()

    (logging_integration,) = [
        integration for integration in sentry.inits[0]["integrations"] if isinstance(integration, LoggingIntegration)
    ]
    assert logging_integration._handler is None  # no event handler installed
    assert logging_integration._breadcrumb_handler.level == logging.INFO


@pytest.mark.unit
def test_only_the_named_integrations_are_enabled(sentry, monkeypatch):
    """No auto-enabling: the SDK would import every library it could instrument."""
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.sentry.io/2")

    error_tracking.init_error_tracking()

    (options,) = sentry.inits
    assert options["auto_enabling_integrations"] is False
    assert {type(integration) for integration in options["integrations"]} == {
        StarletteIntegration,
        FastApiIntegration,
        LoggingIntegration,
    }


@pytest.mark.unit
def test_a_missing_release_is_left_for_the_sdk_to_detect(sentry, monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.sentry.io/2")
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)

    error_tracking.init_error_tracking()

    assert sentry.inits[0]["release"] is None


@pytest.mark.unit
@pytest.mark.parametrize(("raw", "expected"), [("0.5", 0.5), ("0", 0.0), ("1", 1.0)])
def test_the_trace_sample_rate_can_be_tuned(sentry, monkeypatch, raw, expected):
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.sentry.io/2")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", raw)

    error_tracking.init_error_tracking()

    assert sentry.inits[0]["traces_sample_rate"] == expected


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["lots", "1.5", "-0.1", "nan"])
def test_a_bad_trace_sample_rate_falls_back_to_the_default(sentry, monkeypatch, raw):
    """A typo in the dashboard must not stop the server from booting."""
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.sentry.io/2")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", raw)

    error_tracking.init_error_tracking()

    assert sentry.inits[0]["traces_sample_rate"] == error_tracking.DEFAULT_TRACES_SAMPLE_RATE


# ---------------------------------------------------------------------------
# report_to_sentry (structlog processor)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("method", ["debug", "info", "warning"])
def test_below_error_nothing_is_sent(sentry, method):
    event = {"event": "race_stints.unavailable", "round": 18}

    assert error_tracking.report_to_sentry(None, method, event) is event
    assert sentry.exceptions == []
    assert sentry.messages == []


@pytest.mark.unit
def test_a_logged_exception_is_sent_with_its_error_id(sentry):
    error = RuntimeError("upstream 503")
    event = {
        "event": "api.predictions.compute_error",
        "error_id": "5655515f8d45",
        "exc_info": error,
        "year": 2026,
        "round": 19,
        "timestamp": "2026-10-30T22:59:32Z",
        "level": "error",
    }

    returned = error_tracking.report_to_sentry(None, "error", event)

    assert returned is event  # the console/JSON log line is still written
    assert sentry.exceptions == [error]
    assert sentry.tags == {"log_event": "api.predictions.compute_error", "error_id": "5655515f8d45"}
    assert sentry.contexts["log"] == {"error_id": "5655515f8d45", "year": 2026, "round": 19}


@pytest.mark.unit
def test_an_error_without_an_exception_is_sent_as_a_message_titled_by_event(sentry):
    """Titled by event name only, so every occurrence groups into one issue."""
    event = {"event": "prediction_cache.load_failed", "error": "connection refused", "timestamp": "t"}

    error_tracking.report_to_sentry(None, "error", event)

    assert sentry.messages == [("prediction_cache.load_failed", "error")]
    assert sentry.exceptions == []
    assert "error_id" not in sentry.tags


@pytest.mark.unit
def test_logger_exception_sends_the_exception_being_handled(sentry):
    """``logger.exception`` passes ``exc_info=True``; the live exception is the one to send."""
    try:
        raise ValueError("no such column: race_data.q3")
    except ValueError as error:
        error_tracking.report_to_sentry(None, "error", {"event": "prefetch.failed", "exc_info": True})
        handled = error

    assert sentry.exceptions == [handled]


@pytest.mark.unit
def test_an_exc_info_tuple_sends_its_exception(sentry):
    error = KeyError("ANT")
    event = {"event": "api.drivers.error", "exc_info": (KeyError, error, None)}

    error_tracking.report_to_sentry(None, "critical", event)

    assert sentry.exceptions == [error]


# ---------------------------------------------------------------------------
# End to end: the real SDK, a capturing transport
# ---------------------------------------------------------------------------


class _CapturingTransport(Transport):
    """Keeps the error events the SDK would have sent, instead of sending them."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.events.extend(item.payload.json for item in envelope.items if item.type == "event")


@pytest.fixture
def live_sentry(monkeypatch) -> Iterator[_CapturingTransport]:
    """The real SDK and the real logging pipeline, with nothing leaving the process."""
    transport = _CapturingTransport()
    real_init = sentry_sdk.init
    monkeypatch.setattr(
        sentry_sdk,
        "init",
        lambda **options: real_init(**options, transport=transport, default_integrations=False),
    )
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.sentry.io/2")
    monkeypatch.setenv("ENVIRONMENT", "production")
    # A fresh proxy: the module's own may already be cached against another config.
    monkeypatch.setattr(errors, "logger", structlog.get_logger("app.api.errors"))

    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    error_tracking.init_error_tracking()
    setup_logging()
    yield transport
    sentry_sdk.get_global_scope().set_client(None)
    structlog.reset_defaults()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


@pytest.mark.integration
def test_a_client_error_reaches_sentry_once_with_its_stack_and_reference(live_sentry):
    def load_qualifying() -> None:
        raise RuntimeError("upstream 503")

    try:
        load_qualifying()
    except RuntimeError as exc:
        payload = errors.client_error("api.predictions.compute_error", exc, year=2026, round=19)
    sentry_sdk.flush()

    (event,) = live_sentry.events
    assert event["tags"]["error_id"] == payload["error_id"]
    assert event["tags"]["log_event"] == "api.predictions.compute_error"
    (exception,) = event["exception"]["values"]
    assert exception["type"] == "RuntimeError"
    assert exception["stacktrace"]["frames"][-1]["function"] == "load_qualifying"
    assert event["contexts"]["log"] == {
        "error_id": payload["error_id"],
        "error": "upstream 503",
        "error_type": "RuntimeError",
        "year": 2026,
        "round": 19,
    }


@pytest.mark.integration
def test_warnings_stay_in_the_logs(live_sentry):
    structlog.get_logger("app.data.race_stints").warning("race_stints.unavailable", round=18)
    sentry_sdk.flush()

    assert live_sentry.events == []


# Imported lazily everywhere else (see ENABLE_LOCAL_MODELS in app/config.py),
# because loading them at boot exhausts the 512 MB Render instance.
_HEAVY_LIBRARIES = ("torch", "transformers", "sentence_transformers", "scipy", "sklearn", "langgraph")

_BOOT_PROBE = textwrap.dedent(
    """
    import sys

    import sentry_sdk
    from sentry_sdk.transport import Transport

    from app import error_tracking


    class _Quiet(Transport):
        def capture_envelope(self, envelope):
            pass


    real_init = sentry_sdk.init
    sentry_sdk.init = lambda **options: real_init(**options, transport=_Quiet())
    assert error_tracking.init_error_tracking()
    print(",".join(name for name in sys.argv[1:] if name in sys.modules))
    """,
)


@pytest.mark.integration
def test_starting_the_sdk_loads_no_heavy_library():
    """Auto-enabled integrations import each library they might instrument to see if
    it is there — torch, transformers, scipy — which took boot memory from 134 MB to
    502 MB. A fresh interpreter, because this one has long since imported them all.
    """
    backend_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(  # noqa: S603 - fixed argv, this interpreter
        [sys.executable, "-c", _BOOT_PROBE, *_HEAVY_LIBRARIES],
        cwd=backend_root,
        env={**os.environ, "SENTRY_DSN": "https://key@o1.ingest.sentry.io/2"},
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )

    assert result.stdout.strip() == ""
