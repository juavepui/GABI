"""Bounded, atomic WIKI files with fingerprints of the actual decoded bytes."""

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

from gabi.application.research.wiki_prices import CachedResponse


class FileWikiCache:
    def __init__(self, directory: Path, *, max_bytes: int = 8_000_000, max_total_bytes: int = 512_000_000,
                 max_files: int = 1000, max_rows: int = 5000):
        if min(max_bytes, max_total_bytes, max_files, max_rows) <= 0:
            raise ValueError("Invalid WIKI cache limits")
        self.directory = directory
        self.max_bytes, self.max_total_bytes = max_bytes, max_total_bytes
        self.max_files, self.max_rows = max_files, max_rows

    def _path(self, symbol: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_^.-]{1,32}", symbol) or symbol in {".", ".."}:
            raise ValueError("Invalid WIKI cache symbol")
        path = self.directory / f"{symbol}.json"
        if path.resolve().parent != self.directory.resolve():
            raise ValueError("WIKI cache file escapes directory")
        return path

    def ensure_directory(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def contains(self, symbol: str) -> bool:
        return self._path(symbol).exists()

    def save(self, symbol: str, payload: dict) -> None:
        path = self._path(symbol)
        if len(payload["data"]) > self.max_rows:
            raise ValueError("WIKI cache row limit exceeded")
        # Exactly the original JSON columns/data representation; no URL/key/meta.
        data = json.dumps({"columns": payload["columns"], "data": payload["data"]}).encode("utf8")
        if len(data) > self.max_bytes:
            raise ValueError("WIKI cache byte limit exceeded")
        self.ensure_directory()
        descriptor, name = tempfile.mkstemp(prefix=".wiki_", suffix=".tmp", dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def records(self) -> Iterator[CachedResponse]:
        files = []
        for path in self.directory.glob("*.json"):
            files.append(path)
            if len(files) > self.max_files:
                raise ValueError("WIKI cache file count limit exceeded")
        total = 0
        for path in sorted(files):
            path = self._path(path.stem)
            with path.open("rb") as stream:
                size = os.fstat(stream.fileno()).st_size
                total += size
                if size > self.max_bytes or total > self.max_total_bytes:
                    raise ValueError("WIKI cache byte limit exceeded")
                data = stream.read(size + 1)
            if len(data) != size:
                raise ValueError("WIKI cache changed while reading")
            payload = json.loads(data.decode("utf8"))
            if len(payload["data"]) > self.max_rows:
                raise ValueError("WIKI cache row limit exceeded")
            yield CachedResponse(path.stem, payload, hashlib.sha256(data).hexdigest())


def nasdaq_key(data_dir: Path) -> str | None:
    key = os.environ.get("NASDAQ_DATA_LINK_API_KEY", "").strip()
    if key:
        return key
    path = data_dir / "nasdaq_data_link_api_key.txt"
    if not path.exists():
        return None
    with path.open("rb") as stream:
        data = stream.read(4097)
    if len(data) > 4096:
        raise ValueError("Nasdaq key file limit exceeded")
    return data.decode("utf8").strip() or None
