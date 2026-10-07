"""Synthetic SEC facts, point-in-time boundary and domain scoring compatibility."""

import json
from pathlib import Path

import pandas as pd
import pytest

from gabi import config, edgar, historical_period, live_ledger, quality_persistence, scoring, storage
from gabi.application.market.quality import quality_as_of
from gabi.domain.market import quality_persistence as quality
from gabi.domain.market import scoring as domain_scoring
from gabi.domain.market import sec_facts
from gabi.domain.research import periods
from gabi.infrastructure.legacy.market import calculators

CASES = ("full", "missing", "stale", "revision", "conflict", "gap", "empty", "zero")


def synthetic_facts(case):
    facts = {"facts": {"us-gaap": {}}}
    values = {"Revenues": 100, "NetIncomeLoss": 10, "OperatingIncomeLoss": 20,
              "NetCashProvidedByUsedInOperatingActivities": 18,
              "PaymentsToAcquirePropertyPlantAndEquipment": 8,
              "StockholdersEquity": 50, "LongTermDebt": 20,
              "GrossProfit": 40, "DepreciationDepletionAndAmortization": 4,
              "CashAndCashEquivalentsAtCarryingValue": 5, "CommonStockSharesOutstanding": 10}
    for tag, value in values.items():
        unit = "shares" if tag == "CommonStockSharesOutstanding" else "USD"
        entries = [{"start": f"{year}-01-01", "end": f"{year}-12-31", "val": value * (1.1 ** (year - 2020)),
                    "form": "10-K", "fp": "FY", "filed": f"{year + 1}-02-01", "accn": f"{year}-1"}
                   for year in range(2020, 2024)]
        facts["facts"]["us-gaap"][tag] = {"units": {unit: entries}}
    gaap = facts["facts"]["us-gaap"]
    if case == "missing":
        del gaap["OperatingIncomeLoss"]
        del gaap["CashAndCashEquivalentsAtCarryingValue"]
    elif case == "stale":
        for tag in ("StockholdersEquity", "LongTermDebt", "NetIncomeLoss"):
            gaap[tag]["units"]["USD"].pop()
    elif case == "revision":
        entries = gaap["Revenues"]["units"]["USD"]
        entries.append({**entries[-1], "val": 150, "filed": "2024-03-01", "accn": "2023-2"})
    elif case == "conflict":
        entries = gaap["Revenues"]["units"]["USD"]
        entries.append({**entries[-1], "val": 150})
    elif case == "gap":
        gaap["Revenues"]["units"]["USD"].pop(1)
    elif case == "empty":
        gaap.clear()
    elif case == "zero":
        gaap["NetIncomeLoss"]["units"]["USD"][-1]["val"] = 0
        gaap["LongTermDebt"]["units"]["USD"][-1]["val"] = 0
    return facts


@pytest.fixture(scope="module")
def reference():
    return json.loads((Path(__file__).parent / "fixtures/fundamental_migration.json").read_text(encoding="utf-8"))


def assert_mapping(actual, expected):
    assert actual.keys() == expected.keys()
    for key, value in expected.items():
        if isinstance(value, float):
            assert actual[key] == pytest.approx(value, rel=1e-12, abs=1e-14)
        else:
            assert actual[key] == value


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("aligned", [False, True])
def test_sec_metrics_and_reasons_match_original(reference, case, aligned):
    facts = synthetic_facts(case)
    expected = reference[case][str(aligned)]
    assert_mapping(sec_facts.compute_edgar_metrics(facts, fiscal_alignment=aligned), expected["metrics"])
    assert sec_facts.fundamental_missing_reasons(facts, fiscal_alignment=aligned) == expected["reasons"]
    assert_mapping(quality.from_facts(facts), reference[case]["quality"])


def test_domain_alignment_is_independent_of_legacy_context():
    facts = synthetic_facts("stale")
    before = sec_facts.compute_edgar_metrics(facts)
    with edgar.fiscal_alignment():
        assert edgar.compute_edgar_metrics(facts) == sec_facts.compute_edgar_metrics(facts, fiscal_alignment=True)
        assert sec_facts.compute_edgar_metrics(facts) == before
    assert not edgar.fiscal_alignment_enabled()


def test_domain_scoring_is_independent_of_frozen_engine_metric_patches(monkeypatch):
    frame = pd.DataFrame({metric: [1., 2.] for group in domain_scoring.SCORE_METRICS.values() for metric in group},
                         index=["A", "B"])
    frame["extra_quality"] = [.4, .8]
    expected = domain_scoring.build_scores(frame)
    monkeypatch.setattr(scoring, "QUALITY_METRICS_HIGHER_BETTER", [*scoring.QUALITY_METRICS_HIGHER_BETTER, "extra_quality"])
    monkeypatch.setitem(scoring.SCORE_METRICS, "quality", [*scoring.SCORE_METRICS["quality"], "extra_quality"])
    assert "extra_quality_pct" in scoring.build_scores(frame)
    pd.testing.assert_frame_equal(domain_scoring.build_scores(frame), expected)


def test_quality_reader_receives_exact_cutoff_and_identity():
    calls = []

    def reader(symbol, cutoff, *, entity_id):
        calls.append((symbol, cutoff, entity_id))
        return synthetic_facts("full")

    result = quality_as_of("ABC", "2024-02-03", read_facts=reader, entity_id="cik:0000000001")
    assert calls == [("ABC", "2024-02-03", "cik:0000000001")]
    assert result == quality.from_facts(synthetic_facts("full"))


def test_legacy_functions_and_ranking_use_single_domain_implementations():
    frame = pd.DataFrame({"pe": [10, 20]}, index=["A", "B"])
    pd.testing.assert_frame_equal(scoring.build_scores(frame), domain_scoring.build_scores(frame))
    pd.testing.assert_series_equal(scoring.compute_confidence(frame), domain_scoring.compute_confidence(frame))
    assert calculators().scores is domain_scoring.build_scores
    assert calculators().confidence is domain_scoring.compute_confidence
    assert quality_persistence.from_facts is quality.from_facts
    assert historical_period.Period is periods.Period
    assert historical_period.P2010 is periods.P2010
    assert edgar._extract_annual_values is sec_facts._extract_annual_values
    assert edgar._extract_instant_values is sec_facts._extract_instant_values
    assert edgar._extract_raw_facts is sec_facts._extract_raw_facts


def test_domain_does_not_read_storage_network_or_global_settings(monkeypatch):
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("Domain accessed SQLite"))
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("Domain accessed network"))
    monkeypatch.setattr(config, "RISK_FREE_RATE", .9)
    assert sec_facts.compute_edgar_metrics(synthetic_facts("full"))["roic"] > 0
    assert quality.from_facts(synthetic_facts("full"))["roic_years"] == 4
    assert domain_scoring.build_scores(pd.DataFrame({"pe": [10, None]}, index=["A", "B"]))["composite_score"].isna().all()
    assert periods.for_date("2015-12-31") is periods.P2010


def test_ledger_tracks_relocated_scoring_and_sec_formulas(monkeypatch):
    monkeypatch.setattr("gabi.research_lab._dependency_versions", lambda: {})
    monkeypatch.setattr("gabi.research_lab._env_fingerprint", lambda: "fixture")
    monkeypatch.setattr("gabi.research_lab._current_git_commit", lambda: "fixture")
    hashes = live_ledger.model_metadata()["code_sha256"]
    assert "domain/market/scoring.py" in hashes and "domain/market/sec_facts.py" in hashes
