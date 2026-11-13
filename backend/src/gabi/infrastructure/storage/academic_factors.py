"""Bounded factor cache snapshots with exact CSV-byte provenance."""

import hashlib
import io
import os
import tempfile
from pathlib import Path

import pandas as pd

from gabi.application.research.academic_factors import FactorSnapshot

LIBRARY_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"


def calculation_sources() -> dict[str, str]:
    root = Path(__file__).parents[2]
    names = ("domain/research/academic_factors.py", "application/research/academic_factors.py")
    return {name: hashlib.sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for name in names}


class FileFactorCache:
    def __init__(self, data_dir: Path, *, max_bytes: int = 2_000_000, max_rows: int = 5000):
        if min(max_bytes, max_rows) <= 0:
            raise ValueError("Invalid factor cache limits")
        self.path = data_dir / "ff_factors.csv"
        self.max_bytes = max_bytes
        self.max_rows = max_rows

    def _snapshot(self, frame: pd.DataFrame, data: bytes) -> FactorSnapshot:
        if len(frame) > self.max_rows:
            raise ValueError("Factor cache row limit exceeded")
        return FactorSnapshot(frame, {"file": "ff_factors.csv", "sha256": hashlib.sha256(data).hexdigest(),
                                      "first_month": None if frame.empty else frame.index.min().date().isoformat(),
                                      "last_month": None if frame.empty else frame.index.max().date().isoformat(), "url": LIBRARY_URL})

    def load_snapshot(self) -> FactorSnapshot | None:
        if not self.path.is_file():
            return None
        with self.path.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            if size > self.max_bytes:
                raise ValueError("Factor cache file limit exceeded")
            data = stream.read(size + 1)
        if len(data) != size:
            raise ValueError("Factor cache changed while reading")
        frame = pd.read_csv(io.BytesIO(data), index_col=0, parse_dates=True, nrows=self.max_rows + 1)
        return self._snapshot(frame, data)

    def save_snapshot(self, frame: pd.DataFrame) -> FactorSnapshot:
        if len(frame) > self.max_rows:
            raise ValueError("Factor cache row limit exceeded")
        # pandas uses os.linesep for its default CSV, exactly as the old path.
        data = frame.to_csv().encode("utf-8")
        if len(data) > self.max_bytes:
            raise ValueError("Factor cache file limit exceeded")
        snapshot = self._snapshot(frame, data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".ff_factors_", suffix=".csv", dir=self.path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return snapshot

    def load(self) -> pd.DataFrame | None:
        snapshot = self.load_snapshot()
        return snapshot.factors if snapshot is not None else None

    def save(self, frame: pd.DataFrame) -> None:
        self.save_snapshot(frame)
