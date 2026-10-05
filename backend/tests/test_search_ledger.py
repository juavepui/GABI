import json
import shutil
from pathlib import Path

import pytest

from gabi import config
from gabi.domain.research.search_ledger import fingerprint
from gabi.infrastructure.storage import search_ledger


def test_published_catalog_reconciles_convention_without_claiming_exhaustiveness():
    ledger = search_ledger.build(config.BASE_DIR)
    assert ledger["counts"] == {
        "legacy_guard_entries": 34, "legacy_observed_entries": 33, "legacy_pending_entries": 1,
        "additional_observed_records": 4, "diagnostic_groups": 14,
    }
    assert ledger["exhaustive_search_history"] is False
    assert ledger["global_error_control_established"] is False
    pending = [row for row in ledger["legacy_entries"] if row["state"] != "observed"]
    assert len(pending) == 1
    assert pending[0]["id"] == "value/prospective"
    assert pending[0]["observed_sample"] is None
    assert pending[0]["result_ref"] is None
    assert len(ledger["unresolved_groups"]) == 4


def test_all_four_new_candidates_retain_failures_without_promotion():
    ledger = search_ledger.build(config.BASE_DIR)
    candidates = [row for row in ledger["legacy_entries"] if row["id"].startswith(("discovery/", "repurchase/"))]
    assert len(candidates) == 4
    assert all(row["failures"] and row["decision"] == "failed_daily_gate" for row in candidates)
    assert all(not row["demonstrated_superiority"] for row in ledger["legacy_entries"])


def test_json_references_resolve_and_configuration_hashes_cover_settings():
    ledger = search_ledger.build(config.BASE_DIR)
    for row in ledger["legacy_entries"] + ledger["additional_observed_records"]:
        assert row["configuration_sha256"] == fingerprint(row["configuration"])
        for reference in (row["specification_ref"], row["result_ref"]):
            if reference is None:
                continue
            name, pointer = reference.split("#", 1)
            if not name.endswith(".json"):
                continue
            value = json.loads((config.BASE_DIR / name).read_text(encoding="utf-8"))
            for key in pointer.strip("/").split("/"):
                value = value[int(key)] if isinstance(value, list) else value[key]


@pytest.fixture
def copied_sources(tmp_path):
    ledger = search_ledger.build(config.BASE_DIR)
    for name in ledger["sources_sha256_lf"]:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(config.BASE_DIR / name, destination)
    return tmp_path, ledger


def test_verification_detects_changed_source_even_if_its_declared_hash_is_unchanged(copied_sources):
    root, ledger = copied_sources
    published = root / "ledger.json"
    published.write_text(json.dumps(ledger), encoding="utf-8")
    search_ledger.verify(root, published)
    source = root / "docs/strategy-discovery/preregistro.json"
    content = json.loads(source.read_text(encoding="utf-8"))
    content["spec"]["portfolio"]["maximum_per_division"] = 7
    source.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        search_ledger.verify(root, published)


def test_verification_detects_tampered_ledger(copied_sources):
    root, ledger = copied_sources
    ledger["exhaustive_search_history"] = True
    published = root / "ledger.json"
    published.write_text(json.dumps(ledger), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        search_ledger.verify(root, published)


def test_catalog_reads_no_data_reserves_or_databases(monkeypatch):
    original = Path.read_text
    read_paths = []

    def record(path, *args, **kwargs):
        relative = path.relative_to(config.BASE_DIR)
        assert relative.parts[0] in {"docs", "HIPOTESIS_CONGELADA.md"}
        assert "smallmid-test" not in relative.parts
        assert "prospective-plan" not in relative.parts
        assert path.suffix != ".db"
        read_paths.append(relative)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", record)
    ledger = search_ledger.build(config.BASE_DIR)
    assert len(read_paths) == len(ledger["sources_sha256_lf"])


def test_published_ledger_is_reproducible():
    search_ledger.verify(config.BASE_DIR)
