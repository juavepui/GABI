import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
import requests

from gabi import config, data_fetch, edgar, edgar_sync, historical_tiingo, macro, price_sync, storage
from gabi import sync_state as sync
from gabi.infrastructure.legacy.periodic import build_periodic_tasks

NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_network_or_wait(monkeypatch):
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("No network allowed"))
    monkeypatch.setattr(sync.time, "sleep", lambda _: None)
    monkeypatch.setattr(config, "load_fred_key", lambda: "fake-key")


def prices(start="2024-01-02", end="2024-01-10"):
    index = pd.bdate_range(start, end)
    return pd.DataFrame({"Open": 10., "High": 10., "Low": 10., "Close": 10.,
                         "Adj Close": 10., "Volume": 100.}, index=index)


def test_new_prices_then_same_session_uses_no_network_and_no_duplicates(monkeypatch):
    calls = []

    def download(*args, **kwargs):
        calls.append(kwargs)
        return prices()

    monkeypatch.setattr(data_fetch.yf, "download", download)
    first = price_sync.run(["A", "A"], now=NOW)
    assert first["events"][0]["status"] == "new"
    assert first["events"][0]["new"] == 7
    again = price_sync.run(["A"], now=NOW)
    assert len(calls) == 1
    assert again["metrics"]["calls"] == 0
    assert again["events"][0]["skipped"]
    assert len(storage.get_prices("A")) == 7


def test_incremental_starts_at_last_valid_close_minus_overlap_and_classifies_revision(monkeypatch):
    storage.upsert_prices("A", prices(end="2024-01-09"))
    calls = []
    panel = prices()
    panel.loc[pd.Timestamp("2024-01-09"), "Volume"] = 150
    monkeypatch.setattr(data_fetch.yf, "download", lambda *a, **k: calls.append(k) or panel)
    event = price_sync.run(["A"], now=NOW)["events"][0]
    assert calls[0]["start"] == "2023-12-26"
    assert "period" not in calls[0]
    assert event["status"] == "revised"
    assert event["new"] == 1 and event["revised"] == 1
    assert storage.get_prices("A").loc["2024-01-09", "volume"] == 150


def test_adjustment_change_repairs_all_cached_history_before_advancing(monkeypatch):
    old = prices("2023-09-01", "2024-01-09")
    storage.upsert_prices("A", old)
    recent = prices()
    recent["Adj Close"] = 5
    complete = prices("2023-09-01")
    complete["Adj Close"] = 5
    calls = []
    monkeypatch.setattr(data_fetch.yf, "download", lambda *a, **k: calls.append(k) or (recent if len(calls) == 1 else complete))
    event = price_sync.run(["A"], now=NOW)["events"][0]
    assert len(calls) == 2
    assert calls[1]["start"] == "2023-09-01"
    assert "reparación histórica" in event["reason"]
    assert (storage.get_prices("A").adj_close == 5).all()


def test_failed_adjustment_repair_preserves_entire_series_and_checkpoint(monkeypatch):
    storage.upsert_prices("A", prices("2023-09-01", "2024-01-09"))
    old = storage.get_prices("A")
    recent = prices().assign(**{"Adj Close": 5.})
    monkeypatch.setattr(data_fetch.yf, "download", lambda *a, **k: recent)
    event = price_sync.run(["A"], now=NOW)["events"][0]
    assert event["status"] == "failed"
    assert "watermark" not in sync.get("yahoo", "ticker:A", "prices:A")
    pd.testing.assert_frame_equal(old, storage.get_prices("A"))


def test_history_repair_rejects_missing_cached_interior_session(monkeypatch):
    storage.upsert_prices("A", prices())
    panel = prices().assign(**{"Adj Close": 5.})
    panel = panel.drop(pd.Timestamp("2024-01-05"))
    monkeypatch.setattr(data_fetch.yf, "download", lambda *a, **k: panel)
    assert price_sync.run(["A"], now=NOW, full_refresh=True)["events"][0]["status"] == "failed"
    assert (storage.get_prices("A").adj_close == 10).all()


def test_interruption_after_data_write_resumes_without_double_insertion(monkeypatch):
    monkeypatch.setattr(data_fetch.yf, "download", lambda *a, **k: prices())
    original = storage.upsert_prices

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(storage, "upsert_prices", interrupted)
    with pytest.raises(KeyboardInterrupt):
        price_sync.run(["A"], now=NOW)
    assert not sync.get("yahoo", "ticker:A", "prices:A")
    monkeypatch.setattr(storage, "upsert_prices", original)
    event = price_sync.run(["A"], now=NOW)["events"][0]
    assert event["status"] == "unchanged" and event["new"] == 0
    assert sync.get("yahoo", "ticker:A", "prices:A")["watermark"] == "2024-01-10"
    assert len(storage.get_prices("A")) == 7


def test_explicit_full_refresh_uses_max_and_rejects_partial_live_bar(monkeypatch):
    calls = []
    panel = prices(end="2024-01-11")
    monkeypatch.setattr(data_fetch.yf, "download", lambda *a, **k: calls.append(k) or panel)
    price_sync.run(["A"], now=NOW, full_refresh=True)
    assert calls[0]["period"] == "max"
    assert storage.get_prices("A").index.max() == pd.Timestamp("2024-01-10")


def test_incomplete_invalid_payload_never_moves_watermark(monkeypatch):
    panel = prices()
    panel.iloc[-1, panel.columns.get_loc("Adj Close")] = np.nan
    monkeypatch.setattr(data_fetch.yf, "download", lambda *a, **k: panel)
    assert price_sync.run(["A"], now=NOW)["events"][0]["status"] == "failed"
    assert storage.get_prices("A").empty


def test_transient_retry_and_failed_attempt_preserve_successful_checkpoint():
    sync.Attempt("test", "A", "data").finish("new", state={"watermark": "2024-01-01"}, new=1)
    tries = []

    def network():
        tries.append(1)
        if len(tries) < 3:
            raise requests.Timeout()
        return "ok"

    attempt = sync.Attempt("test", "A", "data")
    assert sync.retry(network, attempt) == "ok"
    assert attempt.calls == 3
    attempt.finish("failed", state={"watermark": "2099-01-01"}, reason="api_key=secret&token=hidden")
    cp = sync.get("test", "A", "data")
    assert cp["watermark"] == "2024-01-01"
    assert "secret" not in cp["error"] and "hidden" not in cp["error"]
    assert sync.due(cp, 24)


def facts(value=100, accn="a1", filed="2020-02-01"):
    return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"start": "2019-01-01", "end": "2019-12-31", "val": value,
         "accn": accn, "filed": filed, "form": "10-K", "fp": "FY", "fy": 2019}]}}}}}


def submissions(accn="a1", filed="2020-02-01"):
    return {"cik": 1, "filings": {"recent": {"form": ["10-K"], "filingDate": [filed],
                                            "accessionNumber": [accn], "primaryDocument": ["doc.htm"]}}}


def test_sec_unchanged_filings_skip_companyfacts_and_keep_provenance(monkeypatch):
    calls = []
    monkeypatch.setattr(edgar, "fetch_submissions", lambda cik: submissions())
    monkeypatch.setattr(edgar, "fetch_company_facts", lambda cik: calls.append(cik) or facts())
    first = edgar_sync.run_one("A", "1")
    original = edgar.get_edgar_facts
    monkeypatch.setattr(edgar, "get_edgar_facts", lambda *a, **k: pytest.fail("No historical read without changed facts"))
    again = edgar_sync.run_one("A", "1")
    monkeypatch.setattr(edgar, "get_edgar_facts", original)
    assert first["new"] == 1 and again["status"] == "unchanged"
    assert len(calls) == 1 and again["calls"] == 1
    stored = edgar.get_edgar_facts("A", entity_id="cik:0000000001")
    assert stored.iloc[0].accn == "a1" and stored.iloc[0].filed_date == "2020-02-01"


def test_sec_same_accession_revision_and_new_amendment_are_separate(monkeypatch):
    monkeypatch.setattr(edgar, "fetch_submissions", lambda cik: submissions())
    monkeypatch.setattr(edgar, "fetch_company_facts", lambda cik: facts())
    edgar_sync.run_one("A", "1")
    monkeypatch.setattr(edgar, "fetch_company_facts", lambda cik: facts(110))
    revised = edgar_sync.run_one("A", "1", full_refresh=True)
    assert revised["revised"] == 1 and revised["new"] == 0
    monkeypatch.setattr(edgar, "fetch_submissions", lambda cik: submissions("a2", "2020-05-01"))
    monkeypatch.setattr(edgar, "fetch_company_facts", lambda cik: facts(120, "a2", "2020-05-01"))
    new = edgar_sync.run_one("A", "1")
    assert new["new"] == 1
    stored = edgar.get_edgar_facts("A", entity_id="cik:0000000001")
    assert set(stored.accn) == {"a1", "a2"}


def test_sec_failed_companyfacts_retries_same_filing_on_resume(monkeypatch):
    monkeypatch.setattr(edgar, "fetch_submissions", lambda cik: submissions())
    monkeypatch.setattr(edgar, "fetch_company_facts", lambda cik: (_ for _ in ()).throw(ValueError("bad JSON")))
    with pytest.raises(ValueError):
        edgar_sync.run_one("A", "1")
    cp = sync.get("sec", "cik:0000000001", "facts:A")
    assert "filings_hash" not in cp
    monkeypatch.setattr(edgar, "fetch_company_facts", lambda cik: facts())
    assert edgar_sync.run_one("A", "1")["status"] == "new"


def test_sec_checkpoint_failure_retries_despite_recent_metrics(monkeypatch):
    edgar.upsert_edgar_metrics("A", "1", {})
    edgar.upsert_edgar_facts("A", [{"tag": "Revenues", "unit": "USD", "start_date": "2019-01-01",
                                   "end_date": "2019-12-31", "val": 100, "form": "10-K", "fp": "FY", "fy": 2019,
                                   "filed_date": "2020-02-01", "accn": "a1"}], cik="1")
    sync.Attempt("sec", "cik:0000000001", "facts:A").finish("failed", reason="interrupted")
    monkeypatch.setattr(edgar, "get_cik_map", lambda **k: pd.DataFrame({"symbol": ["A"], "cik": ["0000000001"], "title": ["A"]}))
    monkeypatch.setattr(edgar, "fetch_submissions", lambda cik: submissions())
    monkeypatch.setattr(edgar, "fetch_company_facts", lambda cik: facts())
    assert edgar.ensure_edgar_data(["A"])["edgar_refreshed"] == 1
    assert sync.get("sec", "cik:0000000001", "facts:A")["status"] == "unchanged"


def test_cik_map_lookup_without_explicit_frame_and_full_refresh(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar, "CIK_CACHE", tmp_path / "map.csv")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"0": {"ticker": "A", "cik_str": 1, "title": "Firm"}}

    calls = []
    monkeypatch.setattr(edgar.requests, "get", lambda *a, **k: calls.append(1) or Response())
    assert edgar.get_cik_for_symbol("A")[0] == "0000000001"
    assert edgar.get_cik_for_symbol("A")[0] == "0000000001"
    assert len(calls) == 1
    edgar.get_cik_map(force_refresh=True)
    assert len(calls) == 2


def test_fred_overlap_revision_withdrawal_and_monthly_full_audit(monkeypatch):
    monkeypatch.setattr(macro, "SERIES", {"TEST": {"units_param": "lin"}})
    calls = []
    payload = [("2020-01-01", 1.), ("2024-01-01", 2.)]
    monkeypatch.setattr(macro, "fetch_series", lambda *a, **k: calls.append(k) or payload)
    macro.ensure_macro_data(force=True)
    assert calls[0]["observation_start"] == "1776-07-04"
    payload = [("2024-01-01", None), ("2024-02-01", 3.)]
    macro.ensure_macro_data(force=True)
    assert calls[1]["observation_start"] == "2022-11-27"
    assert macro.get_series_history("TEST").loc["2024-01-01", "value"] != 2
    event = sync.events_since()[-1]
    assert event["new"] == 1 and event["revised"] == 1
    # No work on an immediate routine run.
    macro.ensure_macro_data()
    assert len(calls) == 2
    cp = sync.get("fred", "TEST", "observations:lin")
    cp["full_audited_at"] = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    sync.Attempt("fred", "TEST", "observations:lin").finish("unchanged", state=cp)
    macro.ensure_macro_data(force=True)
    assert calls[-1]["observation_start"] == "1776-07-04"


def test_yahoo_fundamentals_snapshot_is_unchanged_on_second_forced_call(monkeypatch):
    monkeypatch.setattr(data_fetch, "_fetch_fundamentals_attempt", lambda s: ({"marketCap": 10}, pd.DataFrame(), pd.DataFrame()))
    assert not data_fetch.fetch_fundamentals_batch(["A"])
    assert not data_fetch.fetch_fundamentals_batch(["A"])
    events = sync.events_since()
    assert [e["status"] for e in events] == ["new", "unchanged"]


def test_periodic_task_integrates_checkpoints_and_full_refresh(monkeypatch):
    from gabi import screener

    flags = []
    monkeypatch.setattr(screener, "get_universe", lambda **k: flags.append(k) or pd.DataFrame({"symbol": ["A"]}))
    monkeypatch.setattr(screener, "refresh_data", lambda *a, **k: flags.append(k) or {"failed": {}})
    monkeypatch.setattr(macro, "ensure_macro_data", lambda **k: {"ok": True})
    first = build_periodic_tasks(config.DATA_DIR).refresh_data()
    again = build_periodic_tasks(config.DATA_DIR).refresh_data()
    assert flags[0] == {"force_refresh": True}
    assert flags[2] == {"force_refresh": False}
    assert first["sync"]["calls"] == 1 and again["sync"]["calls"] == 0
    build_periodic_tasks(config.DATA_DIR).refresh_data(full_refresh=True)
    assert flags[-1] == {"full_refresh": True}


def test_periodic_universe_failure_keeps_the_previous_checkpoint(monkeypatch):
    from gabi import screener

    sync.Attempt("universe", "SP500", "members").finish("new", state={"fingerprint": "previous"})
    monkeypatch.setattr(screener, "get_universe", lambda **k: (_ for _ in ()).throw(RuntimeError("no source")))
    with pytest.raises(RuntimeError):
        build_periodic_tasks(config.DATA_DIR).refresh_data(full_refresh=True)
    cp = sync.get("universe", "SP500", "members")
    assert cp["status"] == "failed" and cp["fingerprint"] == "previous"


def test_tiingo_second_import_does_not_parse_or_import_complete_files(tmp_path, monkeypatch):
    monkeypatch.setattr(historical_tiingo, "DIRECTORY", tmp_path)
    rows = [{"date": "2012-01-02", "open": 10, "high": 10, "low": 10, "close": 10, "adjClose": 10, "volume": 100}]
    path = tmp_path / "A.json"
    path.write_text(json.dumps(rows))
    assert historical_tiingo.import_cached()["accepted"] == 1
    monkeypatch.setattr(historical_tiingo.historical_archive, "import_price_chunk", lambda *a: pytest.fail("No import on repeat"))
    assert historical_tiingo.import_cached()["accepted"] == 0
    path.write_text(json.dumps([{**rows[0], "close": 11}]))
    with pytest.raises(ValueError, match="alterado"):
        historical_tiingo.import_cached()
