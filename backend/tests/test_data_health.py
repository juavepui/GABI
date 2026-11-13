"""The old Calidad de los datos as the explicit data_health job (legacy readers create schema while reading)."""

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gabi import config
from gabi.application.administration.data_health import build_data_health, normalize_data_health
from gabi.application.errors import QueryError
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app

TODAY = date(2026, 10, 1)


class FakeSource:
    def __init__(self):
        self.calls = []

    def universe(self):
        return [{"symbol": "AAA", "name": "Alpha"}, {"symbol": "BBB", "name": None}]

    def summary(self, symbols):
        self.calls.append(("summary", symbols))
        return {"n_symbols": len(symbols), "sources": {"prices": {"coverage": float("nan")}}}

    def recent_errors(self):
        return [{"source": "yahoo_precio", "symbol": "BBB", "reason": "x", "occurred_at": "2026-09-30"},
                {"source": "sec_edgar", "symbol": "AAA", "reason": "y", "occurred_at": "2026-09-29"}]

    def provenance(self, symbol, as_of):
        return {"symbol": symbol, "reference": as_of, "fetched_at": datetime(2026, 9, 30, 8, tzinfo=UTC),
                "sessions": np.int64(250)}

    def identity(self, symbol, as_of):
        return {"resolution": {"status": "resolved"}, "name_candidates": []}

    def identities(self, symbols, as_of):
        return [{"symbol": s, "cik": "1" if s == "AAA" else None} for s in symbols]

    def archive_sources(self):
        return [{"source": "m", "data": "Composición", "rows": 3, "first": "1996-01-02", "last": "2015-12-31"}]

    def archive_quarterly(self):
        return [{"date": "2009-12-31", "members": 1}, {"date": "2010-03-31", "members": 2},
                {"date": "2016-03-31", "members": 3}]

    def archive_members(self, source, as_of):
        return {"symbols": ["AAA"], "source_date": "2009-12-31" if as_of == "2010-01-04" else as_of}

    def archive_prices(self, source, symbol, start, end):
        self.calls.append(("prices", start, end))
        return [{"date": "2010-01-04", "close": 1.0, "adj_close": 1.0, "volume": 5}]


def _build(options, source=None):
    return build_data_health(normalize_data_health(options), source or FakeSource(), TODAY)


def test_scopes_keep_the_old_page_content_and_json_safe_values():
    universe = _build({"scope": "universe"})
    assert universe["summary"]["sources"]["prices"]["coverage"] is None
    assert universe["recent_errors_total"] == 2 and universe["universe"][0]["name"] == "Alpha"
    company = _build({"scope": "company", "symbol": " bbb ", "as_of": "2026-09-30"})
    assert company["provenance"]["fetched_at"] == "2026-09-30T08:00:00+00:00"
    assert type(company["provenance"]["sessions"]) is int
    assert company["symbol"] == "BBB" and [row["symbol"] for row in company["recent_errors"]] == ["BBB"]
    assert _build({"scope": "identities", "as_of": "2026-09-30"})["without_cik"] == 1


def test_archive_opens_only_2010_2015():
    archive = _build({"scope": "archive"})
    assert [row["date"] for row in archive["quarterly"]] == ["2010-03-31"]
    source = FakeSource()
    _build({"scope": "archive_prices", "source": "p", "symbol": "ATVI"}, source)
    assert source.calls == [("prices", "2010-01-01", "2016-01-01")]
    for as_of in ("2009-12-31", "2016-01-04"):
        with pytest.raises(QueryError):
            normalize_data_health({"scope": "archive_members", "source": "m", "as_of": as_of})
    # The membership in force on a 2010 date may have been recorded in 2009: it is still 2010 information.
    members = _build({"scope": "archive_members", "source": "m", "as_of": "2010-01-04"})
    assert (members["source_date"], members["symbols"]) == ("2009-12-31", ["AAA"])


@pytest.mark.parametrize("options", [{"scope": "other"}, {"scope": "universe", "symbol": "AAA"},
                                     {"scope": "company", "symbol": "bad symbol", "as_of": "2026-09-30"},
                                     {"scope": "company", "symbol": "AAA"},
                                     {"scope": "archive_prices", "source": "two words", "symbol": "AAA"}])
def test_invalid_options_are_rejected(options):
    with pytest.raises(QueryError):
        normalize_data_health(options)


def test_future_dates_are_rejected():
    with pytest.raises(QueryError):
        _build({"scope": "identities", "as_of": "2026-10-02"})


@pytest.fixture
def client():
    with TestClient(create_app(Settings(config.DATA_DIR))) as test_client:
        yield test_client


def _run(client, health, key):
    job = client.post("/api/v1/jobs", json={"kind": "data_health", "idempotency_key": key, "health": health})
    assert job.status_code == 202, job.text
    assert Worker(SqliteJobs(config.DATA_DIR), LegacyExecutor(Settings(config.DATA_DIR)), config.DATA_DIR).run_once()
    return client.get(f"/api/v1/jobs/{job.json()['id']}/result")


def test_worker_runs_the_legacy_page_over_temporary_data(client):
    pd.DataFrame({"symbol": ["AAA", "BBB"], "name": ["Alpha", "Beta"]}).to_csv(config.SP500_CACHE, index=False)
    universe = _run(client, {"scope": "universe"}, "health-universe").json()
    assert universe["summary"]["n_symbols"] == 2 and universe["recent_errors"] == []
    assert set(universe["summary"]["sources"]) >= {"prices", "fundamentals", "edgar", "fred"}
    company = _run(client, {"scope": "company", "symbol": "AAA", "as_of": "2025-01-02"}, "health-company").json()
    assert company["provenance"]["prices"]["adjusted_sessions"] == 0
    assert company["identity"]["resolution"]["status"] == "unresolved"
    assert _run(client, {"scope": "archive"}, "health-archive").json()["sources"] == []
    response = client.post("/api/v1/jobs", json={"kind": "data_health", "idempotency_key": "health-bad",
                                                 "health": {"scope": "archive_members", "source": "m",
                                                            "as_of": "2005-01-03"}})
    assert response.status_code == 422
