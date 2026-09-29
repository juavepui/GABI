from copy import deepcopy
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from gabi import config, live_ledger, scoring
from gabi import evidence_catalog as catalogue
from gabi import evidence_confidence as ec

NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)


def frame():
    points = np.linspace(99, 1, 35)
    columns = {m + "_pct": points for metrics in scoring.SCORE_METRICS.values() for m in metrics}
    result = pd.DataFrame({**columns, **{b + "_score": points for b in scoring.SCORE_METRICS},
                           "composite_score": points, "score_coverage": 1., "confidence": 100.},
                          index=[f"F{i:02d}" for i in range(35)])
    result.attrs["sources"] = {s: {"price_date": "2024-01-10", "close": 10., "adj_close": 10.,
                                   "fundamentals_fetched_at": NOW.isoformat(), "sec_fetched_at": NOW.isoformat()}
                               for s in [*result.index, "SPY"]}
    return result


def synthetic_catalogue():
    """Explicit synthetic evidence to exercise categories; never production studies."""
    return {"available": True, "errors": [], "limitations": [],
            "factors": {m: {"media": .1, "p_holm": .01} for metrics in scoring.SCORE_METRICS.values() for m in metrics},
            "model": {"pass": True}, "placebos": {"pass": True}, "bootstrap": {"pass": True},
            "independent_confirmations": []}


def assess(cat=None, row=None, **overrides):
    args = {"catalogue": synthetic_catalogue() if cat is None else cat, "quality": {"fresh": True},
            "stability": {"top20_inclusion": 1.}, "model_matches": True,
            "trace": {"model_version": "exact-model"}, **overrides}
    return ec.assess(frame().iloc[0] if row is None else row, scoring.DEFAULT_WEIGHTS, **args)


def test_real_pinned_studies_high_score_complete_data_still_low():
    cat = catalogue.load()
    assert cat["available"] and len(cat["sources"]) == 7
    assert cat["independent_confirmations"] == []
    assert not cat["model"]["pass"]
    assert cat["placebos"]["conditional_pass"]
    assert cat["bootstrap"]["v2_cagr_difference"]["20"]["lower"] < 0
    result = ec.build(frame(), scoring.DEFAULT_WEIGHTS, now=NOW)["F00"]
    assert result["score"] == 99. and result["weighted_data_coverage"] == 100.
    assert result["confidence_level"] == "BAJA"
    assert result["validated_score_fraction"] == 0.
    assert result["stability"]["top20_inclusion"] == 1.
    assert any("#44" in r for r in result["reasons_against"])
    assert any("sectores" in r for r in result["reasons_against"])
    assert result["trace"]["data_fingerprint"].startswith("signal-inputs-v1:")
    assert "future_probability" not in result
    assert all(len(f["sic_division_stability"]) == 10 for f in result["factors"])
    assert all(f["sic_experiment_id"] == "factor-zoo-sector" for f in result["factors"])


def test_higher_categories_require_all_gates_and_independent_provenance():
    cat = synthetic_catalogue()
    assert assess(cat)["confidence_level"] == "MEDIA"
    confirmations = [{"preregistered": True, "independent": True, "integrity_ok": True, "early_unsealed": False,
                      "model_version": "exact-model", "dataset_id": d, "p_corrected": .01, "effect": .2}
                     for d in ("independent-a", "independent-b")]
    cat["independent_confirmations"] = confirmations
    assert assess(cat)["confidence_level"] == "ALTA"
    for field, value in (("model_version", "other-model"), ("early_unsealed", True), ("integrity_ok", False),
                         ("independent", False), ("p_corrected", .07), ("effect", -.1), ("dataset_id", "independent-a")):
        invalid = deepcopy(cat)
        invalid["independent_confirmations"][1][field] = value
        assert assess(invalid)["confidence_level"] == "MEDIA"
    for stage in live_ledger.STAGES:
        assert assess(stage=stage, cat=catalogue.load())["confidence_level"] == "BAJA"


@pytest.mark.parametrize("override", [{"quality": {"fresh": False}}, {"stability": {}},
                                       {"stability": {"top20_inclusion": .8}}, {"model_matches": False}])
def test_missing_stale_fragile_experimental_inputs_fail_conservatively(override):
    result = assess(**override)
    assert result["confidence_level"] == "BAJA" and result["reasons_against"]


def test_raw_p_and_descriptive_classification_cannot_validate_a_factor():
    cat = synthetic_catalogue()
    for values in cat["factors"].values():
        values.update(p_holm=.08, p=.001, classification="robusto")
    result = assess(cat)
    assert result["validated_factor_weight"] == 0
    assert result["confidence_level"] == "BAJA"


def test_positive_sic_diagnostics_never_replace_primary_holm():
    cat = synthetic_catalogue()
    for values in cat["factors"].values():
        values.update(p_holm=.20, sic_division_stability={"D": {"ic_mean": .8, "n_periods": 57,
                                                               "status": "sufficient_periods"}})
    result = assess(cat)
    assert result["validated_factor_weight"] == 0
    assert result["confidence_level"] == "BAJA"
    assert all(f["sic_division_stability"]["D"]["ic_mean"] == .8 for f in result["factors"])


def test_changed_sector_metadata_is_named_and_fails_conservatively(monkeypatch):
    from pathlib import Path

    path = config.BASE_DIR / "docs" / "factor-zoo-sector" / "assignments.csv"
    original = Path.read_text

    def changed(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        return value + "modified" if self == path else value

    monkeypatch.setattr(Path, "read_text", changed)
    cat = catalogue.load()
    assert not cat["available"]
    assert any("factor-zoo-sector" in error for error in cat["errors"])
    assert assess(cat)["confidence_level"] == "BAJA"


def test_available_block_renormalization_reproduces_score_without_reweighting():
    row = frame().iloc[0].copy()
    for metric in scoring.SCORE_METRICS["risk"]:
        row[metric + "_pct"] = np.nan
    row["risk_score"] = np.nan
    row["confidence"] = 90
    result = assess(row=row)
    assert sum(c["effective_weight"] for c in result["factors"]) == pytest.approx(1.)
    assert sum(c["effective_weight"] for c in result["factors"] if c["family"] == "value") == pytest.approx(.30 / .9)
    assert sum(c["contribution_points"] for c in result["factors"]) == pytest.approx(row.composite_score)
    assert result["validated_score_fraction"] == pytest.approx(1.)
    assert result["weighted_data_coverage"] == 90


def test_missing_or_tampered_study_cannot_upgrade_and_is_named(tmp_path, monkeypatch):
    from pathlib import Path

    path = config.BASE_DIR / "docs" / "factor-zoo" / "resultado.json"
    original = Path.read_text

    def changed(self, *args, **kwargs):
        if self == path:
            return '{}'
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", changed)
    cat = catalogue.load()
    assert not cat["available"] and not cat["factors"]
    result = assess(cat)
    assert result["confidence_level"] == "BAJA"
    assert any("factor-zoo" in r for r in result["reasons_against"])


def test_rule_tampering_unavailable_catalogue_and_custom_universe(monkeypatch):
    monkeypatch.setattr(catalogue, "RULE_SHA256", "tampered")
    cat = catalogue.load()
    assert not cat["available"]
    assert assess(cat)["confidence_level"] == "BAJA"
    assert not catalogue.matches(cat, scoring.DEFAULT_WEIGHTS, "CUSTOM")


def test_freshness_requires_benchmark_and_input_timestamps_and_valid_prices():
    source = frame().attrs["sources"]["F00"]
    assert ec.freshness(source, source, market_date="2024-01-10", now=NOW)["fresh"]
    for field, value in (("sec_fetched_at", None), ("fundamentals_fetched_at", "2025-01-01T00:00:00+00:00"),
                         ("price_date", "2024-01-09"), ("adj_close", np.nan)):
        bad = {**source, field: value}
        assert not ec.freshness(bad, source, market_date="2024-01-10", now=NOW)["fresh"]


def test_build_is_read_only_and_weights_changes_are_traceable():
    original = frame()
    snapshot = original.copy(deep=True)
    weights = {**scoring.DEFAULT_WEIGHTS, "value": .29, "quality": .36}
    result = ec.build(original, weights, now=NOW)
    pd.testing.assert_frame_equal(snapshot, original)
    assert result["F00"]["trace"]["model_id"] == "EXPERIMENTAL"
    assert result["F00"]["confidence_level"] == "BAJA"
    assert result["F00"]["trace"]["configuration"]["weights"] == weights
