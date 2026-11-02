"""Operational settings outside the sealed config (#270): one versioned source, exact equivalence, no config reads."""

import ast
import json
from pathlib import Path

from gabi import config
from gabi.infrastructure import operational_settings
from gabi.infrastructure.model_versions import active_model

SRC = Path(__file__).resolve().parents[1] / "src" / "gabi"
MOVED = {"BENCHMARK_SYMBOL", "CACHE_MAX_AGE_HOURS", "EDGAR_CACHE_MAX_AGE_HOURS", "INFO_KEYS"}


def test_the_versioned_source_reproduces_the_sealed_values_exactly():
    settings = operational_settings.current()
    assert settings.version == "operational-settings-v1"
    assert operational_settings.benchmark_symbol() == config.BENCHMARK_SYMBOL == active_model().benchmark_symbol
    assert settings.cache_max_age_hours == config.CACHE_MAX_AGE_HOURS
    assert settings.edgar_cache_max_age_hours == config.EDGAR_CACHE_MAX_AGE_HOURS
    # The sealed list plus the field the checklist (#167) added outside it, in the same order as before.
    assert settings.info_keys == (*config.INFO_KEYS, "heldPercentInsiders")


def _frozen() -> set[str]:
    hashes = json.loads((SRC.parents[1] / "legacy-engine-hashes.json").read_text(encoding="utf-8"))
    return set(hashes)


def test_no_adapter_or_permanent_module_reads_the_moved_settings_from_config():
    frozen = _frozen()
    offenders = []
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(SRC).as_posix()
        if relative == "config.py" or relative in frozen or "__pycache__" in relative:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in MOVED and isinstance(node.value, ast.Name) \
                    and node.value.id == "config":
                offenders.append(f"{relative}:{node.lineno}:{node.attr}")
            if isinstance(node, ast.ImportFrom) and node.module in {"gabi.config", "config"} \
                    and any(alias.name in MOVED for alias in node.names):
                offenders.append(f"{relative}:{node.lineno}:import")
    assert offenders == []


def test_the_live_ledger_fingerprint_covers_the_operational_settings():
    from gabi import live_ledger

    assert "infrastructure/operational_settings.py" in live_ledger.model_metadata()["code_sha256"]
