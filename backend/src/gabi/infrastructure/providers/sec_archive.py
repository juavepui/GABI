"""Paced streaming of SEC archive files; size and provenance are checked by the download use case."""

import time
from collections.abc import Iterator

import requests

from gabi.infrastructure.jobs.sec_batch import run as parallel  # noqa: F401 - four-worker SEC pool

PAUSE_SECONDS = .15
CHUNK_BYTES = 1024 * 1024


class SecArchiveChunks:
    def __init__(self, user_agent: str):
        self.headers = {"User-Agent": user_agent}

    def chunks(self, url: str) -> Iterator[bytes]:
        time.sleep(PAUSE_SECONDS)
        with requests.get(url, headers=self.headers, timeout=(20, 90), stream=True) as response:
            response.raise_for_status()
            yield from response.iter_content(CHUNK_BYTES)


# Transport failures callers may record per file instead of aborting a batch.
HTTP_ERROR = requests.HTTPError
REQUEST_ERROR = requests.RequestException


def http_status(exc: BaseException) -> int | None:
    """HTTP status of a failed SEC response; None for any other failure."""
    response = exc.response if isinstance(exc, requests.HTTPError) else None
    return response.status_code if response is not None else None
