"""Published hash conventions from the unchanged retrospective engines."""

from pathlib import Path

from gabi import evidence_catalog, factor_sector_stability, live_ledger

RULE_SHA256 = evidence_catalog.RULE_SHA256
SOURCES_SHA256 = evidence_catalog.SOURCES_SHA256
SECTOR_SPEC_SHA256 = factor_sector_stability.SPEC_SHA256
SECTOR_CODE_PATH = Path(factor_sector_stability.__file__)


def fingerprint(value: dict) -> str:
    return live_ledger.fingerprint(value)


def text_hash(path: Path) -> str:
    return factor_sector_stability.file_hash(path, text=True)
