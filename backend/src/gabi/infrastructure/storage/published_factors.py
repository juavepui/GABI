"""Verified, bounded published Factor Zoo and SIC artifacts; no operational data."""

import hashlib
import json
import threading
from pathlib import Path

from gabi.application.errors import QueryError
from gabi.infrastructure.legacy import published_factors as seal

ARTIFACTS = frozenset(("cross-section-test", "factor-zoo", "tail-effect-test", "placebo-engine",
                       "block-bootstrap", "rank-stability", "factor-zoo-sector"))
SECTOR_CSV = frozenset(("filings.csv", "assignments.csv", "sector_ic.csv", "coverage.csv",
                        "factor_coverage.csv"))
DOWNLOADS = frozenset(("sector_ic.csv", "coverage.csv", "factor_coverage.csv"))
MAX_JSON_BYTES = 2_000_000
MAX_FILE_BYTES = 6_000_000
MAX_TOTAL_BYTES = 16_000_000


class FilePublishedFactors:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()
        self._version: tuple[tuple[int, int, int, int, int], ...] | None = None
        self._result: dict | None = None

    def _paths(self) -> tuple[Path, ...]:
        docs = self.root / "docs"
        return (docs / "evidence-confidence" / "preregistro.json",
                docs / "evidence-confidence" / "sources.json",
                *(docs / name / "resultado.json" for name in sorted(ARTIFACTS)),
                docs / "factor-zoo-sector" / "preregistro.json", seal.SECTOR_CODE_PATH,
                *(docs / "factor-zoo-sector" / name for name in sorted(SECTOR_CSV)))

    @staticmethod
    def _stamp(paths: tuple[Path, ...]) -> tuple[tuple[int, int, int, int, int], ...]:
        stamps = []
        total = 0
        for path in paths:
            stat = path.stat()
            if stat.st_size > MAX_FILE_BYTES:
                raise ValueError("Published artifact exceeds size limit")
            total += stat.st_size
            stamps.append((stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
                           stat.st_ctime_ns))
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Published artifacts exceed total size limit")
        return tuple(stamps)

    @staticmethod
    def _json(path: Path) -> dict:
        with path.open("rb") as stream:
            raw = stream.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("Published JSON exceeds size limit")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Published JSON must be an object")
        return value

    def _load_verified(self) -> dict:
        docs = self.root / "docs"
        rules_path = docs / "evidence-confidence" / "preregistro.json"
        manifest_path = docs / "evidence-confidence" / "sources.json"
        rules, manifest = self._json(rules_path), self._json(manifest_path)
        if seal.fingerprint(rules) != seal.RULE_SHA256 or seal.fingerprint(manifest) != seal.SOURCES_SHA256:
            raise ValueError("Published catalogue seal differs")
        sources = manifest["artifacts"]
        if set(sources) != ARTIFACTS:
            raise ValueError("Unexpected published artifact list")
        results = {}
        for name in sorted(ARTIFACTS):
            source = sources[name]
            expected_path = f"docs/{name}/resultado.json"
            if source["path"] != expected_path:
                raise ValueError("Unexpected published artifact path")
            path = self.root / expected_path
            result = self._json(path)
            if seal.fingerprint(result) != source["sha256"]:
                raise ValueError("Published artifact seal differs")
            results[name] = result

        sector = results["factor-zoo-sector"]
        self.verify_sector(sector)
        if not isinstance(results["factor-zoo"].get("factors"), dict) or not isinstance(
            sector.get("factors"), dict
        ) or not isinstance(sector.get("coverage"), list):
            raise ValueError("Unexpected published factor shape")
        return {"zoo": results["factor-zoo"], "sector": sector,
                "zoo_sha256": sources["factor-zoo"]["sha256"],
                "sector_sha256": sources["factor-zoo-sector"]["sha256"]}

    def verify_sector(self, sector: dict) -> dict:
        docs = self.root / "docs"
        specification_path = docs / "factor-zoo-sector" / "preregistro.json"
        if seal.fingerprint(self._json(specification_path)) != seal.SECTOR_SPEC_SHA256:
            raise ValueError("Published SIC specification differs")
        if sector["spec_sha256"] != seal.SECTOR_SPEC_SHA256 or sector["code_sha256"] != seal.text_hash(
            seal.SECTOR_CODE_PATH
        ):
            raise ValueError("Published SIC code seal differs")
        if set(sector["artifacts_sha256"]) != SECTOR_CSV:
            raise ValueError("Unexpected SIC artifact list")
        for name in sorted(SECTOR_CSV):
            path = docs / "factor-zoo-sector" / name
            if path.stat().st_size > MAX_FILE_BYTES or seal.text_hash(path) != sector["artifacts_sha256"][name]:
                raise ValueError("Published SIC artifact seal differs")
        return sector

    def read(self) -> dict:
        with self._lock:
            try:
                paths = self._paths()
                before = self._stamp(paths)
                if self._result is not None and before == self._version:
                    return self._result
                result = self._load_verified()
                # A changed artifact during verification must never be cached as verified.
                if before != self._stamp(paths):
                    raise ValueError("Published artifacts changed during verification")
                self._result, self._version = result, before
                return result
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                self._result, self._version = None, None
                raise QueryError("published_factors_unavailable",
                                 "No se puede verificar el mapa de factores publicado.", 503) from exc

    def download(self, name: str) -> str:
        if name not in DOWNLOADS:
            raise QueryError("published_export_not_found", "La exportación publicada no existe.", 404)
        result = self.read()
        path = self.root / "docs" / "factor-zoo-sector" / name
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("Published export exceeds size limit")
            contents = path.read_text(encoding="utf-8")
            if hashlib.sha256(contents.encode()).hexdigest() != result["sector"]["artifacts_sha256"][name]:
                raise ValueError("Published export seal differs")
            return contents
        except (OSError, ValueError, KeyError) as exc:
            raise QueryError("published_factors_unavailable",
                             "No se puede verificar la exportación publicada.", 503) from exc
