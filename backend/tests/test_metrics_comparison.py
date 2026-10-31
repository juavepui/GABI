"""V1 against SEC metrics V2 (#245): summaries and the explicit comparison over temporary inputs only."""

from datetime import date

import pandas as pd
import pytest

from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError
from gabi.application.market.metrics_comparison import compare_metrics
from gabi.domain.market import metrics_comparison as compare

TODAY = date(2026, 10, 31)
FY24, FY23 = ("2024-01-01", "2024-12-31"), ("2023-01-01", "2023-12-31")


def flow(value, period=FY24):
    return {"start": period[0], "end": period[1], "val": value, "form": "10-K", "fp": "FY", "accn": "a",
            "filed": "2025-02-15"}


def stock(value, end="2024-12-31"):
    return {"end": end, "val": value, "form": "10-K", "fp": "FY", "accn": "a", "filed": "2025-02-15"}


def facts(debt=True):
    tags = {
        "OperatingIncomeLoss": [flow(200.0)],
        "StockholdersEquity": [stock(900.0, "2023-12-31"), stock(1100.0)],
        "CashAndCashEquivalentsAtCarryingValue": [stock(150.0, "2023-12-31"), stock(200.0)],
    }
    if debt:
        tags["LongTermDebt"] = [stock(450.0, "2023-12-31"), stock(420.0)]
    return {"facts": {"us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in tags.items()}}}


def metric(value, state="computed", reason=None):
    return {"value": value, "state": state, "reason": reason}


def test_roic_summary_counts_states_rank_agreement_and_what_v1_hid():
    rows = [{"symbol": f"S{i}", "v1": i / 100, "v2": metric(i / 100 + 0.01)} for i in range(10)]
    rows.append({"symbol": "DEBT", "v1": 0.2, "v2": metric(None, "absent", "debt_absent")})
    rows.append({"symbol": "BANK", "v1": 0.1, "v2": metric(None, "not_applicable", "financial_sector")})
    summary = compare.roic(rows)
    assert summary["v2_states"] == {"computed": 10, "absent": 1, "not_applicable": 1}
    assert summary["spearman"] == pytest.approx(1.0) and summary["top_quintile_overlap"] == 1.0
    assert summary["median_abs_difference"] == pytest.approx(0.01)
    assert summary["v1_only_reasons"] == {"debt_absent": 1, "financial_sector": 1}
    assert len(summary["largest_differences"]) == 10


def test_enterprise_value_summary_measures_the_relative_gap_with_yahoo():
    rows = [{"symbol": "A", "yahoo": 100.0, "v2": metric(105.0)},
            {"symbol": "B", "yahoo": 100.0, "v2": metric(80.0)},
            {"symbol": "C", "yahoo": None, "v2": metric(50.0)},
            {"symbol": "D", "yahoo": 100.0, "v2": metric(None, "absent", "cash_absent")}]
    summary = compare.enterprise_value(rows)
    assert summary["both_available"] == 2
    assert summary["median_relative_difference"] == pytest.approx((0.05 - 0.20) / 2)
    assert summary["share_beyond_tolerance"] == 0.5
    assert summary["largest_differences"][0]["symbol"] == "B"


def test_ranking_reports_agreement_and_top_n_changes():
    v1 = pd.Series({"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.0})
    v2 = pd.Series({"A": 3.0, "B": 0.5, "C": 2.0, "D": 0.0})
    result = compare.ranking(v1, v2, 2)
    assert result["top_overlap"] == 0.5 and result["entering"] == ["C"] and result["leaving"] == ["B"]


def _run(as_of, **overrides):
    stored = {"AAA": facts(), "BBB": facts(debt=False), "BANK": facts()}
    asked = []
    options = dict(
        universe=lambda: [("AAA", "Information Technology"), ("BBB", "Industrials"), ("BANK", "Financials")],
        facts=lambda symbol, day: asked.append((symbol, day)) or stored[symbol],
        v1_metrics=lambda companyfacts: {"roic": 0.10},
        infos=lambda symbols: {"AAA": {"marketCap": 5000.0, "enterpriseValue": 5300.0}},
        ranking=lambda: pd.DataFrame({"composite_score": [2.0, 1.0, 0.5], "roic": [0.1, 0.1, 0.1]},
                                     index=["AAA", "BBB", "BANK"]),
        rescore=lambda table: table.assign(composite_score=table["roic"].fillna(-1)),
        as_of=as_of, today=TODAY)
    return compare_metrics(**(options | overrides)), asked


def test_today_compares_roic_enterprise_value_and_the_rescored_ranking():
    report, asked = _run(TODAY)
    assert asked[0] == ("AAA", "2026-10-31")
    assert report["roic"]["v2_states"] == {"computed": 1, "absent": 1, "not_applicable": 1}
    assert report["roic"]["v1_only_reasons"] == {"debt_absent": 1, "financial_sector": 1}
    # EV V2 = 5000 + 420 − 200 against Yahoo's 5300.
    assert report["enterprise_value"]["largest_differences"][0]["relative"] == pytest.approx(5220 / 5300 - 1)
    assert report["ranking"]["top_n"] == 20 and report["ranking"]["entering"] == []


def test_a_past_date_compares_only_sec_facts_filed_up_to_it():
    report, asked = _run(date(2025, 3, 31), infos=lambda symbols: pytest.fail("Yahoo is not point in time"))
    assert {day for _, day in asked} == {"2025-03-31"}
    assert report["enterprise_value"] is None and report["ranking"] is None
    assert report["roic"]["companies"] == 3


def test_the_job_accepts_today_or_an_observed_date_only():
    JobCommand("metrics_comparison")
    JobCommand("metrics_comparison", start="2020-06-30")
    for options in ({"start": "2026-01-01"}, {"start": "2020-06-30", "end": "2020-12-31"}):
        with pytest.raises(QueryError):
            JobCommand("metrics_comparison", **options)


def test_the_worker_compares_the_cached_universe_without_writing(tmp_path):
    from market_fixture import TODAY as FIXTURE_TODAY
    from market_fixture import seed_fixture

    from gabi.infrastructure.legacy.jobs import LegacyExecutor
    from gabi.infrastructure.settings import Settings

    seed_fixture(tmp_path)
    stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
    phases = []
    report = LegacyExecutor(Settings(tmp_path), today=lambda: FIXTURE_TODAY)(
        JobCommand("metrics_comparison"), lambda fraction, phase: phases.append(fraction))
    assert report["as_of"] == FIXTURE_TODAY.isoformat() and report["roic"]["companies"] == 16
    # The fixture stores SEC metrics but no facts: V2 says why instead of computing a number.
    assert report["roic"]["v2_reasons"] == {"no_annual_report": 16}
    assert report["ranking"] is not None and phases[-1] == 1.0
    assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp
