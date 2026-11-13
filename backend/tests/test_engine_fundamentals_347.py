"""#347: GABI-MF-v5 scores the Composite's company metrics as the tested historical engine computes them."""

import math
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.application.administration.periodic import PeriodicTasks
from gabi.domain.market import engine_fundamentals as rules
from gabi.domain.market.metric_sources import METRIC_SOURCES, metric_sources
from gabi.infrastructure.legacy import periodic as legacy_periodic
from gabi.infrastructure.model_versions import GABI_MF_V4, GABI_MF_V5
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage import ranking_revision
from gabi.infrastructure.storage.engine_fundamentals import SqliteEngineFundamentals
from gabi_api.bootstrap import create_app

SYMBOLS = [f"T{i:03d}" for i in range(12)]
OVERRIDDEN = ("pe", "pb", "ev_ebitda", "operating_margin", "debt_to_equity")


def _engine_table(symbols=SYMBOLS) -> pd.DataFrame:
    """Distinct, recognisable values: 1000 + position for each metric, NaN for T001's P/E."""
    frame = pd.DataFrame({metric: [1000.0 + position + index / 100 for index in range(len(symbols))]
                          for position, metric in enumerate(rules.METRICS)}, index=symbols)
    frame.loc["T001", "pe"] = float("nan")
    return frame


def _store(root: Path, as_of: date = TODAY, symbols=SYMBOLS) -> None:
    SqliteEngineFundamentals(root / "gabi.db").replace(rules.rows(_engine_table(symbols), as_of), datetime.now(UTC))


def _ranking(root: Path, model=GABI_MF_V5) -> pd.DataFrame:
    app = create_app(Settings(root), today=lambda: TODAY, model=model)
    repository = app.state.market.repository
    try:
        return repository.ranking(dict(model.weights), TODAY).table
    finally:
        repository.close()


@pytest.fixture
def root(tmp_path):
    seed_fixture(tmp_path, companies=12)
    return tmp_path


def test_stored_rows_are_used_only_while_current_and_of_this_rule():
    row = {"symbol": "A", "as_of": "2026-11-06", "rule_version": rules.RULE_VERSION,
           **{metric: 1.5 for metric in rules.METRICS}, "pe": float("nan")}
    today = date(2026, 11, 6)
    assert rules.stored(row, today) == {**dict.fromkeys(rules.METRICS, 1.5), "pe": None}
    assert rules.stored(row, today + timedelta(days=rules.MAX_AGE_DAYS))["pb"] == 1.5
    empty = dict.fromkeys(rules.METRICS)
    assert rules.stored(row, today + timedelta(days=rules.MAX_AGE_DAYS + 1)) == empty  # Outdated.
    assert rules.stored(row, today - timedelta(days=1)) == empty  # From the future.
    assert rules.stored({**row, "rule_version": "other"}, today) == empty
    assert rules.stored({**row, "as_of": "nonsense"}, today) == empty
    assert rules.stored(None, today) == empty


def test_rows_keep_the_eight_metrics_finite_or_missing():
    rows = rules.rows(_engine_table(["A", "T001"]).assign(extra=1), date(2026, 11, 6))
    assert [row["symbol"] for row in rows] == ["A", "T001"]
    assert set(rows[0]) == {"symbol", "as_of", "rule_version", *rules.METRICS}
    assert rows[1]["pe"] is None and rows[0]["rule_version"] == rules.RULE_VERSION


def test_the_table_is_replaced_whole_and_never_created_with_its_database(root, tmp_path_factory):
    _store(root, symbols=SYMBOLS)
    _store(root, symbols=SYMBOLS[:3])
    with sqlite3.connect(root / "gabi.db") as db:
        assert db.execute("SELECT count(*) FROM engine_fundamentals").fetchone()[0] == 3
    missing = tmp_path_factory.mktemp("empty") / "gabi.db"
    with pytest.raises(FileNotFoundError):
        SqliteEngineFundamentals(missing).replace([], datetime.now(UTC))
    assert not missing.exists()


def test_v5_scores_the_engine_values_and_never_falls_back_to_yahoo(root):
    yahoo = _ranking(root, GABI_MF_V4)
    _store(root, symbols=SYMBOLS[:-1])  # The last company has no engine row.
    table = _ranking(root)
    engine = _engine_table()
    for symbol in SYMBOLS[:-1]:
        for metric in rules.METRICS:
            expected = engine.loc[symbol, metric]
            value = table.loc[symbol, metric]
            assert (math.isnan(expected) and pd.isna(value)) or value == expected, (symbol, metric)
    assert table.loc[SYMBOLS[-1], list(rules.METRICS)].isna().all()  # Missing, not Yahoo's value.
    assert yahoo.loc[SYMBOLS[-1], list(OVERRIDDEN)].notna().any()
    assert table.loc["T001", "pe"] != yahoo.loc["T001", "pe"] or pd.isna(table.loc["T001", "pe"])


def test_v5_without_current_rows_has_no_company_metrics(root):
    _store(root, as_of=TODAY - timedelta(days=rules.MAX_AGE_DAYS + 1))
    table = _ranking(root)
    assert table[list(rules.METRICS)].isna().all().all()


def test_earlier_versions_ignore_the_engine_table(root):
    before = _ranking(root, GABI_MF_V4)
    _store(root)
    after = _ranking(root, GABI_MF_V4)
    pd.testing.assert_frame_equal(before, after, check_exact=True)


def test_writing_the_engine_table_invalidates_the_ranking(root):
    _store(root)
    ranking_revision.install(root / "gabi.db")
    app = create_app(Settings(root), today=lambda: TODAY, model=GABI_MF_V5)
    repository = app.state.market.repository
    try:
        first = repository.ranking(dict(GABI_MF_V5.weights), TODAY)
        _store(root, symbols=SYMBOLS[:5])
        second = repository.ranking(dict(GABI_MF_V5.weights), TODAY)
    finally:
        repository.close()
    assert second.revision != first.revision and not second.cache_hit
    assert second.table.loc[SYMBOLS[6], list(rules.METRICS)].isna().all()


def test_the_company_page_says_the_v5_metrics_come_from_the_sec(root):
    _store(root)
    with TestClient(create_app(Settings(root), today=lambda: TODAY, model=GABI_MF_V5)) as client:
        sources = client.get("/api/v1/companies/T000").json()["metric_sources"]
    for metric in OVERRIDDEN:
        assert sources[metric]["source"] == "sec_10k" and sources[metric]["period"] == "fiscal_year"
    assert sources["momentum_12m"]["source"] == "prices"
    assert metric_sources(GABI_MF_V4.metrics_version) == METRIC_SOURCES
    with TestClient(create_app(Settings(root), today=lambda: TODAY, model=GABI_MF_V4)) as client:
        assert client.get("/api/v1/companies/T000").json()["metric_sources"]["pe"]["source"] == "yahoo"


def test_v5_is_the_tested_configuration():
    assert GABI_MF_V5.metrics_version == rules.METRICS_VERSION
    assert dict(GABI_MF_V5.weights) == dict(GABI_MF_V4.weights)
    assert GABI_MF_V5.technical == GABI_MF_V4.technical and GABI_MF_V5.input_checks is None
    assert (GABI_MF_V5.benchmark_symbol, GABI_MF_V5.risk_free_rate) == ("SPY", 0.04)


def test_the_ledger_hashes_the_code_that_scores_v5():
    base = Path(legacy_periodic.__file__).parents[2]
    for relative in legacy_periodic.ACTIVE_MODEL_CODE:
        assert (base / relative).is_file(), relative
    assert "domain/market/engine_fundamentals.py" in legacy_periodic.ACTIVE_MODEL_CODE


def test_the_daily_task_stores_the_engine_metrics_before_the_ledger_and_survives_a_failure():
    class Operations:
        def __init__(self, fail):
            self.fail, self.calls = fail, []

        def verify_ledger(self):
            return {"ok": True}

        def install_ranking_revision(self):
            return {"instalado": True}

        def record_engine_fundamentals(self):
            self.calls.append("engine")
            if self.fail:
                raise OSError("SEC caída")
            return {"guardadas": 503}

        def capture_ledger(self, error, maintenance):
            self.calls.append("ledger")
            return {"seq": 1, "record_hash": "h", "payload": {"status": "OK"}}

        def capture_active_ledger(self, error, maintenance):
            self.calls.append("active")
            return None

        def record_scores(self):
            return {}

        def save_ranking(self):
            return {}

    def run(fail):
        operations = Operations(fail)
        tasks = PeriodicTasks(type("Store", (), {"log": lambda self, event: None})(), operations, None,
                              lambda: pd.Timestamp("2026-11-07T05:00Z").to_pydatetime(), lambda: 0.0, lambda: 0.0)
        tasks.status = lambda: {}
        tasks.record_due = lambda: []
        tasks.smallmid_step = lambda: {}
        return operations, tasks.run(refresh=False)

    operations, report = run(False)
    assert operations.calls == ["engine", "ledger", "active"] and report["fundamentales_motor"] == {"guardadas": 503}
    operations, report = run(True)
    assert report["fundamentales_motor"] == {"error": "OSError: SEC caída"}
    assert report["ledger"]["status"] == "OK" and "error" not in report
