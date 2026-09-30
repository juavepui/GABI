"""Bounded, cached access to the already published repository ledger."""

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
