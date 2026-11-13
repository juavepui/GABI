"""Raw Tiingo snapshots: hash first, decode only when application requests it."""

import hashlib
import io
import os
import re
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from gabi.application.research.tiingo_prices import RawSnapshot
from gabi.domain.research.tiingo_prices import current_listings


class FileTiingoCache:
    def __init__(self, directory: Path, *, max_bytes: int = 8_000_000,
                 max_total_bytes: int = 512_000_000, max_files: int = 1000):
        if min(max_bytes, max_total_bytes, max_files) <= 0:
            raise ValueError("Invalid Tiingo cache limits")
        self.directory, self.max_bytes = directory, max_bytes
        self.max_total_bytes, self.max_files = max_total_bytes, max_files

    def _path(self, symbol: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_^.-]{1,32}", symbol) or symbol in {".", ".."}:
            raise ValueError("Invalid Tiingo cache symbol")
        path = self.directory / f"{symbol}.json"
        if path.resolve().parent != self.directory.resolve():
            raise ValueError("Tiingo cache file escapes directory")
        return path

    def ensure_directory(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def contains(self, symbol: str) -> bool:
        return self._path(symbol).exists()

    def save(self, symbol: str, body: bytes) -> None:
        path = self._path(symbol)
        if len(body) > self.max_bytes:
            raise ValueError("Tiingo cache byte limit exceeded")
        self.ensure_directory()
        descriptor, name = tempfile.mkstemp(prefix=".tiingo_", suffix=".tmp", dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def snapshots(self) -> Iterator[RawSnapshot]:
        files = []
        for path in self.directory.glob("*.json"):
            files.append(path)
            if len(files) > self.max_files:
                raise ValueError("Tiingo cache file count limit exceeded")
        total = 0
        for path in sorted(files):
            path = self._path(path.stem)
            with path.open("rb") as stream:
                size = os.fstat(stream.fileno()).st_size
                total += size
                if size > self.max_bytes or total > self.max_total_bytes:
                    raise ValueError("Tiingo cache byte limit exceeded")
                body = stream.read(size + 1)
            if len(body) != size:
                raise ValueError("Tiingo cache changed while reading")
            yield RawSnapshot(path.stem, body, hashlib.sha256(body).hexdigest())
            del body


def tiingo_key(data_dir: Path) -> str | None:
    key = os.environ.get("TIINGO_API_KEY", "").strip()
    if key:
        return key
    path = data_dir / "tiingo_api_key.txt"
    if not path.exists():
        return None
    with path.open("rb") as stream:
        data = stream.read(4097)
    if len(data) > 4096:
        raise ValueError("Tiingo key file limit exceeded")
    return data.decode("utf8").strip() or None


def read_current_listings(path: Path, *, max_bytes: int = 16_000_000, max_csv_bytes: int = 64_000_000,
                          max_rows: int = 200_000) -> pd.DataFrame:
    with path.open("rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        if size > max_bytes:
            raise ValueError("Tiingo listing ZIP byte limit exceeded")
        data = stream.read(size + 1)
    if len(data) != size:
        raise ValueError("Tiingo listing ZIP changed while reading")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        info = archive.getinfo("supported_tickers.csv")
        if info.file_size > max_csv_bytes:
            raise ValueError("Tiingo listing CSV byte limit exceeded")
        with archive.open(info) as source:
            frame = pd.read_csv(source, nrows=max_rows + 1)
    if len(frame) > max_rows:
        raise ValueError("Tiingo listing row limit exceeded")
    return current_listings(frame)
