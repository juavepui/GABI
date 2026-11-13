"""Explicit SEC archive download with immutable URL provenance."""

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Protocol


class ArchiveFiles(Protocol):
    def exists(self, path: str) -> bool: ...
    def write(self, path: str, chunks: Iterable[bytes]) -> None: ...
    def fingerprint(self, path: str) -> tuple[str, int]: ...


class ArchiveProvenance(Protocol):
    def register(self, url: str, digest: str, size: int, fetched_at: str) -> None: ...


def download(url: str, path: str, *, files: ArchiveFiles, provenance: ArchiveProvenance,
             source: Callable[[str], Iterable[bytes]], now: Callable[[], datetime]) -> str:
    if not files.exists(path):
        files.write(path, source(url))
    digest, size = files.fingerprint(path)
    provenance.register(url, digest, size, now().isoformat())
    return path
