"""Bounded, cached access to the already published repository ledger."""

import csv
import hashlib
import io
import json
import threading
from pathlib import Path

from gabi.application.errors import QueryError


class FilePublishedLedger:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._version: tuple[int, int] | None = None
        self._ledger: dict | None = None

    def read(self) -> dict:
        try:
            stat = self.path.stat()
        except OSError as exc:
            raise QueryError("ledger_unavailable", "No está disponible el registro publicado.", 503) from exc
        if stat.st_size > 2_000_000:
            raise QueryError("ledger_unavailable", "El registro publicado supera el límite de lectura.", 503)
        version = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if version != self._version:
                try:
                    raw = self.path.read_bytes()
                    if len(raw) > 2_000_000:
                        raise ValueError("Published ledger is too large")
                    ledger = json.loads(raw)
                    if ledger.get("scope") != "explicit_published_repository_artifacts_only":
                        raise ValueError("Unexpected ledger scope")
                    if not isinstance(ledger.get("legacy_entries"), list) or not isinstance(
                        ledger.get("additional_observed_records"), list
                    ):
                        raise ValueError("Unexpected ledger shape")
                except (OSError, ValueError, AttributeError) as exc:
                    raise QueryError("ledger_unavailable", "No se puede leer el registro publicado.", 503) from exc
                self._ledger = ledger
                self._version = version
            assert self._ledger is not None
            return self._ledger


MAX_ARTIFACT_BYTES = 5_000_000
MAX_SERIES = 500


class FilePublishedArtifacts:
    """Published JSON/CSV artifacts referenced by the ledger, only under docs/ and checked against its hashes."""

    def __init__(self, root: Path, ledger: FilePublishedLedger):
        self.root, self.ledger = root.resolve(), ledger
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[tuple[int, int], bytes]] = {}

    def _bytes(self, relative: str) -> bytes:
        path = (self.root / relative).resolve()
        if (not relative.startswith("docs/") or ".." in relative.split("/")
                or not path.is_relative_to(self.root / "docs") or path.suffix not in {".json", ".csv"}):
            raise QueryError("artifact_unavailable", "La referencia no apunta a un artefacto publicado.", 404)
        try:
            stat = path.stat()
        except OSError as exc:
            raise QueryError("artifact_unavailable", "El artefacto publicado no está en este checkout.", 404) from exc
        if stat.st_size > MAX_ARTIFACT_BYTES:
            raise QueryError("artifact_unavailable", "El artefacto supera el límite de lectura.", 503)
        version = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._cache.get(relative)
            if cached is None or cached[0] != version:
                cached = (version, path.read_bytes())
                self._cache[relative] = cached
            return cached[1]

    def read(self, ref: str) -> tuple[object, bool | None]:
        """(value at the reference, whether the file matches the ledger hash; None when it lists none)."""
        relative, _, fragment = ref.partition("#")
        raw = self._bytes(relative)
        expected = self.ledger.read().get("sources_sha256_lf", {}).get(relative)
        verified = None if expected is None else hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == expected
        try:
            if relative.endswith(".csv"):
                return self._column(raw, fragment), verified
            value: object = json.loads(raw)
            for part in [segment for segment in fragment.split("/") if segment]:
                part = part.replace("~1", "/").replace("~0", "~")
                value = value[int(part)] if isinstance(value, list) else value[part]  # type: ignore[index]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise QueryError("artifact_unavailable", "La referencia del resultado no se encuentra.", 404) from exc
        return value, verified

    @staticmethod
    def _column(raw: bytes, column: str) -> list[dict]:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
        if not reader.fieldnames or column not in reader.fieldnames:
            raise KeyError(column)
        first = reader.fieldnames[0]
        series = [{"date": row[first], "value": float(row[column]) if row[column] not in ("", None) else None}
                  for row in reader]
        if len(series) > MAX_SERIES:
            raise ValueError("Serie demasiado larga")
        return series
