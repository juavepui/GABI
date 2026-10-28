"""Prospective ENS record (#237): calendar, window, chain and scoring reuse, with synthetic data only."""

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gabi.application.research import ensemble_prospective as use_case
from gabi.domain.research import ensemble_prospective as rules
from gabi.domain.research.ensemble_robustness import metric_columns

SPEC = json.loads((Path(__file__).parents[2] / "docs/ensemble-robustness/preregistro.json").read_text(encoding="utf-8"))["spec"]
DIVISIONS = ["D", "H", "I", "G"]


def weekdays(start: date, end: date) -> list[date]:
    return [start + timedelta(days=n) for n in range((end - start).days + 1) if (start + timedelta(days=n)).weekday() < 5]


SESSIONS = weekdays(date(2026, 12, 1), date(2028, 1, 31))


def scored(n=60, seed=1):
    """Synthetic output of the frozen #60 scorer: metric percentiles and their blocks."""
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(rng.uniform(0, 1, (n, len(metric_columns(SPEC)))), columns=metric_columns(SPEC),
                         index=[f"S{i:03d}" for i in range(n)])
    frame.iloc[0, :] = np.nan  # no block: outside U_t
    frame.insert(0, "division", [DIVISIONS[i % 4] for i in range(n)])
    frame.insert(0, "entity_id", [f"cik:{i:010d}" for i in range(n)])
    for block in ("value", "quality", "expectations"):
        columns = SPEC["components"]["metrics"][block]
        minimum = SPEC["components"]["block_minimum_available"][block]
        frame[block] = frame[columns].mean(axis=1).where(frame[columns].notna().sum(axis=1) >= minimum)
    return frame


def test_calendar_and_recording_window():
    assert rules.signal_dates(date(2027, 9, 21)) == [date(2026, 12, 21), date(2027, 3, 21), date(2027, 6, 21),
                                                     date(2027, 9, 21)]
    # 2026-12-21 is a Monday: the window closes five sessions later (Christmas is not a holiday here).
    assert rules.window_end(date(2026, 12, 21), SESSIONS) == date(2026, 12, 28)
    assert rules.open_signal(date(2026, 12, 28), SESSIONS) == date(2026, 12, 21)
    assert rules.open_signal(date(2026, 12, 29), SESSIONS) is None
    # 2027-03-21 is a Sunday: the window starts on Monday the 22nd.
    assert rules.window_end(date(2027, 3, 21), SESSIONS) == date(2027, 3, 29)
    assert rules.missed(date(2027, 4, 1), {date(2026, 12, 21)}, SESSIONS) == [date(2027, 3, 21)]


def test_record_reuses_the_ensemble_rules_and_seals_the_chain():
    frame = scored()
    first = rules.record(date(2026, 12, 21), date(2026, 12, 21), frame, SPEC, previous=None,
                         excluded={"X": "stale_filing"}, entry={"S001": {"date": "2026-12-18", "close": 10.0,
                                                                         "adj_close": 9.5}},
                         evidence=[], inputs={"code_commit": "abc"})
    assert first["universe"] == {"size": 59, "minimum_size": 40, "evaluable": True, "scored": 60,
                                 "excluded": [{"symbol": "X", "reason": "stale_filing"}]}
    by_symbol = {row["symbol"]: row for row in first["scores"]}
    assert "S000" not in by_symbol and by_symbol["S001"]["adj_close"] == 9.5 and by_symbol["S002"]["adj_close"] is None
    expected = frame.loc["S005", ["value", "quality", "expectations"]].mean()
    assert by_symbol["S005"]["ENS"] == pytest.approx(expected, abs=1e-15)
    for name, portfolio in first["portfolios"].items():
        assert len(portfolio["symbols"]) + portfolio["cash_slots"] == 20
        assert max(pd.Series([by_symbol[s]["division"] for s in portfolio["symbols"]]).value_counts()) <= 6
    assert "retorno" not in json.dumps(first) and '"return' not in json.dumps(first)
    marker = rules.not_recorded(date(2027, 3, 21), date(2027, 3, 29), first["sha256"])
    assert rules.verify_chain([first, marker])["not_recorded"] == 1
    with pytest.raises(ValueError, match="Huella"):
        rules.verify_chain([{**first, "universe": {**first["universe"], "size": 1}}])
    with pytest.raises(ValueError, match="calendario"):
        rules.verify_chain([marker])
    with pytest.raises(ValueError, match="Bloque"):
        rules.record(date(2026, 12, 21), date(2026, 12, 21), frame.assign(value=frame["value"] + .1), SPEC,
                     previous=None, excluded={}, entry={}, evidence=[], inputs={})


class Store:
    def __init__(self):
        self.records = []

    def all(self):
        return list(self.records)

    def write(self, record):
        if any(row["signal_date"] == record["signal_date"] for row in self.records):
            raise FileExistsError(record["signal_date"])
        self.records.append(json.loads(json.dumps(record)))  # what the JSON file gives back
        return f"registro-{record['signal_date']}.json"


class Sources:
    def __init__(self, price_day="2026-12-18"):
        self.price_day, self.calls = price_day, []

    def sessions(self, start, end):
        return [day for day in SESSIONS if start <= day <= end]

    def constituents(self):
        return [f"S{i:03d}" for i in range(62)], {"source": "test"}

    def ranking(self, signal, symbols):
        self.calls.append(("ranking", signal))
        frame = pd.DataFrame(index=symbols)
        frame["composite_score"] = 50.0
        frame["score_coverage"] = .9
        frame.loc["S060", "score_coverage"] = .5  # not eligible
        frame.loc["S061", "composite_score"] = np.nan  # not eligible
        return frame

    def divisions(self, frame, signal):
        labels = pd.DataFrame({"division": [DIVISIONS[i % 4] for i in range(len(frame))], "reason": "classified"},
                              index=frame.index)
        labels.loc["S059", ["division", "reason"]] = ["", "stale_filing"]
        return labels

    def score(self, frame):
        assert "S059" not in frame.index and set(frame.division) <= set(DIVISIONS)
        return scored().loc[frame.index].assign(division=frame.division)

    def entry_prices(self, symbols, signal):
        return {symbol: {"date": self.price_day, "close": 1.0, "adj_close": 1.0} for symbol in symbols}


def test_use_case_records_once_seals_missed_quarters_and_requires_fresh_prices():
    store = Store()
    with pytest.raises(ValueError, match="empieza"):
        use_case.record_due(date(2026, 12, 18), spec=SPEC, sources=Sources(), store=store, inputs=dict)
    with pytest.raises(ValueError, match="Precios"):
        use_case.record_due(date(2026, 12, 21), spec=SPEC, sources=Sources("2026-12-17"), store=store, inputs=dict)
    result = use_case.record_due(date(2026, 12, 22), spec=SPEC, sources=Sources(), store=store,
                                 inputs=lambda: {"code_commit": "abc"})
    assert result["recorded"] == "2026-12-21" and result["universe"] == 58 and result["excluded"] == 1
    sealed = store.records[0]
    assert sealed["inputs"]["eligible"] == 60 and sealed["universe"]["excluded"] == [
        {"symbol": "S059", "reason": "stale_filing"}]
    again = use_case.record_due(date(2026, 12, 23), spec=SPEC, sources=Sources(), store=store, inputs=dict)
    assert again["recorded"] is None and again["reason"] == "ya registrado"
    # March's window is missed; June records after sealing March as not recorded.
    late = use_case.record_due(date(2027, 6, 21), spec=SPEC, sources=Sources("2027-06-18"), store=store, inputs=dict)
    assert late["recorded"] == "2027-06-21" and late["not_recorded"] == ["registro-2027-03-21.json"]
    assert use_case.verify(store) | {"last_sha256": None} == {
        "records": 3, "recorded": 2, "not_recorded": 1, "last_signal": "2027-06-21", "last_sha256": None,
        "below_minimum": []}


def test_filings_pages_are_read_only_until_a_periodic_report_before_the_signal():
    from gabi.infrastructure.legacy.ensemble_live import filings_from_submissions

    def block(forms, dates):
        return {"accessionNumber": [f"a-{d}-{f}" for f, d in zip(forms, dates)], "form": forms, "filingDate": dates,
                "acceptanceDateTime": [f"{d}T16:00:00.000Z" for d in dates]}

    payload = {"sic": "6021", "filings": {"recent": block(["424B2"] * 3, ["2026-12-18", "2026-12-10", "2026-11-20"]),
                                          "files": [{"name": "CIK0000000001-submissions-001.json", "filingTo": "2026-11-19"},
                                                    {"name": "CIK0000000001-submissions-002.json", "filingTo": "2026-09-01"}]}}
    read = []

    def pages(name):
        read.append(name)
        return block(["10-Q", "424B2"], ["2026-11-03", "2026-10-01"])

    filings = filings_from_submissions("0000000001", payload, pages, 400, date(2026, 12, 21))
    assert read == ["CIK0000000001-submissions-001.json"]  # the second page is not needed
    assert set(filings.sic) == {"6021"} and "10-Q" in set(filings.form)
    assert filings.loc[filings.form == "10-Q", "source_url"].item().endswith("submissions-001.json")


def test_live_sources_use_the_frozen_sic_rule_and_scorer(tmp_path):
    from gabi import strategy_discovery
    from gabi.infrastructure.legacy.ensemble_live import LegacyEnsembleSources

    def submissions(cik):
        sic = {"0000000001": "3571", "0000000002": "6021", "0000000003": "7372"}[cik]
        filed = "2025-06-01" if cik == "0000000003" else "2026-11-03"  # 3: older than 400 days
        return {"sic": sic, "filings": {"recent": {"accessionNumber": [f"a{cik}"], "form": ["10-Q"],
                                                   "filingDate": [filed], "acceptanceDateTime": [f"{filed}T16:00:00.000Z"]}}}

    def counted(call, attempt):
        attempt.calls += 1
        return call()

    sources = LegacyEnsembleSources(tmp_path, submissions=submissions, pages=lambda name: {}, retry=counted,
                                    sessions=lambda start, end: [])
    frame = pd.DataFrame({"entity_id": ["cik:0000000001", "cik:0000000002", "cik:0000000003", None]},
                         index=["AAA", "BBB", "CCC", "DDD"])
    assert sources.divisions(frame.iloc[0:0], date(2026, 12, 21)).empty
    labels = sources.divisions(frame, date(2026, 12, 21))
    assert labels.division.to_dict() == {"AAA": "D", "BBB": "H", "CCC": "", "DDD": ""}
    assert labels.reason.to_dict() == {"AAA": "classified", "BBB": "classified", "CCC": "stale_filing",
                                       "DDD": "missing_identity"}

    rng = np.random.default_rng(3)
    ranking = pd.DataFrame(rng.uniform(1, 30, (12, 3)), columns=["pe", "pb", "ev_ebitda"],
                           index=[f"T{i:02d}" for i in range(12)])
    ranking["entity_id"] = [f"cik:{i:010d}" for i in range(12)]
    ranking["division"] = ["D", "H"] * 6
    for column in ("roic_persistence_mean", "operating_margin_persistence_mean", "historical_fcf_cagr",
                   "implied_fcf_growth"):
        ranking[column] = rng.normal(0, 1, 12)
    ranking[["roic_years", "operating_margin_years", "fcf_years", "fcf_positive_years"]] = 5, 5, 5, 4
    ranking[["expectations_discount_rate", "expectations_terminal_growth", "expectations_forecast_years"]] = .09, .025, 5
    scored = sources.score(ranking)
    pd.testing.assert_frame_equal(scored, strategy_discovery.score_frame(ranking))
    record = rules.record(date(2026, 12, 21), date(2026, 12, 21), scored, SPEC, previous=None, excluded={},
                          entry={}, evidence=[], inputs={})
    assert record["universe"]["size"] == 12 and not record["universe"]["evaluable"]  # below the minimum of 40


def test_record_files_are_never_overwritten_and_match_their_names(tmp_path):
    from gabi.infrastructure.storage.ensemble_records import FileEnsembleRecords

    store = FileEnsembleRecords(tmp_path / "registro")
    assert store.all() == [] and use_case.verify(store)["records"] == 0
    marker = rules.not_recorded(date(2026, 12, 21), date(2026, 12, 28), None)
    store.write(marker)
    with pytest.raises(FileExistsError):
        store.write(marker)
    assert store.all() == [marker] and use_case.verify(store)["not_recorded"] == 1
    (tmp_path / "registro" / "registro-2027-03-21.json").write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(ValueError, match="nombre"):
        store.all()


def test_entry_prices_are_bounded_by_the_signal_date(tmp_path):
    import sqlite3
    from contextlib import closing

    from gabi.infrastructure.legacy.ensemble_live import LegacyEnsembleSources
    from gabi.infrastructure.storage.cache_writes import SCHEMA

    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db:
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO prices (symbol,date,close,adj_close) VALUES (?,?,?,?)",
                       [("SPY", "2026-12-18", 600.0, 598.0), ("SPY", "2026-12-22", 610.0, 608.0)])
        db.commit()
    sources = LegacyEnsembleSources(tmp_path, submissions=dict, pages=dict, retry=None, sessions=None)
    assert sources.entry_prices(["SPY", "NONE"], date(2026, 12, 21)) == {
        "SPY": {"date": "2026-12-18", "close": 600.0, "adj_close": 598.0}}


def test_submissions_pages_only_accept_sec_page_names():
    from gabi.infrastructure.providers.sec_xbrl import SecXbrl

    with pytest.raises(ValueError, match="inválida"):
        SecXbrl("test").submissions_page("../other.json")


def test_edgar_acceptance_times_are_converted_from_utc_to_eastern():
    from gabi.infrastructure.legacy.ensemble_live import _eastern

    # Observed on EDGAR: a Form 4 dated 2024-01-03 accepted at 02:23Z, i.e. 21:23 EST the same day.
    assert _eastern("2024-01-04T02:23:05.000Z") == "2024-01-03 21:23:05"
    assert _eastern("2026-07-01T19:45:07.000Z") == "2026-07-01 15:45:07"  # EDT
    assert _eastern("") == "" and _eastern(None) == "" and _eastern("not a date") == ""
