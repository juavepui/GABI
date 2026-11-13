"""The one process-wide pacer and the bounded retry of transient source failures.

Legacy facades and the bootstrap bridges all retry through here, so SEC's four threads cannot each
burst independently. Never checkpoints: the attempt records the outcome.
"""

import threading
import time

import requests

from gabi.application.administration.sync_events import retry as retry_use_case
from gabi.domain.market.source_errors import RETRYABLE_CATEGORIES, classify

_PACE_LOCK = threading.Lock()
_NEXT_REQUEST: dict[str, float] = {}


def _pace(source: str, seconds: float) -> None:
    with _PACE_LOCK:
        now = time.perf_counter()
        delay = max(0., _NEXT_REQUEST.get(source, now) - now)
        _NEXT_REQUEST[source] = now + delay + seconds
    if delay:
        time.sleep(delay)


def transient(exc: Exception) -> bool:
    category, _ = classify(str(exc))
    response = getattr(exc, "response", None)
    return (category in RETRYABLE_CATEGORIES or isinstance(exc, (requests.Timeout, requests.ConnectionError))
            or (response is not None and response.status_code >= 500))


def retry_after(exc: Exception) -> tuple[bool, object]:
    response = getattr(exc, "response", None)
    return (False, None) if response is None else (True, response.headers.get("Retry-After"))


def retry(call, attempt, *, attempts: int = 3, pace: float = .25):
    """Bounded retry; only transient network/rate failures."""
    return retry_use_case(call, attempt, transient=transient, retry_after=retry_after,
                          pace=lambda source, seconds: _pace(source, seconds),
                          sleep=lambda seconds: time.sleep(seconds), attempts=attempts, pace_seconds=pace)

