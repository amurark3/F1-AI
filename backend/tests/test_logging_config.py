"""A logged traceback never prints local variables (they can hold a database URL or a key)."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
LOCAL_VALUE = "hunter2-db-password"

# Runs in a fresh interpreter, so structlog's configuration starts from its defaults.
PROGRAM = """
import structlog
{setup}

def connect():
    password = "{secret}"
    raise RuntimeError("could not connect")

try:
    connect()
except RuntimeError:
    structlog.get_logger().exception("connect.failed")
"""


@pytest.mark.parametrize(
    "setup",
    [
        # A script: imports the app and never calls setup_logging.
        "import app.data.store",
        # The local dev server.
        "from app.logging_config import setup_logging; setup_logging()",
    ],
    ids=["script", "dev-server"],
)
def test_a_logged_traceback_shows_the_error_but_no_local_values(setup: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed argv, this interpreter
        [sys.executable, "-c", PROGRAM.format(setup=setup, secret=LOCAL_VALUE)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
        env={"ENVIRONMENT": "development", "PATH": ""},
    )
    output = result.stdout + result.stderr

    assert "RuntimeError: could not connect" in output
    assert LOCAL_VALUE not in output
