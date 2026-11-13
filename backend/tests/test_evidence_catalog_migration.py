"""Pinned catalogue parity, bounded sources and invalidation on copied publications."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_published_factors_api import copied_publications

from gabi.application.research.evidence_catalog import load_catalog
from gabi.domain.research.evidence_catalog import interpret, matches
from gabi.infrastructure.storage.evidence_catalog import FileEvidenceCatalog

REFERENCE = json.loads((Path(__file__).parent / "fixtures/evidence_catalog_migration.json").read_text(encoding="utf-8"))


def test_explicit_root_matches_original_and_cached_results_are_isolated(tmp_path, monkeypatch):
    copied_publications(tmp_path)
    source = FileEvidenceCatalog(tmp_path)
    calls = []
    document = source.document
    monkeypatch.setattr(source, "document", lambda path: calls.append(path) or document(path))
    result = source.load()
    assert result == REFERENCE["catalogue"]
    loaded = len(calls)
    result["factors"].clear()
    assert source.load() == REFERENCE["catalogue"] and len(calls) == loaded
    assert not (tmp_path / "data").exists()


def test_modification_missing_artifact_and_repair_invalidate_the_cache(tmp_path):
    copied_publications(tmp_path)
    source = FileEvidenceCatalog(tmp_path)
    assert source.load()["available"]
    path = tmp_path / "docs/factor-zoo/resultado.json"
    original = path.read_bytes()
    path.write_text("{}", encoding="utf-8")
    invalid = source.load()
    assert not invalid["available"] and not invalid["factors"]
    assert invalid["errors"] == ["factor-zoo: resultado ausente, ilegible o modificado"]
    assert "factor-zoo-sector" in invalid["sources"]  # Independent SIC verification still succeeds.
    path.unlink()
    assert source.load()["errors"] == invalid["errors"]
    path.write_bytes(original)
    assert source.load() == REFERENCE["catalogue"]


def test_source_path_and_json_sizes_are_bounded(tmp_path):
    source = FileEvidenceCatalog(tmp_path)
    with pytest.raises(ValueError, match="Ruta inesperada"):
        source.document("../data/gabi.db")
    path = tmp_path / "docs/evidence-confidence/preregistro.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b" " * 2_000_001)
    with pytest.raises(ValueError, match="size limit"):
        source.document("docs/evidence-confidence/preregistro.json")


def test_change_during_verification_is_never_cached(tmp_path, monkeypatch):
    copied_publications(tmp_path)
    source = FileEvidenceCatalog(tmp_path)
    document = source.document

    def mutate(path):
        result = document(path)
        if path == "docs/tail-effect-test/resultado.json":
            (tmp_path / path).write_text("{}", encoding="utf-8")
        return result

    monkeypatch.setattr(source, "document", mutate)
    result = source.load()
    assert not result["available"] and source._version is None
    assert result["errors"][-1] == "El catálogo cambió durante la verificación."


def test_scope_comparison_has_explicit_code_hash():
    cat = {"scope": {"weights": {"value": .3}, "universe_id": "SYNTHETIC", "scoring_sha256": "original"}}
    assert matches(cat, {"value": .3}, "SYNTHETIC", scoring_sha256="original")
    for code in (None, "changed"):
        assert not matches(cat, {"value": .3}, "SYNTHETIC", scoring_sha256=code)
    assert not matches(cat, {"value": .3}, "CUSTOM", scoring_sha256="original")
    assert not matches(cat, {"value": .4}, "SYNTHETIC", scoring_sha256="original")


def test_failed_interpretation_preserves_partial_output_without_mutating_inputs():
    catalogue = {"available": True, "errors": [], "factors": {}, "model": {}}
    artifacts = {"factor-zoo": {"factors": {"synthetic": {"media": .1}}}, "cross-section-test": {}}
    before = deepcopy((catalogue, artifacts))
    result = interpret(catalogue, artifacts)
    assert not result["available"] and result["factors"] == artifacts["factor-zoo"]["factors"]
    assert result["errors"] == ["'principal_ic'"] and (catalogue, artifacts) == before


def test_unverified_manifest_does_not_read_artifacts():
    class Unverified:
        def __init__(self):
            self.calls = []

        def document(self, path):
            self.calls.append(path)
            return {}

        def verify_sector(self, expected):
            pytest.fail("Unverified source reached SIC verifier")

    inputs = Unverified()
    assert not load_catalog(inputs)["available"]
    assert inputs.calls == ["docs/evidence-confidence/preregistro.json", "docs/evidence-confidence/sources.json"]
