"""Explicit comparison of the V1 metrics with SEC metrics V2 (#245); reads the local cache only.

At today's date it also compares the Yahoo enterprise value and the operating
ranking rescored with each ROIC. At a past date it compares only SEC metrics
filed up to that date: Yahoo values and the cached ranking are not point in time.
"""

from collections.abc import Callable
from datetime import date

import pandas as pd

from gabi.domain.market import metrics_comparison as compare
from gabi.domain.market import sec_metrics_v2 as v2

VERSION = "metrics-comparison-v1"
TOP_N = 20
# GICS proxy for the SEC SIC codes V2 treats as financial: banks, insurers and REITs.
FINANCIAL_SECTORS = {"Financials": 6000, "Real Estate": 6798}


def _metric(metric: v2.Metric) -> dict:
    return {"value": metric.value, "state": metric.state, "reason": metric.reason}


def compare_metrics(*, universe: Callable[[], list[tuple[str, str | None]]],
                    facts: Callable[[str, str], dict], v1_metrics: Callable[[dict], dict],
                    infos: Callable[[list[str]], dict[str, dict]], ranking: Callable[[], pd.DataFrame],
                    rescore: Callable[[pd.DataFrame], pd.DataFrame], as_of: date, today: date,
                    progress: Callable[[int, int], None] = lambda done, total: None) -> dict:
    """`facts(symbol, as_of)` returns stored companyfacts filed up to `as_of`; V1 is computed from the same facts."""
    members = universe()
    current = as_of == today
    market = infos([symbol for symbol, _ in members]) if current else {}
    roic_rows, ev_rows, v2_roic = [], [], {}
    for done, (symbol, sector) in enumerate(members, 1):
        companyfacts = facts(symbol, as_of.isoformat())
        sic = FINANCIAL_SECTORS.get(sector or "")
        anchor = v2.latest_annual_end(companyfacts)
        new = v2.roic(companyfacts, anchor, sic=sic) if anchor else v2.Metric(None, "absent", "no_annual_report", "")
        v2_roic[symbol] = new.value
        roic_rows.append({"symbol": symbol, "v1": v1_metrics(companyfacts).get("roic"), "v2": _metric(new)})
        if current:
            info = market.get(symbol) or {}
            ev = (v2.enterprise_value(companyfacts, anchor, info.get("marketCap"), sic=sic) if anchor
                  else v2.Metric(None, "absent", "no_annual_report", ""))
            ev_rows.append({"symbol": symbol, "yahoo": info.get("enterpriseValue"), "v2": _metric(ev)})
        if done % 25 == 0 or done == len(members):
            progress(done, len(members))
    report = {"version": VERSION, "metrics_version": v2.VERSION, "as_of": as_of.isoformat(),
              "sector_proxy": "GICS Financials y Real Estate como no aplicables",
              "roic": compare.roic(roic_rows),
              "enterprise_value": compare.enterprise_value(ev_rows) if current else None,
              "ranking": None}
    if current:
        table = ranking()
        if not table.empty and "composite_score" in table:
            rescored = rescore(table.assign(roic=pd.Series(v2_roic).reindex(table.index)))
            report["ranking"] = compare.ranking(table["composite_score"], rescored["composite_score"], TOP_N)
    return report
