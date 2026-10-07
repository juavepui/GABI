"""Fixed-date quality and provenance references and local metadata ports."""
import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from gabi.application.administration.data_quality import QualityReaders, provenance, summary
from gabi.domain.market import data_quality as quality
from gabi.domain.research.live_ledger import safe

NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)
SYMBOLS = ["AAA", "BBB", "EMPTY"]


def memory_readers(case="normal"):
    empty = case == "missing"
    prices = {} if empty else {"AAA": {"adjusted_count": 20, "latest_adjusted_date": "2024-01-10"},
                                "BBB": {"adjusted_count": 10, "latest_adjusted_date": "2023-12-01"}}
    fundamentals = {} if empty else {"AAA": "2024-01-10T20:00:00+00:00", "BBB": "2025-01-01T00:00:00+00:00"}
    sec = {} if empty else {"AAA": "2024-01-02T22:00:00+00:00", "BBB": NOW.isoformat()}
    insider = {} if empty else {"AAA": NOW.isoformat()}
    facts = set() if empty else {"AAA"}
    macro = {} if empty else {"M1": "2024-01-10T21:00:00+00:00", "M2": "2024-01-07T22:00:00+00:00"}

    def sectors(symbols, as_of):
        return {symbol: {"sector": "Technology" if symbol == "AAA" and not empty else None,
                         "is_approximate": symbol != "AAA" or empty,
                         "effective_date": "2022-01-01" if symbol == "AAA" and not empty else None}
                for symbol in symbols}

    def ciks(symbols):
        return {symbol: "0000000123" if symbol == "AAA" and not empty else None for symbol in symbols}

    def histories(series):
        if empty or series == "M2":
            return pd.DataFrame()
        return pd.DataFrame({"value": [1., 2.]}, index=pd.to_datetime(["2023-12-01", "2024-01-08"]))

    return QualityReaders(lambda s: prices, lambda s: fundamentals, lambda s: sec, lambda s: insider,
                          lambda s: facts, sectors, ciks, False, lambda: macro, ("M1", "M2"), histories,
                          lambda s: {symbol: {"fetched_at": dt} for symbol, dt in fundamentals.items()},
                          lambda s: {} if empty else {"AAA": {"latest_10k_date": "2023-12-31", "latest_10q_date": "2023-09-30"}})


def diagnostic_frame(case):
    frame = pd.DataFrame({"revenue_growth_pct": [80., None, 50.], "composite_score": [80., None, 20.],
                          "confidence": [90., None, 20.], "score_coverage": [1., .2, .6],
                          "sector": ["Technology", None, "Other"], "sector_is_approximate": [False, True, True],
                          "identity_status": ["resolved", "unresolved", "resolved"]}, index=SYMBOLS)
    return frame.iloc[:0] if case == "empty" else frame


def _reference():
    return json.loads((Path(__file__).parent / "fixtures/data_quality_migration.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", ["normal", "missing"])
def test_fixed_date_sources_match_original(case):
    readers = memory_readers(case)
    reference = _reference()["cases"][case]
    assert summary(SYMBOLS, readers, now=NOW) == reference["summary"]
    for symbol in SYMBOLS:
        assert provenance(symbol, readers, now=NOW, as_of="2023-01-10") == reference["provenance"][symbol]


@pytest.mark.parametrize("case", ["normal", "empty"])
def test_ranking_diagnostics_match_original_without_mutating_input(case):
    table = diagnostic_frame(case)
    before = table.copy(deep=True)
    reference = _reference()["diagnostics"][case]
    result = quality.ranking_quality(table)
    assert safe(result) == reference["quality"]
    assert quality.ranking_quality_warnings(result) == reference["warnings"]
    assert quality.low_confidence_candidates(table, SYMBOLS) == reference["low_confidence"]
    pd.testing.assert_frame_equal(table, before)


def test_empty_summary_does_not_invoke_readers_and_domain_uses_no_clock_or_io(monkeypatch):
    from gabi import storage

    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("SQLite accessed"))
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("Network accessed"))
    assert summary([], None, now=NOW) == {"n_symbols": 0, "sources": {}, "cik": None, "macro": None}
    assert quality.age_hours("2024-01-10T20:00:00+00:00", now=NOW) == 2
    with pytest.raises(TypeError, match="now"):
        quality.age_hours(None)
    inputs = {"AAA": NOW.isoformat()}
    before = deepcopy(inputs)
    assert quality.fetched_at_summary("Fixture", ["AAA"], inputs, 24, now=NOW)["fresh"] == 1.
    assert inputs == before


def test_worker_uses_explicit_clock_and_the_shared_flow(tmp_path, monkeypatch):
    from gabi import data_quality
    from gabi.infrastructure.legacy.data_health import LegacyDataHealth

    readers = memory_readers()
    monkeypatch.setattr(data_quality, "_readers", lambda: readers)
    source = LegacyDataHealth(tmp_path, now=lambda: NOW)
    assert source.summary(SYMBOLS) == _reference()["cases"]["normal"]["summary"]
    assert source.provenance("AAA", "2023-01-10") == _reference()["cases"]["normal"]["provenance"]["AAA"]
    assert not (tmp_path / "gabi.db").exists()


def test_application_uses_utc_day_for_sector_reference():
    readers = memory_readers()
    dates = []
    sectors = readers.sector_asof

    def captured(symbols, as_of):
        dates.append(as_of)
        return sectors(symbols, as_of)

    readers = replace(readers, sector_asof=captured)
    summary(SYMBOLS, readers, now=datetime.fromisoformat("2024-01-11T00:30:00+03:00"))
    assert dates == ["2024-01-10", "2023-01-10"]
