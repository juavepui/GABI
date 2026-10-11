"""Paced streaming of SEC archive files; size and provenance are checked by the download use case."""

import time
from collections.abc import Iterator

import requests

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
