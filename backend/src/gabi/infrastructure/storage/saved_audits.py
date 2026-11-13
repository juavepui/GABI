"""Published Research Lab audits from `docs/`, verified once per file change and cached in memory."""

import threading
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from gabi.application.errors import QueryError
from gabi.infrastructure.legacy import saved_audits as legacy

MAX_FILE_BYTES = 8_000_000
MAX_TOTAL_BYTES = 24_000_000
BOOTSTRAP_DATASETS = ("v2_daily_net", "v1_quarterly_net", "cross_section_means")
DOWNLOADS = {
    "overfitting-audit": ("returns.csv", "audit.json"),
    "factor-benchmark": ("expanding-curves.csv", "in_sample-curves.csv", "audit.json"),
    "factor-stability": ("coefficients.csv", "audit.json"),
    "block-bootstrap": tuple(f"{name}-distributions.csv" for name in BOOTSTRAP_DATASETS) + ("resultado.json",),
}


def _overfitting(directory: Path) -> dict:
    report, _ = legacy.load_overfitting(directory)  # Also verifies the matrix against its fingerprint.
    return report


def _block_bootstrap(directory: Path) -> dict:
    result = legacy.load_block_bootstrap(directory)  # Verifies every distribution file's SHA-256.
    frames = {name: pd.read_csv(directory / f"{name}-distributions.csv", float_precision="round_trip")
              for name in result["datasets"]}
    return {"result": result, "distributions": frames}


def _rank_stability(directory: Path) -> dict:
    result = legacy.load_rank_stability(directory)
    companies = pd.read_csv(directory / "companies.csv", float_precision="round_trip")
    return {"result": result, "companies": {date: frame.drop(columns="date")
                                            for date, frame in companies.groupby("date", sort=False)}}


# Directory, the file whose presence publishes the audit, and its verified reader.
AUDITS: dict[str, tuple[str, Callable[[Path], dict]]] = {
    "overfitting-audit": ("audit.json", _overfitting),
    "factor-benchmark": ("audit.json", legacy.load_factor_benchmark),
    "factor-stability": ("audit.json", legacy.load_factor_stability),
    "block-bootstrap": ("resultado.json", _block_bootstrap),
    "rank-stability": ("resultado.json", _rank_stability),
}


class FileSavedAudits:
    """Hashes are verified by the legacy readers only when a file's identity, size or times change."""

    def __init__(self, root: Path):
        self.docs = root / "docs"
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[tuple, dict]] = {}

    @staticmethod
    def _stamp(directory: Path) -> tuple:
        stamps, total = [], 0
        for path in sorted(item for item in directory.iterdir() if item.is_file()):
            stat = path.stat()
            if stat.st_size > MAX_FILE_BYTES:
                raise ValueError(f"El artefacto {path.name} supera el límite de lectura.")
            total += stat.st_size
            stamps.append((path.name, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        if total > MAX_TOTAL_BYTES:
            raise ValueError("La auditoría supera el límite de lectura.")
        return tuple(stamps)

    def load(self, name: str) -> dict | None:
        """None when the audit has not been published in this checkout, as Streamlit hid the section."""
        marker, reader = AUDITS[name]
        directory = self.docs / name
        if not (directory / marker).is_file():
            return None
        try:
            with self._lock:
                stamp = self._stamp(directory)
                cached = self._cache.get(name)
                if cached is None or cached[0] != stamp:
                    self._cache[name] = (stamp, reader(directory))
                    # A change during verification is caught by the next stamp comparison.
                return self._cache[name][1]
        except (OSError, ValueError, KeyError) as exc:
            self._cache.pop(name, None)
            raise QueryError("saved_audit_invalid", f"No se puede verificar la auditoría guardada: {exc}", 503) from exc

    def download(self, name: str, filename: str) -> bytes:
        if filename not in DOWNLOADS.get(name, ()):
            raise QueryError("download_not_found", "Esta descarga no existe.", 404)
        if self.load(name) is None or not (self.docs / name / filename).is_file():
            raise QueryError("download_not_found", "Esta descarga no existe.", 404)
        contents = (self.docs / name / filename).read_bytes()
        with self._lock:
            cached = self._cache.get(name)
            if cached is None or cached[0] != self._stamp(self.docs / name):
                raise QueryError("saved_audit_changed", "La auditoría ha cambiado durante la descarga.", 409)
        return contents
