"""One way to ask OpenF1 for rows, shared by every module that reads it.

OpenF1 answers in ways that look like failures but are not, and the other way
round, so each caller used to carry its own reading of them:

* ``404 {"detail": "No results found."}`` is an empty answer, not an outage.
* ``429`` comes after a burst of about twenty requests. The request is retried
  after the wait OpenF1 advertises, within bounds, because this runs on a worker
  thread that a page is waiting on.
* ``401`` means an F1 session is live somewhere. While one is, OpenF1 refuses
  every unauthenticated request, past sessions included, so it is reported as
  its own error: the page can say "try after the session" instead of "broken".

Requests are also paced across the whole process: two pages opening at once
would otherwise burst past the rate limit together.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import httpx

from app.config import OPENF1_HTTP_TIMEOUT_SECONDS, OPENF1_MIN_REQUEST_GAP_SECONDS

if TYPE_CHECKING:
    from collections.abc import Callable

OPENF1_BASE = "https://api.openf1.org/v1"

# A rate-limited request is tried this many times, waiting what OpenF1 asks for
# between attempts, within bounds.
RATE_LIMIT_ATTEMPTS = 3
DEFAULT_RETRY_AFTER_SECONDS = 2.0
MAX_RETRY_AFTER_SECONDS = 10.0


class OpenF1UnavailableError(RuntimeError):
    """OpenF1 gave no usable answer: unreachable, rate limited, or closed for a live session."""


class OpenF1LiveLockoutError(OpenF1UnavailableError):
    """OpenF1 is closed to clients without an account while an F1 session is live."""


class RequestPacer:
    """Spaces the starts of requests at least ``gap`` seconds apart.

    The lock guards the schedule, not the request: a caller books the next free
    start time, releases the lock and sleeps until then, so slow responses never
    hold anyone else up.
    """

    def __init__(
        self,
        gap: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._gap = gap
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_start = 0.0

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            start = max(now, self._next_start)
            self._next_start = start + self._gap
        if start > now:
            self._sleep(start - now)


PACER = RequestPacer(OPENF1_MIN_REQUEST_GAP_SECONDS)


def new_client() -> httpx.Client:
    return httpx.Client(timeout=OPENF1_HTTP_TIMEOUT_SECONDS)


def retry_after(response: httpx.Response) -> float:
    try:
        wait = float(response.headers.get("retry-after", DEFAULT_RETRY_AFTER_SECONDS))
    except ValueError:
        wait = DEFAULT_RETRY_AFTER_SECONDS
    return min(max(wait, 0.0), MAX_RETRY_AFTER_SECONDS)


def _rows(response: httpx.Response, path: str) -> list[dict]:
    if response.status_code == httpx.codes.NOT_FOUND:
        return []
    if response.status_code == httpx.codes.UNAUTHORIZED:
        raise OpenF1LiveLockoutError(f"{path}: closed while an F1 session is live")
    if response.status_code != httpx.codes.OK:
        raise OpenF1UnavailableError(f"{path}: HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise OpenF1UnavailableError(f"{path}: not JSON") from exc
    if not isinstance(payload, list):
        raise OpenF1UnavailableError(f"{path}: {str(payload)[:120]}")
    return payload


def get_json(client: httpx.Client, path: str, params: dict) -> list[dict]:
    """The rows OpenF1 holds for a query; empty when the query matches nothing."""
    for _attempt in range(RATE_LIMIT_ATTEMPTS):
        PACER.wait()
        try:
            response = client.get(f"{OPENF1_BASE}/{path}", params=params)
        except httpx.HTTPError as exc:
            raise OpenF1UnavailableError(f"{path}: {exc}") from exc
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            time.sleep(retry_after(response))
            continue
        return _rows(response, path)
    raise OpenF1UnavailableError(f"{path}: rate limited")
