import builtins
import hashlib
import json
import socket
import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest
import requests
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import app_mode, config, identity, screener, storage
from gabi.domain.market.selection import RankingFilter, filter_ranking
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


@pytest.fixture
def api(tmp_path):
    seed_fixture(tmp_path)
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, app.state.market.repository, tmp_path


def hashes(root):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir() if path.is_file()}


def test_health_and_openapi_without_creating_data(tmp_path):
    absent = tmp_path / "absent"
    with TestClient(create_app(Settings(absent), today=lambda: TODAY)) as client:
        assert client.get("/api/v1/health").json()["status"] == "ok"
        contract = client.get("/openapi.json").json()
        assert set(contract["paths"]) == {"/api/v1/health", "/api/v1/model", "/api/v1/learn/metrics", "/api/v1/data/status",
                                         "/api/v1/ranking", "/api/v1/companies/{symbol}",
                                         "/api/v1/comparison", "/api/v1/portfolio/plan",
                                         "/api/v1/administration/settings", "/api/v1/administration/weights",
                                         "/api/v1/administration/mode",
                                         "/api/v1/jobs",
                                         "/api/v1/jobs/{job_id}", "/api/v1/jobs/{job_id}/cancel",
                                         "/api/v1/jobs/{job_id}/result",
                                         "/api/v1/portfolio/journal",
                                         "/api/v1/portfolio/journal/{entry_id}/review",
                                         "/api/v1/portfolio/journal/{entry_id}/delete",
                                         "/api/v1/market/macro", "/api/v1/market/snapshots",
                                         "/api/v1/market/snapshots/{snapshot_id}/earnings",
                                         "/api/v1/market/signals", "/api/v1/market/signals/compare",
                                         "/api/v1/market/signals/filings/record",
                                         "/api/v1/portfolio/simulations",
                                         "/api/v1/portfolio/simulations/{portfolio_id}",
                                         "/api/v1/portfolio/simulations/{portfolio_id}/trades",
                                         "/api/v1/portfolio/simulations/{portfolio_id}/undo",
                                         "/api/v1/portfolio/simulations/{portfolio_id}/result",
                                         "/api/v1/portfolio/decisions",
                                         "/api/v1/portfolio/decisions/{plan_id}",
                                         "/api/v1/portfolio/decisions/{plan_id}/progress",
                                             "/api/v1/portfolio/decisions/{plan_id}/rename",
                                             "/api/v1/portfolio/decisions/{plan_id}/delete",
                                             "/api/v1/research/overview", "/api/v1/research/trials",
                                             "/api/v1/research/historical/{job_id}",
                                             "/api/v1/evidence", "/api/v1/ranking/stability", "/api/v1/ranking/coverage",
                                             "/api/v1/market/snapshots/{snapshot_id}/progress",
                                             "/api/v1/companies/{symbol}/research",
                                             "/api/v1/administration/keys/{source}",
                                             "/api/v1/companies/{symbol}/filing-changes",
                                             "/api/v1/market/snapshots/{snapshot_id}/rename",
                                             "/api/v1/companies/{symbol}/evidence",
                                             "/api/v1/companies/{symbol}/evidence.json",
                                             "/api/v1/research/blind-validations",
                                             "/api/v1/research/blind-validations/{validation_id}/break-seal",
                                             "/api/v1/research/blind-rebalances/{job_id}",
                                             "/api/v1/research/portfolio-lab/{job_id}",
                                             "/api/v1/research/blind-performance/{job_id}",
                                             "/api/v1/research/blind-exports/{job_id}",
                                             "/api/v1/research/experiments",
                                             "/api/v1/research/experiments/{experiment_id}",
                                             "/api/v1/research/experiments/{experiment_id}/delete",
                                             "/api/v1/research/experiments/{experiment_id}/tail-risk",
                                             "/api/v1/research/experiment-statistics/deflated-sharpe",
                                             "/api/v1/research/experiment-pbo/{job_id}",
                                             "/api/v1/research/saved-audits",
                                             "/api/v1/research/live-ledger",
                                             "/api/v1/research/live-ledger/decisions/{seq}",
                                             "/api/v1/research/live-ledger/decisions/{seq}/event.json",
                                             "/api/v1/research/live-ledger/evaluations",
                                             "/api/v1/research/live-forward/{job_id}",
                                             "/api/v1/research/saved-audits/overfitting",
                                             "/api/v1/research/saved-audits/factor-benchmark",
                                             "/api/v1/research/saved-audits/factor-stability",
                                             "/api/v1/research/saved-audits/block-bootstrap",
                                             "/api/v1/research/saved-audits/rank-stability",
                                             "/api/v1/research/saved-audits/{audit}/files/{filename}",
                                             "/api/v1/research/experiment-bootstrap/{job_id}",
                                             "/api/v1/research/experiment-bootstrap/{job_id}/distributions.csv",
                                             "/api/v1/research/estimate-captures",
                                             "/api/v1/research/estimate-analysis/{job_id}",
                                             "/api/v1/research/backtests/{job_id}",
                                             "/api/v1/research/backtests/{job_id}/diagnostics",
                                             "/api/v1/research/backtest-factors/{job_id}",
                                             "/api/v1/research/preparations/{job_id}",
                                             "/api/v1/research/historical/{job_id}/table",
                                             "/api/v1/research/historical-outcomes/{job_id}",
                                             "/api/v1/research/factors/{job_id}",
                                             "/api/v1/research/published-factors",
                                             "/api/v1/research/published-factors/exports/{name}"}
        assert contract["components"]["schemas"]["Metric"]["required"] == ["value", "unit"]
        assert client.get("/api/v1/ranking").json()["data"]["status"] == "empty"
        assert client.get("/api/v1/companies/TEST").status_code == 404
    assert not absent.exists()


def test_typed_units_nulls_dates_identity_and_provenance(api):
    client, _, _ = api
    response = client.get("/api/v1/ranking?hide_no_data=false")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["model"]["independent_advantage_demonstrated"] is False
    assert payload["risk_free_rate"] == {"value": .0425, "unit": "fraction"}
    items = {item["symbol"]: item for item in payload["items"]}
    assert items["EMPTY"]["metrics"]["composite_score"]["value"] is None
    assert items["T000"]["metrics"]["market_cap"] == {"value": 1e9, "unit": "USD"}
    assert items["T000"]["metrics"]["debt_to_equity"] == {"value": 30., "unit": "percent"}
    assert items["T000"]["metrics"]["operating_margin"]["unit"] == "fraction"
    assert items["T000"]["metrics"]["confidence"]["unit"] == "points_0_100"
    assert items["BRK-A"]["identity"]["entity_id"] == items["BRK-B"]["identity"]["entity_id"] == "issuer"
    assert items["T000"]["identity"]["status"] == "unresolved"
    assert items["T000"]["provenance"]["price_date"] == TODAY.isoformat()
    assert items["T000"]["provenance"]["historical_point_in_time"] is False
    assert payload["data"]["warnings"] == ["incomplete_coverage"]
    json.dumps(payload, allow_nan=False)


def test_company_uses_universe_scores_and_bounded_chart(api):
    client, _, _ = api
    ranking = client.get("/api/v1/ranking?hide_no_data=false").json()
    row = next(item for item in ranking["items"] if item["symbol"] == "BRK-B")
    detail = client.get("/api/v1/companies/brk.b?bars=10").json()
    assert detail["company"] == row
    assert len(detail["prices"]) == 10
    assert detail["prices"][-1]["date"] == TODAY.isoformat()
    assert detail["prices"] == sorted(detail["prices"], key=lambda point: point["date"])


def test_streamlit_and_api_match_pre_migration_golden_all_metrics(api, monkeypatch):
    client, _, root = api
    monkeypatch.setattr(config, "DB_PATH", root / "gabi.db")
    universe = pd.read_csv(root / "sp500_constituents.csv")
    table = screener.build_screener_table(universe, app_mode.FROZEN_WEIGHTS)
    expected = json.loads((Path(__file__).parent / "fixtures/api-ranking-v1.json").read_text(encoding="utf-8"))
    actual = json.loads(table.to_json(orient="split", double_precision=15, date_format="iso"))
    assert actual["columns"] == expected["columns"]
    assert actual["index"] == expected["index"]
    for row, reference in zip(actual["data"], expected["data"], strict=True):
        for value, target in zip(row, reference, strict=True):
            if isinstance(target, float):
                assert value == pytest.approx(target, rel=1e-12, abs=1e-12)
            else:
                assert value == target
    payload = client.get("/api/v1/ranking?hide_no_data=false").json()
    assert [item["symbol"] for item in payload["items"]] == list(table.index)
    for item in payload["items"]:
        for metric, wire in item["metrics"].items():
            raw = table.loc[item["symbol"], metric]
            assert wire["value"] is None if pd.isna(raw) else wire["value"] == pytest.approx(raw)


@pytest.mark.parametrize("query,filters,offset,limit", [
    ("search=t00&limit=3&offset=2", RankingFilter(search="t00"), 2, 3),
    ("sectors=Financials&hide_no_data=false", RankingFilter(sectors=("Financials",), hide_no_data=False), 0, 100),
    ("min_market_cap=9000000000", RankingFilter(min_market_cap=9e9), 0, 100),
    ("golden_cross_only=true", RankingFilter(golden_cross_only=True), 0, 100),
    ("search=[", RankingFilter(search="["), 0, 100),
    ("offset=1000", RankingFilter(), 1000, 100),
])
def test_selection_filters_limits_and_literal_search(api, query, filters, offset, limit):
    client, repository, _ = api
    base = repository.ranking(app_mode.FROZEN_WEIGHTS, TODAY).table
    selected = filter_ranking(base, filters)
    payload = client.get("/api/v1/ranking?" + query).json()
    assert payload["total"] == len(selected)
    assert [item["symbol"] for item in payload["items"]] == list(selected.iloc[offset:offset + limit].index)


@pytest.mark.parametrize("query", ["mode=RESEARCH", "value=.25&quality=.25&momentum=.25&risk=.25"])
def test_investor_restrictions_cannot_be_bypassed_by_url(api, query):
    client, _, root = api
    (root / "weights.json").write_text(json.dumps({"value": .25, "quality": .25, "momentum": .25, "risk": .25}))
    assert client.get("/api/v1/ranking?" + query).status_code == 403
    model = client.get("/api/v1/model").json()
    assert model["weights"] == app_mode.FROZEN_WEIGHTS
    assert model["status"] == "FROZEN"


def test_research_alternatives_are_explicit_and_do_not_write(api):
    client, _, root = api
    (root / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    before = hashes(root)
    payload = client.get("/api/v1/ranking?value=.25&quality=.25&momentum=.25&risk=.25").json()
    assert payload["model"]["status"] == "EXPERIMENTAL"
    assert hashes(root) == before


def test_mode_command_is_explicit_persistent_and_compatible_with_legacy(api, monkeypatch):
    client, _, root = api
    weights = {"value": .25, "quality": .25, "momentum": .25, "risk": .25}
    (root / "weights.json").write_text(json.dumps(weights))
    saved_weights = (root / "weights.json").read_bytes()
    monkeypatch.setattr(app_mode, "MODE_PATH", root / "app_mode.json")
    monkeypatch.setattr(config, "DATA_DIR", root)

    assert client.get("/api/v1/model").json()["mode"] == "INVESTOR"
    invalid = client.post("/api/v1/administration/mode", json={"mode": "ADMIN"})
    assert invalid.status_code == 422
    assert not (root / "app_mode.json").exists()

    research = client.post("/api/v1/administration/mode", json={"mode": "RESEARCH"})
    assert research.status_code == 200, research.text
    assert research.json()["mode"] == "RESEARCH"
    assert research.json()["weights"] == weights
    assert research.json()["status"] == "EXPERIMENTAL"
    assert app_mode.get_mode() == "RESEARCH"
    assert client.get("/api/v1/model").json()["mode"] == "RESEARCH"

    investor = client.post("/api/v1/administration/mode", json={"mode": "INVESTOR"})
    assert investor.status_code == 200, investor.text
    assert investor.json()["weights"] == app_mode.FROZEN_WEIGHTS
    assert investor.json()["status"] == "FROZEN"
    assert app_mode.get_mode() == "INVESTOR"
    assert (root / "weights.json").read_bytes() == saved_weights
    assert list(root.glob("app_mode.*.tmp")) == []

    app_mode.set_mode("RESEARCH")
    assert client.get("/api/v1/model").json()["mode"] == "RESEARCH"


@pytest.mark.parametrize("query", ["value=.3", "value=.1&quality=.1&momentum=.1&risk=.1",
                                    "limit=501", "offset=-1", "min_market_cap=NaN", "min_market_cap=Infinity"])
def test_invalid_requests_have_consistent_sanitized_errors(api, query):
    client, _, root = api
    (root / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    response = client.get("/api/v1/ranking?" + query)
    assert response.status_code == 422
    assert set(response.json()) == {"error", "status"}
    assert response.json()["status"] == "error"
    assert query not in response.text


def test_read_only_get_forbids_network_files_and_mutating_sql(api, monkeypatch):
    client, _, root = api
    before = hashes(root)
    real_open, real_connect, socket_connect = builtins.open, sqlite3.connect, socket.socket.connect
    traces = []

    def forbidden(*args, **kwargs):
        pytest.fail("GET attempted a mutation or external request")

    def readonly_open(file, mode="r", *args, **kwargs):
        assert not any(char in mode for char in "wax+")
        return real_open(file, mode, *args, **kwargs)

    def readonly_connect(*args, **kwargs):
        assert "mode=ro" in args[0] and kwargs.get("uri") is True
        connection = real_connect(*args, **kwargs)
        denied = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                  sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_DROP_TABLE}
        connection.set_authorizer(lambda action, *args: sqlite3.SQLITE_DENY if action in denied else sqlite3.SQLITE_OK)
        connection.set_trace_callback(traces.append)
        return connection

    def local_socket(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1", "localhost"}:
            return socket_connect(sock, address)
        forbidden()

    monkeypatch.setattr(builtins, "open", readonly_open)
    monkeypatch.setattr(sqlite3, "connect", readonly_connect)
    monkeypatch.setattr(requests.Session, "request", forbidden)
    monkeypatch.setattr(socket.socket, "connect", local_socket)
    monkeypatch.setattr(storage, "get_connection", forbidden)
    for name in ("write_text", "write_bytes", "mkdir", "unlink"):
        monkeypatch.setattr(Path, name, forbidden)
    for path in ("health", "model", "data/status", "ranking", "companies/T000?bars=5"):
        response = client.get("/api/v1/" + path)
        assert response.status_code == 200, response.text
    assert hashes(root) == before
    assert all(not any(word in statement.upper() for word in ("INSERT", "UPDATE", "CREATE", "ALTER", "DELETE")) for statement in traces)


def test_cache_invalidates_old_price_corrections_and_wal_commits(api):
    client, repository, root = api
    with sqlite3.connect(root / "gabi.db") as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        first = client.get("/api/v1/ranking").json()
        cold_queries, cold_rows = repository.query_count, repository.row_count
        warm = client.get("/api/v1/ranking").json()
        assert warm["cache_hit"] is True
        assert repository.row_count - cold_rows < 30
        assert repository.query_count - cold_queries < 10
        writer.execute("UPDATE prices SET close=close*.5, adj_close=adj_close*.5 WHERE symbol='T000' AND date=(SELECT MIN(date) FROM prices WHERE symbol='T000')")
        writer.commit()
        corrected = client.get("/api/v1/ranking").json()
        assert corrected["cache_hit"] is False
        assert corrected["revision"] != first["revision"]
        assert corrected["data"]["latest_price_date"] == first["data"]["latest_price_date"]
        def stock(payload):
            return next(item for item in payload["items"] if item["symbol"] == "T000")
        assert stock(corrected)["metrics"]["volatility"] != stock(first)["metrics"]["volatility"]


def test_limits_fail_without_truncating_financial_metrics(api):
    client, repository, _ = api
    repository.settings = replace(repository.settings, max_price_rows_per_batch=100)
    response = client.get("/api/v1/ranking")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "resource_limit"
    assert not repository.cache


def test_deep_histories_make_smaller_batches_with_identical_rankings(api):
    """A full-history backfill (16k sessions per firm locally) must not exceed the row budget."""
    client, repository, _ = api
    expected = client.get("/api/v1/ranking", params={"limit": 100}).json()["items"]
    repository.cache.clear()
    symbols = tuple(row[0] for row in repository.rows("SELECT DISTINCT symbol FROM prices"))
    longest = max(repository.price_counts(symbols).values())
    repository.settings = replace(repository.settings, max_price_rows_per_batch=longest * 2)
    queries = repository.query_count
    response = client.get("/api/v1/ranking", params={"limit": 100})
    assert response.status_code == 200
    assert response.json()["items"] == expected
    assert repository.query_count - queries > len(expected) // 2  # Batches of at most two firms.


def test_stale_empty_and_corrupt_are_distinct(api):
    client, repository, root = api
    repository.close()
    stale_app = create_app(Settings(root), today=lambda: TODAY + timedelta(days=30))
    with TestClient(stale_app) as stale:
        assert stale.get("/api/v1/data/status").json()["status"] == "stale"
    with sqlite3.connect(root / "gabi.db") as writer:
        writer.execute("UPDATE fundamentals SET info_json='SECRET invalid JSON'")
    failure = client.get("/api/v1/ranking")
    assert failure.status_code == 503
    assert failure.json()["status"] == "error"
    assert "SECRET" not in failure.text and str(root) not in failure.text


def test_metadata_evidence_never_reads_blind_payloads(api):
    client, repository, root = api
    with sqlite3.connect(root / "gabi.db") as writer:
        writer.execute("INSERT INTO blind_validations(id,created_at,name,model_id,weights_json,n_positions,rebalance_months,start_date,unlock_date,status) VALUES(1,'2026-09-29','fixture','GABI-MF-v1',?,10,3,'2026-09-29','2027-09-29','locked')", (json.dumps(app_mode.FROZEN_WEIGHTS),))
        writer.execute("INSERT INTO blind_validation_periods(id,validation_id,rebalance_date,recorded_at,symbols_json,weights_json,entry_prices_json,record_hash) VALUES(1,1,'2026-09-29','2026-09-29','SECRET','SECRET','SECRET','SECRET')")
    model = client.get("/api/v1/model").json()
    assert model["status"] == "LIVE_FORWARD" and model["blind_validation_id"] == 1
    assert model["independent_advantage_demonstrated"] is False
    blocked = {"symbols_json", "entry_prices_json", "record_hash", "ranking_json", "returns_json", "result_json"}
    assert repository.connection is not None
    repository.connection.set_authorizer(lambda action, table, column, *args:
                                        sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and column in blocked else sqlite3.SQLITE_OK)
    assert client.get("/api/v1/model").status_code == 200
    assert client.get("/api/v1/ranking").status_code == 200


def test_current_identity_matches_legacy_ambiguity_rule(api, monkeypatch):
    client, _, root = api
    monkeypatch.setattr(config, "DB_PATH", root / "gabi.db")
    with sqlite3.connect(root / "gabi.db") as writer:
        writer.execute("INSERT INTO entities VALUES('other','0000000002','Other','2026-01-01')")
        writer.execute("INSERT INTO entity_aliases VALUES('other','BRK-A','2026-01-01',NULL,'low-confidence',.1)")
    expected = identity.resolve("BRK-A", TODAY.isoformat())
    actual = client.get("/api/v1/companies/BRK-A").json()["company"]["identity"]
    assert {key: actual[key] for key in expected} == expected
    assert actual["status"] == "ambiguous"


@pytest.mark.parametrize("origin,allowed", [("http://localhost:5173", True), ("http://127.0.0.1:5173", True),
                                           ("https://example.com", False), ("http://localhost:8001", False)])
def test_cors_is_limited_to_local_client(api, origin, allowed):
    client, _, _ = api
    response = client.options("/api/v1/ranking", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert (response.headers.get("access-control-allow-origin") == origin) == allowed


def test_launcher_uses_loopback_only(monkeypatch):
    import uvicorn

    from gabi_api import bootstrap

    captured = {}
    monkeypatch.setattr(bootstrap, "create_app", lambda: object())
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: captured.update(kwargs))
    bootstrap.main()
    assert captured["host"] == "127.0.0.1"


def test_unexpected_error_does_not_expose_secrets(api, monkeypatch):
    client, repository, _ = api
    def failure():
        raise RuntimeError("secret-key internal-path")
    monkeypatch.setattr(repository, "local_model", failure)
    response = client.get("/api/v1/model")
    assert response.status_code == 500
    assert "secret-key" not in response.text and "internal-path" not in response.text


def test_missing_database_preserves_universe_with_null_metrics(tmp_path):
    (tmp_path / "sp500_constituents.csv").write_text("symbol,name,sector\nTEST,Test,Financials\n")
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as client:
        payload = client.get("/api/v1/ranking?hide_no_data=false").json()
    assert payload["data"]["status"] == "empty"
    assert payload["items"][0]["metrics"]["price"]["value"] is None
    assert payload["items"][0]["metrics"]["pe"]["value"] is None
    assert not (tmp_path / "gabi.db").exists()


def test_nonfinite_values_are_null_and_earnings_use_injected_date(api):
    from datetime import UTC, datetime

    client, _, root = api
    with sqlite3.connect(root / "gabi.db") as writer:
        raw = writer.execute("SELECT info_json FROM fundamentals WHERE symbol='T000'").fetchone()[0]
        info = json.loads(raw)
        info.update(marketCap=float("inf"), returnOnAssets=float("nan"),
                    earningsTimestampStart=int(datetime(2026, 9, 30, tzinfo=UTC).timestamp()))
        writer.execute("UPDATE fundamentals SET info_json=? WHERE symbol='T000'", (json.dumps(info),))
    response = client.get("/api/v1/companies/T000")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["company"]["metrics"]["market_cap"]["value"] is None
    assert payload["company"]["metrics"]["roa"]["value"] is None
    assert payload["company"]["next_earnings"]["days_until"] == 1
    assert payload["company"]["next_earnings"]["is_estimate"] is True
    json.dumps(payload, allow_nan=False)


def test_cache_invalidation_universe_changes_and_lru_bound(api):
    client, repository, root = api
    first = client.get("/api/v1/ranking").json()
    (root / "sp500_constituents.csv").write_text((root / "sp500_constituents.csv").read_text().replace("Company T000", "Renamed T000"))
    changed = client.get("/api/v1/ranking").json()
    assert changed["revision"] != first["revision"] and changed["cache_hit"] is False
    assert next(item for item in changed["items"] if item["symbol"] == "T000")["name"] == "Renamed T000"
    (root / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    for value in (.1, .2, .3, .4, .5):
        result = client.get("/api/v1/ranking", params={"value": value, "quality": 1 - value, "momentum": 0, "risk": 0})
        assert result.status_code == 200
    assert len(repository.cache) == repository.settings.cache_entries


def test_concurrent_cold_queries_share_one_calculation(api):
    from concurrent.futures import ThreadPoolExecutor

    from gabi.infrastructure.legacy.market import calculators

    _, repository, _ = api
    calls = []
    original = calculators().scores
    def scores(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    repository.calculators = replace(repository.calculators, scores=scores)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: repository.ranking(app_mode.FROZEN_WEIGHTS, TODAY), range(4)))
    assert len(calls) == 1
    assert sum(snapshot.cache_hit for snapshot in results) == 3
    assert len({snapshot.revision for snapshot in results}) == 1


def test_mid_query_change_is_rejected_instead_of_caching_mixed_data(api):
    _, repository, root = api
    from gabi.infrastructure.legacy.market import calculators

    original = calculators().scores
    def scores(*args, **kwargs):
        (root / "sp500_constituents.csv").write_text((root / "sp500_constituents.csv").read_text().replace("Company T000", "Renamed T000"))
        return original(*args, **kwargs)
    repository.calculators = replace(repository.calculators, scores=scores)
    from gabi.application.errors import QueryError
    with pytest.raises(QueryError, match="cambiaron") as error:
        repository.ranking(app_mode.FROZEN_WEIGHTS, TODAY)
    assert error.value.status == 409
    assert not repository.cache


def test_search_preserves_legacy_unicode_lowercase_semantics():
    table = pd.DataFrame({"name": ["Straße", "MISSING"], "sector": ["Financials"] * 2,
                          "price": [1., 2.]}, index=["A", "B"])
    assert list(filter_ranking(table, RankingFilter(search="ß")).index) == ["A"]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_is_applied_to_full_filtered_universe_before_pagination(api, direction):
    client, repository, _ = api
    table = repository.ranking(app_mode.FROZEN_WEIGHTS, TODAY).table
    expected = table.sort_values("market_cap", ascending=direction == "asc", kind="stable", na_position="last")
    payload = client.get(f"/api/v1/ranking?order_by=market_cap&direction={direction}&hide_no_data=false&limit=3&offset=2").json()
    assert [row["symbol"] for row in payload["items"]] == list(expected.iloc[2:5].index)
    assert [row["rank"] for row in payload["items"]] == [int(table.index.get_loc(symbol)) + 1 for symbol in expected.iloc[2:5].index]
    assert client.get("/api/v1/ranking?order_by=unknown").status_code == 422


@pytest.mark.parametrize("direction,expected", [("asc", ["C", "A", "D", "B"]),
                                                ("desc", ["A", "D", "C", "B"])])
def test_sort_stable_ties_missing_last_and_scores_unchanged(direction, expected):
    from gabi.domain.market.selection import RankingSort, sort_ranking
    table = pd.DataFrame({"market_cap": [2., None, 1., 2.], "composite_score": [80., 70., 60., 50.]},
                         index=["A", "B", "C", "D"])
    result = sort_ranking(table, RankingSort("market_cap", direction))
    assert list(result.index) == expected
    pd.testing.assert_series_equal(result["composite_score"].reindex(table.index), table["composite_score"])
    assert sort_ranking(table, RankingSort()) is table
