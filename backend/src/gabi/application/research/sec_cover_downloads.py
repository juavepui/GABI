"""Bounded, paced and resumable download of selected SEC XBRL covers."""

import threading
from collections.abc import Callable, Iterable

from gabi.domain.research.sec_bulk import instance_url

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class Pacer:
    """One start schedule shared by every worker: at most one request per interval, retries included."""

    def __init__(self, interval: float, *, clock: Callable[[], float], wait: Callable[[float], None]):
        self.interval, self.clock, self.wait = interval, clock, wait
        self._lock = threading.Lock()
        self._next = clock()

    def __call__(self) -> None:
        with self._lock:
            now = self.clock()
            delay = max(0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            self.wait(delay)


def pending_covers(selected: dict[str, tuple], limit: int, *,
                   cached: Callable[[str], bool]) -> tuple[int, list[tuple[str, str]]]:
    """Covers already cached and up to ``limit`` (accession, url) still missing, oldest filing first."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    already_cached = 0
    pending: list[tuple[str, str]] = []
    for accn, cik, _filed, instance in sorted(selected.values(), key=lambda row: (row[2], row[0])):
        if cached(accn):
            already_cached += 1
            continue
        if len(pending) < limit:
            pending.append((accn, instance_url(cik, accn, instance)))
    return already_cached, pending


class CoverFailure(Exception):
    """A cover that could not be fetched; counted and logged, never fatal for the batch."""


Parallel = Callable[[list[tuple[str, str]], Callable[[str, str], None]], Iterable[tuple[str, Exception | None]]]


def download_covers(pending: list[tuple[str, str]], *, download: Callable[[str, str], object],
                    errors: tuple[type[BaseException], ...], status: Callable[[BaseException], int | None],
                    parallel: Parallel, clock: Callable[[], float], wait: Callable[[float], None],
                    log: Callable[[str], None], interval: float = 0.25, attempts: int = 3) -> dict:
    """Download each pending cover; transient SEC statuses are retried, other listed failures are counted."""
    pace = Pacer(interval, clock=clock, wait=wait)

    def fetch_one(accn: str, url: str) -> None:
        for attempt in range(attempts):
            try:
                pace()
                download(url, accn)
                return
            except errors as exc:
                if status(exc) in RETRY_STATUSES and attempt < attempts - 1:
                    wait(2 ** attempt)
                    continue
                raise CoverFailure(str(exc)) from exc
        raise CoverFailure("retries exhausted")

    fetched = failures = 0
    for accn, error in parallel(pending, fetch_one):
        if isinstance(error, CoverFailure):
            failures += 1
            log(f"SEC identity download failed {accn}: {error}")
        elif error is not None:
            raise error
        else:
            fetched += 1
        if (fetched + failures) % 50 == 0:
            log(f"SEC identity covers attempted: {fetched + failures}")
    return {"fetched": fetched, "failed": failures}
