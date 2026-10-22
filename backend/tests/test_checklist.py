"""Descriptive fundamental Checklist (#167): Excel formulas, fiscal alignment, absences and threshold commands."""

import json
import sqlite3
from contextlib import closing
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import config
from gabi.application.errors import QueryError
from gabi.application.market.checklist import CompanyChecklist
from gabi.domain.market import checklist
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.checklist_thresholds import FileChecklistThresholds
from gabi.infrastructure.storage.sec_xbrl import FACTS_SCHEMA
from gabi_api.bootstrap import create_app

ANCHOR = 2025


def _duration(tag, year, value, *, filed=None, accn=None):
    return tag, "USD", {"start": f"{year - 1}-01-01", "end": f"{year - 1}-12-31", "val": value, "form": "10-K",
                        "fp": "FY", "filed": filed or f"{year}-02-15", "accn": accn or f"a{year}"}


def _instant(tag, year, value, unit="USD", *, form="10-K", filed=None):
    return tag, unit, {"end": f"{year - 1}-12-31", "val": value, "form": form, "fp": "FY",
                       "filed": filed or f"{year}-02-15", "accn": f"a{year}"}


def _facts(entries):
    family: dict = {}
    for tag, unit, entry in entries:
        family.setdefault(tag, {"units": {}})["units"].setdefault(unit, []).append(entry)
    return {"facts": {"us-gaap": family}}


def _excel_example():
    """The fictitious company of the Excel «Datos» sheet, in millions; fiscal years end 2015-12-31…2024-12-31."""
    last, first = ANCHOR, ANCHOR - 10
    rows = [
        _duration("Revenues", first, 4500), _duration("Revenues", last, 10000),
        _duration("GrossProfit", last, 5500), _duration("NetIncomeLoss", last, 1800),
        _duration("OperatingIncomeLoss", last, 2400), _duration("DepreciationDepletionAndAmortization", last, 500),
        _duration("InterestExpense", last, 60), _duration("IncomeTaxExpenseBenefit", last, 420),
        _duration(checklist.PRETAX_TAGS[0], last, 2000),
        _duration("NetCashProvidedByUsedInOperatingActivities", first, 1000),
        _duration("NetCashProvidedByUsedInOperatingActivities", last, 2600),
        _duration("PaymentsToAcquirePropertyPlantAndEquipment", last, 700),
        _duration("ShareBasedCompensation", last, 150),
        _instant("CashAndCashEquivalentsAtCarryingValue", last, 3000),
        _instant("LongTermDebtNoncurrent", last, 2500), _instant("DebtCurrent", last, 0),
        _instant("StockholdersEquity", last, 12500),
        _instant("CommonStockSharesOutstanding", last, 600, "shares"),
        _instant("CommonStockSharesOutstanding", last - 5, 640, "shares"),
    ]
    return rows


MARKET = checklist.MarketInputs(price=85, price_date="2025-06-30", shares=600, shares_date="2024-12-31",
                                forward_eps=3.4, beta=0.9)


def _evaluate(rows, market=MARKET, *, sector="Technology", thresholds=None, edited=frozenset(), insiders=(),
              splits=lambda start, end: 1.0):
    return checklist.evaluate(_facts(rows), market, sector=sector, thresholds=thresholds or checklist.defaults(),
                              edited=set(edited), insider_rows=list(insiders), today=date(2025, 7, 1),
                              split_factor_between=splits)


def _by_key(result):
    return {item["key"]: item for item in result["criteria"]}


def test_ratios_match_the_excel_checklist_sheet():
    result = _evaluate(_excel_example())
    criteria = _by_key(result)
    expected = {
        "revenue_cagr": 0.0831254203977676, "cfo_cagr": 0.100265093106018, "net_income": 1800,
        "gross_margin": 0.55, "net_margin": 0.18, "roic": 0.158, "net_debt": -500,
        "net_debt_to_ebitda": -0.172413793103448, "interest_coverage": 40, "cash_conversion": 1.44444444444444,
        "cfo_margin": 0.26, "fcf": 1900, "capex_to_revenue": 0.07, "shares_change": -0.0625,
        "sbc_to_net_income": 0.0833333333333333, "market_cap": 51000, "enterprise_value": 50500,
        "pe": 28.3333333333333, "forward_pe": 25.0, "ev_ebitda": 17.4137931034483, "ev_ebit": 21.0416666666667,
        "ev_fcf": 26.5789473684211, "fcf_yield": 0.0372549019607843, "beta": 0.9,
    }
    for key, value in expected.items():
        assert criteria[key]["value"] == pytest.approx(value), key
    verdicts = {key: item["verdict"] for key, item in criteria.items()}
    assert verdicts | {"revenue_growth_stability": "missing"} == verdicts
    assert {key for key, verdict in verdicts.items() if verdict == "fail"} == {
        "pe", "ev_ebitda", "ev_ebit", "ev_fcf", "fcf_yield"}
    assert verdicts["forward_pe"] == "pass" and verdicts["cfo_margin"] == "info"
    assert criteria["beta"]["detail"] == {"class": "neutral"}
    assert criteria["revenue_cagr"]["detail"]["years"] == 10
    assert criteria["insiders_pct"]["verdict"] == "missing" and criteria["insiders_pct"]["reason"] == "not_captured"
    assert result["fiscal_year_end"] == "2024-12-31"
    assert result["summary"]["passed"] + result["summary"]["failed"] == result["summary"]["evaluated"]


def test_reverse_dcf_matches_the_excel_sheet():
    options = {"discount_rate": 0.09, "terminal_growth": 0.03, "years": 10}
    assert checklist.dcf_value_per_share(1900, 600, 0.10, **options) == pytest.approx(84.4260955680603)
    growth, reason = checklist.implied_growth(85, 1900, 600, **options)
    assert reason is None and growth == pytest.approx(0.101, abs=1e-3)
    assert checklist.dcf_value_per_share(1900, 600, growth, **options) == pytest.approx(85)
    dcf = _evaluate(_excel_example())["dcf"]
    assert dcf["implied_growth"] == pytest.approx(growth) and dcf["historical_cfo_cagr"] == pytest.approx(0.1002651)
    assert dcf["verdict"] == "demanding"  # implied 10.1 % > historical CFO CAGR 10.0 %
    cheap = _evaluate(_excel_example(), checklist.MarketInputs(price=40, shares=600))["dcf"]
    assert cheap["verdict"] == "reasonable"
    expensive = _evaluate(_excel_example(), checklist.MarketInputs(price=400, shares=600))["dcf"]
    assert expensive["verdict"] == "discard"


def test_absent_components_are_missing_never_zero():
    rows = [row for row in _excel_example() if row[0] not in {"LongTermDebtNoncurrent", "DebtCurrent",
                                                              "InterestExpense", "ShareBasedCompensation"}]
    criteria = _by_key(_evaluate(rows))
    assert criteria["net_debt"]["verdict"] == "missing" and criteria["net_debt"]["reason"] == "no_debt_reported"
    assert criteria["enterprise_value"]["value"] is None and criteria["ev_ebitda"]["verdict"] == "missing"
    assert criteria["interest_coverage"]["reason"] == "no_interest"
    assert criteria["sbc_to_net_income"]["reason"] == "no_sbc"


def test_components_of_another_fiscal_year_are_not_mixed():
    rows = [row for row in _excel_example() if row[0] != "InterestExpense"]
    rows.append(_duration("InterestExpense", ANCHOR - 2, 60))
    criteria = _by_key(_evaluate(rows))
    assert criteria["interest_coverage"]["verdict"] == "missing"
    assert criteria["interest_coverage"]["reason"] == "stale_interest"


def test_debt_free_company_passes_interest_coverage_and_partial_debt_is_listed():
    rows = [row for row in _excel_example() if row[0] not in {"InterestExpense", "LongTermDebtNoncurrent",
                                                              "DebtCurrent"}]
    rows += [_instant("LongTermDebtNoncurrent", ANCHOR, 0), _instant("DebtCurrent", ANCHOR, 0)]
    criteria = _by_key(_evaluate(rows))
    assert criteria["interest_coverage"]["verdict"] == "pass" and criteria["interest_coverage"]["reason"] == "no_debt"
    partial = [row for row in _excel_example() if row[0] != "DebtCurrent"]
    detail = _by_key(_evaluate(partial))["net_debt"]["detail"]
    assert detail["components_not_reported"] == ["lt_debt_current", "short_borrowings", "short_investments"]


def test_financial_sector_marks_unsuitable_criteria_not_applicable():
    result = _evaluate(_excel_example(), sector="Financial Services")
    criteria = _by_key(result)
    assert result["financial_sector"]
    assert criteria["gross_margin"]["verdict"] == "not_applicable" and criteria["ev_ebitda"]["verdict"] == "not_applicable"
    assert criteria["pe"]["verdict"] == "fail" and result["dcf"]["verdict"] == "not_applicable"


def test_share_change_undoes_later_splits():
    rows = [row for row in _excel_example() if row[0] != "CommonStockSharesOutstanding"]
    rows += [_instant("CommonStockSharesOutstanding", ANCHOR, 2400, "shares"),
             _instant("CommonStockSharesOutstanding", ANCHOR - 5, 640, "shares")]
    change = _by_key(_evaluate(rows, splits=lambda start, end: 4.0))["shares_change"]
    assert change["value"] == pytest.approx(-0.0625) and change["detail"]["split_factor"] == 4.0


def test_margin_expansion_and_alarms():
    rows = _excel_example() + [_duration("Revenues", ANCHOR - 5, 6000), _duration("NetIncomeLoss", ANCHOR - 5, 600),
                               _duration("GrossProfit", ANCHOR - 5, 3600)]
    criteria = _by_key(_evaluate(rows))
    assert criteria["net_margin_change"]["value"] == pytest.approx(0.08)
    assert criteria["gross_margin_change"]["value"] == pytest.approx(-0.05)
    assert criteria["gross_margin_change"]["verdict"] == "fail"
    insiders = [{"transaction_date": "2025-05-01", "owner_name": "A", "owner_title": "Chief Executive Officer",
                 "is_officer": 1, "transaction_code": "S", "is_10b5_1_plan": 0, "shares": 300,
                 "shares_owned_after": 700}]
    alarms = {item["key"]: item for item in _evaluate(rows, insiders=insiders)["alarms"]}
    assert alarms["executives_selling"]["status"] == "active"
    assert alarms["executives_selling"]["detail"]["largest_sold_fraction"] == pytest.approx(0.3)
    planned = [insiders[0] | {"is_10b5_1_plan": 1}]
    assert {a["key"]: a for a in _evaluate(rows, insiders=planned)["alarms"]}["executives_selling"]["status"] == "clear"
    assert alarms["dilution"]["status"] == "clear"
    assert alarms["blames_external_factors"]["status"] == "manual"
    assert alarms["goodwill"]["status"] == "missing"


def test_earnings_outpacing_cash_flow_is_flagged():
    rows = [row for row in _excel_example() if row[0] not in {"NetIncomeLoss",
                                                              "NetCashProvidedByUsedInOperatingActivities"}]
    for back, (income, cash) in enumerate([(1800, 1200), (1500, 1100), (1200, 1150), (900, 1000)]):
        rows += [_duration("NetIncomeLoss", ANCHOR - back, income),
                 _duration("NetCashProvidedByUsedInOperatingActivities", ANCHOR - back, cash)]
    alarms = {item["key"]: item for item in _evaluate(rows)["alarms"]}
    assert alarms["earnings_outpace_cfo"]["status"] == "active"


def test_threshold_validation():
    assert checklist.validate_thresholds({"pe": 20}) == {"pe": 20.0}
    for overrides, message in (({"unknown": 1}, "desconocido"), ({"pe": 1000}, "entre"), ({"pe": True}, "número"),
                               ({"dcf_years": 7.5}, "entero"), ({"dcf_terminal_growth": 0.09}, "menor")):
        with pytest.raises(ValueError, match=message):
            checklist.validate_thresholds(overrides)
    edited = _by_key(_evaluate(_excel_example(), thresholds=checklist.defaults() | {"pe": 30}, edited={"pe"}))
    assert edited["pe"]["verdict"] == "pass" and edited["pe"]["edited"] and edited["pe"]["default_threshold"] == 18


class _Facts:
    def __init__(self, frame):
        self.frame = frame

    def facts(self, symbol, *, entity_id=None, tags=None, as_of=None, unit=None):
        return self.frame[self.frame.filed_date <= as_of] if as_of else self.frame

    def last_filed(self, symbols, as_of=None):
        return {}


class _Cache:
    def latest_adjusted(self, symbols):
        return {"ACME": ("2025-06-30", 85.0, 84.0)}

    def split_ratios_after(self, symbol, as_of):
        return []

    def last_price(self, symbol, as_of):
        return (80.0, 79.0)

    def fundamentals(self, symbols):
        return [("ACME", "2025-06-30T08:00:00+00:00", json.dumps({"forwardEps": 3.4, "beta": 0.9, "heldPercentInsiders": 0.15,
                                                                     "sector": "Technology"}), "{}", "{}")]


class _Insiders:
    def insider_transactions(self, symbol):
        return pd.DataFrame()


def _frame(rows):
    return pd.DataFrame([{"symbol": "ACME", "tag": tag, "unit": unit, "start_date": entry.get("start") or "",
                          "end_date": entry["end"], "val": entry["val"], "form": entry["form"], "fp": entry["fp"],
                          "fy": None, "filed_date": entry["filed"], "accn": entry["accn"]}
                         for tag, unit, entry in rows])


def test_use_case_reads_known_filings_and_persists_only_edits(tmp_path):
    rows = _excel_example() + [_duration("NetIncomeLoss", ANCHOR, 99999, filed="2025-09-01", accn="later")]
    store = FileChecklistThresholds(tmp_path)
    service = CompanyChecklist(_Facts(_frame(rows)), _Cache(), _Insiders(), store, lambda: date(2025, 7, 1))
    body = service.company("acme")
    criteria = {item["key"]: item for item in body["criteria"]}
    assert criteria["net_income"]["value"] == 1800  # the restatement filed after today is unknown
    assert criteria["pe"]["value"] == pytest.approx(28.3333333)
    assert criteria["insiders_pct"]["value"] == 0.15 and criteria["insiders_pct"]["verdict"] == "pass"
    assert body["sources"]["sec_last_filed"] == "2025-02-15" and body["sources"]["price_date"] == "2025-06-30"
    assert not (tmp_path / "checklist_thresholds.json").exists()
    saved = service.save_thresholds({"pe": 30, "net_margin": 0.10})
    assert saved["edited"] == ["pe"] and json.loads(store.path.read_text())["values"] == {"pe": 30.0}
    assert {item["key"]: item for item in service.company("ACME")["criteria"]}["pe"]["verdict"] == "pass"
    with pytest.raises(QueryError) as error:
        service.save_thresholds({"pe": -1})
    assert error.value.status == 422 and json.loads(store.path.read_text())["values"] == {"pe": 30.0}
    assert service.reset_thresholds()["edited"] == [] and not store.path.exists()
    store.path.write_text("{not json", encoding="utf-8")
    recovered = service.thresholds()
    assert recovered["warning"] == "invalid_saved_thresholds" and recovered["values"]["pe"] == 18


def _yearly(years=range(ANCHOR - 4, ANCHOR + 1)):
    """Five fiscal years with net income 100·k, EBIT 150·k, D&A 50, CFO 120·k, CAPEX 20, debt 300, cash 100."""
    rows = []
    for k, year in enumerate(years, start=1):
        rows += [_duration("Revenues", year, 1000 * k), _duration("NetIncomeLoss", year, 100 * k),
                 _duration("OperatingIncomeLoss", year, 150 * k),
                 _duration("DepreciationDepletionAndAmortization", year, 50),
                 _duration("NetCashProvidedByUsedInOperatingActivities", year, 120 * k),
                 _duration("PaymentsToAcquirePropertyPlantAndEquipment", year, 20),
                 _instant("LongTermDebt", year, 300), _instant("ShortTermBorrowings", year, 0),
                 _instant("CashAndCashEquivalentsAtCarryingValue", year, 100),
                 _instant("ShortTermInvestments", year, 0),
                 _instant("CommonStockSharesOutstanding", year, 10, "shares")]
    return rows


def test_own_multiples_use_each_year_end_close_and_split_adjusted_shares():
    closes = {f"{year}-12-31": 10.0 * (year - 2019) for year in range(2020, 2025)}
    splits = {"2020-12-31": 2.0}  # a 2:1 split after 2020: those 10 shares are 20 in today's basis
    history = checklist.multiples_history(_facts(_yearly()), close_on=closes.get,
                                          split_factor_after=lambda day: splits.get(day, 1.0), financial=False)
    years = {row["fiscal_year_end"]: row for row in history["by_year"]}
    assert list(years) == [f"{year}-12-31" for year in range(2024, 2019, -1)]
    first = years["2020-12-31"]
    assert first["market_cap"] == pytest.approx(10 * 10 * 2.0) and first["pe"] == pytest.approx(200 / 100)
    assert first["ev_ebitda"] == pytest.approx((200 + 200) / 200)
    assert first["ev_ebit"] == pytest.approx(400 / 150) and first["ev_fcf"] == pytest.approx(400 / 100)
    last = years["2024-12-31"]
    assert last["pe"] == pytest.approx(50 * 10 / 500)
    pes = sorted(row["pe"] for row in years.values())
    assert history["median"]["pe"] == {"median": pytest.approx(pes[2]), "count": 5, "reason": None}
    # The latest year agrees with the criterion computed at that close.
    market = checklist.MarketInputs(price=50.0, shares=10)
    criteria = _by_key(_evaluate(_yearly(), market))
    for key in checklist.MULTIPLE_KEYS:
        assert criteria[key]["value"] == pytest.approx(last[key]), key


def test_own_multiples_need_three_years_and_skip_ev_for_financials():
    closes = {"2024-12-31": 50.0, "2023-12-31": 40.0}  # no price before 2023: unknown, not zero
    history = checklist.multiples_history(_facts(_yearly()), close_on=closes.get,
                                          split_factor_after=lambda day: 1.0, financial=False)
    assert [row["market_cap"] is None for row in history["by_year"]] == [False, False, True, True, True]
    assert history["median"]["pe"] == {"median": None, "count": 2, "reason": "fewer_than_3_years"}
    financial = checklist.multiples_history(_facts(_yearly()), close_on=lambda day: 30.0,
                                            split_factor_after=lambda day: 1.0, financial=True)
    assert financial["median"]["pe"]["count"] == 5
    assert financial["median"]["ev_ebitda"] == {"median": None, "count": 0, "reason": "financial_sector"}
    loss = [row for row in _yearly() if row[0] != "NetIncomeLoss"] + [_duration("NetIncomeLoss", ANCHOR, -5)]
    years = checklist.multiples_history(_facts(loss), close_on=lambda day: 30.0,
                                        split_factor_after=lambda day: 1.0, financial=False)["by_year"]
    assert years[0]["pe"] is None and years[0]["ev_ebit"] is not None


class _SectorFacts:
    def __init__(self):
        self.reads, self.filed = [], {"ACME": "2025-02-15"}

    def facts(self, symbol, *, entity_id=None, tags=None, as_of=None, unit=None):
        self.reads.append((symbol, tuple(tags or ())))
        frame = _frame(_yearly())
        return frame.assign(symbol=symbol)

    def last_filed(self, symbols, as_of=None):
        return {symbol: self.filed.get(symbol, "2025-02-15") for symbol in symbols}


class _SectorCache(_Cache):
    def latest_adjusted(self, symbols):
        return {symbol: ("2025-06-30", 10.0 + index, 10.0) for index, symbol in enumerate(sorted(symbols))}


def test_sector_medians_exclude_the_company_and_reuse_the_sector_until_data_changes(tmp_path):
    universe = [("ACME", "Technology")] + [(f"P{index}", "Technology") for index in range(6)] + [("BANK", "Financials")]
    reads = _SectorFacts()
    service = CompanyChecklist(reads, _SectorCache(), _Insiders(), FileChecklistThresholds(tmp_path),
                               lambda: date(2025, 7, 1), lambda: universe)
    body = service.sector_multiples("acme")
    # Peers P0…P5 cost 11…16 per share with 10 shares and 500 of net income: PER 0.22…0.32.
    assert body["sector"] == "Technology" and body["peers"] == 6 and not body["cached"]
    assert body["medians"]["pe"] == {"median": pytest.approx((13.5 * 10) / 500), "count": 6, "reason": None}
    assert all(tags == tuple(checklist.MULTIPLE_TAGS) for _, tags in reads.reads)
    assert len(reads.reads) == 7 and not (tmp_path / "checklist_thresholds.json").exists()
    other = service.sector_multiples("P0")
    assert other["cached"] and len(reads.reads) == 7 and other["peers"] == 6
    reads.filed["P3"] = "2025-06-01"  # a new filing changes the key: recomputed, never stale
    assert not service.sector_multiples("ACME")["cached"] and len(reads.reads) == 14
    few = service.sector_multiples("BANK")
    assert few["peers"] == 0 and few["medians"]["pe"]["reason"] == "fewer_than_5_peers"
    assert few["medians"]["ev_fcf"]["reason"] == "financial_sector"
    assert service.sector_multiples("NOPE")["reason"] == "not_in_universe"


@pytest.fixture
def api():
    root = config.DATA_DIR
    seed_fixture(root)
    frame = _frame(_excel_example())
    with closing(sqlite3.connect(root / "gabi.db")) as db:
        db.executescript(FACTS_SCHEMA)
        db.executemany("INSERT INTO edgar_facts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       [("T001", r.tag, r.unit, r.start_date, r.end_date, r.val, r.form, r.fp, r.fy, r.filed_date,
                         r.accn) for r in frame.itertuples()])
        db.commit()
    with TestClient(create_app(Settings(root), today=lambda: TODAY)) as client:
        yield client, root


def test_api_get_has_no_side_effects_and_thresholds_are_explicit_commands(api):
    client, root = api
    before = (root / "gabi.db").read_bytes()
    body = client.get("/api/v1/companies/t001/checklist").json()
    assert body["symbol"] == "T001" and body["fiscal_year_end"] == "2024-12-31"
    criteria = {item["key"]: item for item in body["criteria"]}
    assert criteria["gross_margin"]["value"] == pytest.approx(0.55) and criteria["pe"]["value"] is not None
    assert body["multiples_history"]["by_year"][0]["fiscal_year_end"] == "2024-12-31"
    sector = client.get("/api/v1/companies/T001/checklist/sector").json()
    assert sector["sector"] == "Information Technology" and sector["peers"] > 0
    assert set(sector["medians"]) == set(checklist.MULTIPLE_KEYS)
    assert client.get("/api/v1/companies/T001/checklist/sector").json()["cached"]
    assert (root / "gabi.db").read_bytes() == before
    assert not (root / "checklist_thresholds.json").exists()
    empty = client.get("/api/v1/companies/T002/checklist").json()
    assert empty["fiscal_year_end"] is None and empty["summary"]["evaluated"] == 0
    catalog = client.get("/api/v1/checklist/thresholds").json()
    assert catalog["values"]["pe"] == 18 and catalog["edited"] == []
    saved = client.post("/api/v1/checklist/thresholds", json={"values": {"pe": 40}}).json()
    assert saved["edited"] == ["pe"] and saved["values"]["pe"] == 40
    edited = {item["key"]: item for item in client.get("/api/v1/companies/T001/checklist").json()["criteria"]}
    assert edited["pe"]["edited"] and edited["pe"]["threshold"] == 40
    rejected = client.post("/api/v1/checklist/thresholds", json={"values": {"dcf_terminal_growth": 0.5}})
    assert rejected.status_code == 422
    assert client.post("/api/v1/checklist/thresholds/reset").json()["edited"] == []
