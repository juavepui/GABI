"""Bounded, versioned reads of pinned evidence from an explicit repository root."""
import hashlib
import threading
from copy import deepcopy
from pathlib import Path

from gabi.application.research.evidence_catalog import load_catalog
from gabi.domain.research import evidence_catalog as rules
from gabi.infrastructure.storage.published_factors import FilePublishedFactors


class FileEvidenceCatalog:
    def __init__(self, root: Path):
        self.root = root
        self.published = FilePublishedFactors(root)
        self._lock = threading.Lock()
        self._version: tuple | None = None
        self._catalogue: dict | None = None
        self._code_hash: str | None = None

    def document(self, relative_path: str) -> dict:
        # A verified manifest supplies these paths; reject unexpected paths too.
        allowed = {"docs/evidence-confidence/preregistro.json", "docs/evidence-confidence/sources.json"}
        allowed.update(f"docs/{name}/resultado.json" for name in (
            "cross-section-test", "factor-zoo", "tail-effect-test", "placebo-engine",
            "block-bootstrap", "rank-stability", "factor-zoo-sector"))
        if relative_path not in allowed:
            raise ValueError("Ruta inesperada del catálogo de evidencia.")
        return self.published._json(self.root / relative_path)

    def verify_sector(self, expected_sha256: str) -> dict:
        # Existing F6 verification includes the frozen specification/code and CSVs.
        sector = self.document("docs/factor-zoo-sector/resultado.json")
        from gabi.domain.research.live_ledger import fingerprint

        if fingerprint(sector) != expected_sha256:
            raise ValueError("Suplemento SIC modificado.")
        return self.published.verify_sector(sector)

    def _stamp(self) -> tuple:
        paths = (*self.published._paths(), self.root / "src/gabi/scoring.py")
        result: list[tuple[int, int, int, int, int] | None] = []
        for path in paths:
            try:
                stat = path.stat()
                result.append((stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
            except OSError:
                result.append(None)
        return tuple(result)

    def load(self) -> dict:
        with self._lock:
            before = self._stamp()
            if before == self._version and self._catalogue is not None:
                return deepcopy(self._catalogue)
            catalogue = load_catalog(self)
            try:
                code = self.root / "src/gabi/scoring.py"
                if code.stat().st_size > 2_000_000:
                    raise ValueError("Scoring source exceeds size limit")
                code_hash = hashlib.sha256(code.read_text(encoding="utf-8").encode()).hexdigest()
            except (OSError, ValueError):
                code_hash = None
            if before != self._stamp():
                self._catalogue, self._version, self._code_hash = None, None, None
                return {**catalogue, "available": False,
                        "errors": [*catalogue["errors"], "El catálogo cambió durante la verificación."]}
            self._catalogue, self._version, self._code_hash = catalogue, before, code_hash
            return deepcopy(catalogue)

    def matches(self, catalogue: dict, weights: dict, universe_id: str) -> bool:
        self.load()
        return rules.matches(catalogue, weights, universe_id, scoring_sha256=self._code_hash)
