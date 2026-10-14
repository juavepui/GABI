"""Captured parity of the legacy HTTP transports now delegated to infrastructure providers (ADR 0004)."""

import ast
import io
import json
import time
import zipfile
from datetime import date
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from gabi import config
from gabi.domain.market.source_errors import classify

REFERENCE = json.loads((Path(__file__).parent / "fixtures/http_providers_migration.json").read_text(encoding="utf-8"))


class Fake:
    """Answers both the legacy (json/content/text) and the streamed provider protocol."""

    def __init__(self, status: int, body: bytes = b""):
        self.status_code, self.content, self.headers = status, body, {}
        self.text = body.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)

    def iter_content(self, chunk_size=1):
        for start in range(0, len(self.content), 7):
            yield self.content[start:start + 7]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def web(monkeypatch):
    state = SimpleNamespace(routes={}, calls=[])

    def get(url, params=None, **kwargs):
        state.calls.append((url, params))
        answer = state.routes.get(url, Fake(404))
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(config, "SEC_USER_AGENT", "GABI test contact@example.com")
    return state


def captured(module: str, names: set[str], namespace: dict) -> dict:
    source = REFERENCE[module]
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names or isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in names for t in node.targets):
            exec(ast.get_source_segment(source, node), namespace)
    return namespace


def outcome(call):
    try:
        return "ok", call()
    except Exception as exc:  # noqa: BLE001 - the comparison is the point
        return type(exc).__name__, classify(str(exc))[0], str(exc) if isinstance(exc, ValueError) else None


def compare(web, scenarios, old, new):
    for routes, call in scenarios:
        results = []
        for function in (old, new):
            web.routes, web.calls = dict(routes), []
            results.append((outcome(lambda: call(function)), [(url, params) for url, params in web.calls]))
        assert results[0] == results[1], call


FRED = "https://api.stlouisfed.org/fred/series/observations"
RELEASES = "https://api.stlouisfed.org/fred/release/dates"


def test_fred_observations_and_releases(web, monkeypatch):
    from gabi.domain.market import fred
    from gabi.infrastructure.providers.fred import FredSource

    old = captured("macro", {"fetch_series", "fetch_next_release_date", "FRED_BASE_URL", "RELEASE_IDS",
                             "RELEASE_DATES_URL", "_parse_next_release_date"},
                   {"requests": requests, "fred": fred, "date": date})
    observations = json.dumps({"count": 900, "observations": [
        {"date": "2026-09-01", "value": "4.2"}, {"date": "2026-08-01", "value": "."}]}).encode()
    scenarios = [({FRED: Fake(200, observations)}, lambda f: f("DGS10", "k", "pc1", 5, observation_start="2020-01-01")),
                 ({FRED: Fake(200, observations)}, lambda f: f("DGS10", "k", include_missing=True)),
                 ({FRED: Fake(401)}, lambda f: f("DGS10", "k")), ({FRED: Fake(500)}, lambda f: f("DGS10", "k")),
                 ({FRED: Fake(429)}, lambda f: f("DGS10", "k")),
                 ({FRED: requests.ConnectionError("HTTPSConnectionPool(host='api'): Max retries exceeded with url: ?api_key=k (Caused by NewConnectionError)")}, lambda f: f("DGS10", "k")),
                 ({FRED: requests.Timeout("read timed out")}, lambda f: f("DGS10", "k"))]
    compare(web, scenarios, old["fetch_series"], partial(FredSource().fetch, require_complete=False))
    releases = json.dumps({"release_dates": [{"date": "2020-01-01"}, {"date": "2999-01-01"}]}).encode()
    compare(web, [({RELEASES: Fake(200, releases)}, lambda f: f("CPIAUCSL", "k")), ({}, lambda f: f("DGS10", "k")),
                  ({RELEASES: Fake(500)}, lambda f: f("CPIAUCSL", "k"))],
            old["fetch_next_release_date"], lambda sid, key: FredSource().next_release(sid, key, date.today()))


def test_fred_errors_never_carry_the_key(web):
    from gabi.infrastructure.providers.fred import FredSource
    web.routes = {FRED: requests.ConnectionError("Max retries exceeded with url: ?api_key=SECRET")}
    with pytest.raises(requests.ConnectionError) as error:
        FredSource().fetch("DGS10", "SECRET")
    assert "SECRET" not in str(error.value)


def test_sec_documents_and_ticker_map(web, tmp_path, monkeypatch):
    from gabi import edgar
    from gabi.infrastructure.providers.form4 import SecForm4Documents

    old = captured("edgar", {"fetch_company_facts", "fetch_submissions", "_headers", "COMPANYFACTS_URL",
                             "SUBMISSIONS_URL"}, {"requests": requests, "config": config})
    facts, subs = ("https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json",
                   "https://data.sec.gov/submissions/CIK0000000001.json")
    body = json.dumps({"cik": 1, "facts": {}}).encode()
    for old_call, new_call, url in ((old["fetch_company_facts"], edgar.fetch_company_facts, facts),
                                    (old["fetch_submissions"], edgar.fetch_submissions, subs)):
        compare(web, [({url: Fake(200, body)}, lambda f: f("0000000001")), ({url: Fake(404)}, lambda f: f("0000000001")),
                      ({url: Fake(503)}, lambda f: f("0000000001"))], old_call, new_call)
    xml_url = "https://www.sec.gov/Archives/edgar/data/1/a/doc.xml"
    old_insider = captured("insider", {"_Documents"}, {"requests": requests, "config": config, "edgar": edgar})
    compare(web, [({xml_url: Fake(200, b"<ownershipDocument/>")}, lambda f: f(xml_url)),
                  ({xml_url: Fake(500)}, lambda f: f(xml_url))],
            old_insider["_Documents"].xml, lambda url: SecForm4Documents(config.SEC_USER_AGENT).xml(url))
    tickers = "https://www.sec.gov/files/company_tickers.json"
    payload = json.dumps({"0": {"cik_str": 1, "ticker": "AAA", "title": "Alpha"}}).encode()
    def old_fetch():
        response = requests.get(tickers, headers=old["_headers"](), timeout=20)
        response.raise_for_status()
        return response.json()

    from gabi.infrastructure.providers.sec_cik import SecTickerMap
    compare(web, [({tickers: Fake(200, payload)}, lambda f: f()), ({tickers: Fake(500)}, lambda f: f())],
            old_fetch, SecTickerMap(config.SEC_USER_AGENT).fetch)


def zip_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("F-F.CSV", text)
    return buffer.getvalue()


def test_french_factor_tables(web):
    from gabi import academic_factors

    old = captured("academic_factors", {"_download_zip_csv", "_HEADERS"}, {"requests": requests, "io": io,
                                                                            "zipfile": zipfile})
    url = academic_factors.FF5_URL
    compare(web, [({url: Fake(200, zip_bytes("hdr\n,Mkt-RF\n202301, 1.0\n"))}, lambda f: f(url)),
                  ({url: Fake(500)}, lambda f: f(url))], old["_download_zip_csv"], academic_factors._download_zip_csv)


def test_tiingo_and_wiki_requests(web, monkeypatch):
    from gabi.application.research.tiingo_prices import PriceResponse
    from gabi.application.research.wiki_prices import FetchResponse
    from gabi.domain.research.tiingo_prices import PRICES_URL
    from gabi.domain.research.wiki_prices import COLUMNS, END_EXCLUSIVE, START, URL, wiki_ticker
    from gabi.infrastructure.providers.tiingo_prices import TiingoPrices
    from gabi.infrastructure.providers.wiki_prices import NasdaqWikiSource

    monkeypatch.setattr(config, "load_tiingo_key", lambda: "tk")
    tiingo = captured("historical_tiingo", {"_Source", "_headers"}, {
        "requests": requests, "config": config, "PRICES_URL": PRICES_URL, "PriceResponse": PriceResponse})
    url = PRICES_URL.format(ticker="brk-b", start="2010-01-01", end="2010-02-01")
    body = json.dumps([{"date": "2010-01-04", "close": 1.0}]).encode()
    compare(web, [({url: Fake(200, body)}, lambda f: f("BRK.B", "2010-01-01", "2010-02-01")),
                  ({url: Fake(429)}, lambda f: f("BRK.B", "2010-01-01", "2010-02-01")),
                  ({url: requests.ConnectionError("down")}, lambda f: f("BRK.B", "2010-01-01", "2010-02-01"))],
            tiingo["_Source"]().request, TiingoPrices(config.load_tiingo_key).request)
    wiki = captured("historical_wiki", {"_Source"}, {"requests": requests, "URL": URL, "START": START,
                                                     "END_EXCLUSIVE": END_EXCLUSIVE, "COLUMNS": COLUMNS,
                                                     "_wiki_ticker": wiki_ticker, "FetchResponse": FetchResponse})
    body = json.dumps({"datatable": {"data": [["AAA", "2010-01-04", 1.0]]}}).encode()
    compare(web, [({URL: Fake(200, body)}, lambda f: f("BRK.B", "key")), ({URL: Fake(404)}, lambda f: f("AAA", "key")),
                  ({URL: requests.Timeout("slow")}, lambda f: f("AAA", "key"))],
            wiki["_Source"]().request, NasdaqWikiSource().request)


def test_sec_archive_chunks(web, monkeypatch):
    from gabi import edgar, sec_history

    old = captured("sec_history", {"_download_chunks"}, {"requests": requests, "time": time, "edgar": edgar})
    url = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/2010q1.zip"
    compare(web, [({url: Fake(200, b"x" * 50)}, lambda f: b"".join(f(url))), ({url: Fake(403)}, lambda f: list(f(url)))],
            old["_download_chunks"], sec_history._download_chunks)


def test_sp500_sources(web, monkeypatch, tmp_path):
    from gabi import universe

    csv = "Symbol,Security,GICS Sector,GICS Sub-Industry\nBRK.B,Berkshire,Financials,Insurance\nAAPL,Apple,IT,HW\n"
    html = ("<table><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th></tr>"
            "<tr><td>BF.B</td><td>Brown</td><td>Staples</td><td>Drinks</td></tr></table>")
    history = "date,tickers\n2020-01-02,\"AAPL,BRK.B\"\n2021-01-04,\"AAPL\"\n"

    def local_read_csv(source, *args, **kwargs):
        return pd.read_csv(io.StringIO(csv), *args, **kwargs) if source == universe.GITHUB_CSV_URL else \
            pd.read_csv(source, *args, **kwargs)

    old = captured("universe", {"_normalize", "_fetch_from_github_csv", "_fetch_from_wikipedia"}, {
        "pd": SimpleNamespace(read_csv=local_read_csv, read_html=lambda url: pd.read_html(io.StringIO(html)),
                              DataFrame=pd.DataFrame),
        "GITHUB_CSV_URL": universe.GITHUB_CSV_URL, "WIKI_URL": universe.WIKI_URL})
    web.routes = {universe.GITHUB_CSV_URL: Fake(200, csv.encode()), universe.WIKI_URL: Fake(200, html.encode()),
                  universe.HISTORICAL_MEMBERSHIP_URL: Fake(200, history.encode())}
    pd.testing.assert_frame_equal(universe._fetch_from_github_csv(), old["_fetch_from_github_csv"]())
    pd.testing.assert_frame_equal(universe._fetch_from_wikipedia(), old["_fetch_from_wikipedia"]())
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", tmp_path / "members.csv")
    monkeypatch.setattr(universe, "apply_reviewed_extension", lambda frame: frame)
    expected = pd.read_csv(io.StringIO(history), dtype={"date": str})
    pd.testing.assert_frame_equal(universe.get_historical_membership(force_refresh=True), expected)
    web.routes[universe.GITHUB_CSV_URL] = Fake(200, b"x" * 64)
    from gabi.infrastructure.providers.sp500_sources import SP500Sources
    with pytest.raises(ValueError, match="límite"):
        SP500Sources("ua", max_bytes=10).constituents_csv()
