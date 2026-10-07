"""Captured evidence rules, explicit cutoffs and shared assessment parity."""
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest
from test_evidence_confidence import NOW, frame, scoring, synthetic_catalogue

from gabi.application.market.evidence_assessment import build_evidence
from gabi.domain.market import evidence

REFERENCE = json.loads((Path(__file__).parent / "fixtures/evidence_rules_migration.json").read_text(encoding="utf-8"))


def _equal(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            _equal(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected, strict=True):
            _equal(a, b)
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-12, abs=1e-14)
    else:
        assert actual == expected


@pytest.mark.parametrize("name", ["normal", "missing", "unstable", "experimental", "retro", "confirmed"])
def test_conservative_categories_match_original(name):
    cat = synthetic_catalogue()
    if name == "confirmed":
        cat["independent_confirmations"] = [dict(preregistered=True, independent=True, integrity_ok=True,
                                                early_unsealed=False, model_version="exact-model", dataset_id=d,
                                                p_corrected=.01, effect=.2) for d in ("a", "b")]
    result = evidence.assess(frame().iloc[0], scoring.DEFAULT_WEIGHTS, catalogue=cat,
                             quality={"fresh": name != "missing"},
                             stability={} if name == "unstable" else {"top20_inclusion": 1.},
                             model_matches=name != "experimental", trace={"model_version": "exact-model"},
                             stage="RETROSPECTIVE" if name == "retro" else "LIVE_FORWARD")
    _equal(result, REFERENCE["cases"][name])


def test_freshness_matches_reference_and_ttls_are_explicit():
    source = frame().attrs["sources"]["F00"]
    _equal(evidence.freshness(source, source, market_date="2024-01-10", now=NOW), REFERENCE["cases"]["fresh"])
    old = {**source, "fundamentals_fetched_at": (NOW - timedelta(hours=25)).isoformat()}
    assert not evidence.freshness(old, source, market_date="2024-01-10", now=NOW)["fresh"]
    assert evidence.freshness(old, source, market_date="2024-01-10", now=NOW,
                              rules=evidence.EvidenceRules(fundamentals_hours=48))["fresh"]
    assert evidence.DEFAULT_RULES.fundamentals_hours == 24


def test_complete_flow_matches_captured_original_without_io_or_mutation(monkeypatch):
    from gabi import storage

    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("SQLite accessed"))
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("Network accessed"))
    table, cat = frame(), synthetic_catalogue()
    saved, catalogue_before = table.copy(deep=True), deepcopy(cat)

    def stability(frame, weights):
        return {}, pd.DataFrame(), pd.DataFrame({"top20_inclusion": [1.] * len(frame)}, index=frame.index)

    result = build_evidence(table, scoring.DEFAULT_WEIGHTS, now=NOW, market_date="2024-01-10", catalogue=cat,
                             matching=True, metadata={}, analyze_stability=stability,
                             model_id="GABI-MF-v1", benchmark="SPY", context={"model_version": "exact-model"})
    _equal(result, REFERENCE["build"])
    pd.testing.assert_frame_equal(saved, table)
    assert cat == catalogue_before


def test_domain_does_not_read_mutable_legacy_configuration(monkeypatch):
    from gabi import config

    source = frame().attrs["sources"]["F00"]
    before = evidence.freshness(source, source, market_date="2024-01-10", now=NOW)
    monkeypatch.setattr(config, "CACHE_MAX_AGE_HOURS", -1)
    assert evidence.freshness(source, source, market_date="2024-01-10", now=NOW) == before


def test_source_adapter_passes_its_clock_and_rule_settings(monkeypatch):
    from gabi import evidence_catalog, history_refresh, live_ledger, rank_stability
    from gabi.infrastructure.legacy.evidence import LegacyEvidence

    cat = synthetic_catalogue()
    monkeypatch.setattr(evidence_catalog, "load", lambda: cat)
    monkeypatch.setattr(evidence_catalog, "matches", lambda *a: True)
    monkeypatch.setattr(live_ledger, "model_metadata", lambda **k: {"model_version": "exact-model"})
    monkeypatch.setattr(rank_stability, "analyze", lambda frame, weights: (
        {}, pd.DataFrame(), pd.DataFrame({"top20_inclusion": [1.] * len(frame)}, index=frame.index)))
    seen = []
    monkeypatch.setattr(history_refresh, "last_completed_session", lambda now: seen.append(now) or "2024-01-10")
    sources = LegacyEvidence(now=lambda: NOW)
    _equal(sources.evidence(frame(), scoring.DEFAULT_WEIGHTS), REFERENCE["build"])
    assert seen == [NOW]
    table = frame()
    table.attrs["sources"]["F00"]["fundamentals_fetched_at"] = (NOW - timedelta(hours=25)).isoformat()
    assert not sources.evidence(table, scoring.DEFAULT_WEIGHTS)["F00"]["quality"]["fresh"]
    relaxed = LegacyEvidence(now=lambda: NOW, rules=evidence.EvidenceRules(fundamentals_hours=48))
    assert relaxed.evidence(table, scoring.DEFAULT_WEIGHTS)["F00"]["quality"]["fresh"]
