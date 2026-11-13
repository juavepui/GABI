"""Compatibility source composition for frozen sector and prospective-ledger callers."""
import hashlib
import json

from gabi.application.research.evidence_catalog import load_catalog
from gabi.domain.research import evidence_catalog as rules

from . import config, factor_sector_stability

RULE_SHA256 = rules.RULE_SHA256
SOURCES_SHA256 = rules.SOURCES_SHA256


class _Inputs:
    @staticmethod
    def document(relative_path):
        return json.loads((config.BASE_DIR / relative_path).read_text(encoding="utf-8"))

    @staticmethod
    def verify_sector(expected_sha256):
        return factor_sector_stability.load_saved(expected_sha256)


def load():
    return load_catalog(_Inputs(), rules_sha256=RULE_SHA256, sources_sha256=SOURCES_SHA256)


def matches(catalogue, weights, universe_id):
    try:
        code_hash = hashlib.sha256((config.BASE_DIR / "src" / "gabi" / "scoring.py").read_text(encoding="utf-8").encode()).hexdigest()
    except OSError:
        return False
    return rules.matches(catalogue, weights, universe_id, scoring_sha256=code_hash)
