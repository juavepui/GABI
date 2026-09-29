"""Quarterly 1996-2015 data audit; no strategy fitting or return backtest.

Reports numerical metric availability separately from certified historical
identity, sector and source continuity. Community mappings are candidates only.
"""
import json
import math
import sqlite3
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

from . import config, edgar, historical_archive, risk, scoring, storage, technicals
from .sec_history import DIRECTORY

METRICS = [m for block in scoring.SCORE_METRICS.values() for m in block]


def fact_structure(frame: pd.DataFrame, as_of: str) -> dict:
    if frame.empty:
        return {"facts": {"us-gaap": {}}}
    frame = frame[(frame.filed_date <= as_of) & (frame.end_date <= as_of)].sort_values(["filed_date", "end_date", "accn"])
    result: dict = {}
    for row in frame.itertuples(index=False):
        entries = result.setdefault(row.tag, {"units": {}})["units"].setdefault(row.unit, [])
        entries.append(dict(start=row.start_date or None, end=row.end_date, val=row.val,
                            form=row.form, fp=row.fp, fy=row.fy, filed=row.filed_date, accn=row.accn))
    return {"facts": {"us-gaap": result}}


def finite(value) -> bool:
    return value is not None and not pd.isna(value) and math.isfinite(float(value))


def metric_row(facts: pd.DataFrame, prices: pd.DataFrame, benchmark: pd.DataFrame,
               as_of: str, *, nominal_price: float | None) -> dict:
    """Same 13 ingredients/formulas as GABI; undefined ratios remain missing."""
    result = dict.fromkeys(METRICS)
    facts = facts[(facts.filed_date <= as_of) & (facts.end_date <= as_of)] if not facts.empty else facts
    m = edgar.compute_edgar_metrics(fact_structure(facts, as_of))
    shares = facts[(facts.tag.isin(edgar.SHARES_TAGS)) & (facts.unit == "shares")] if not facts.empty else facts
    count = float(shares.sort_values(["filed_date", "end_date"]).iloc[-1].val) if not shares.empty else None
    cap = nominal_price * count if nominal_price and count and count > 0 else None
    ni, equity, ebitda = (m.get(k) for k in ["latest_net_income", "latest_equity", "latest_ebitda"])
    debt, cash = m.get("latest_debt"), m.get("latest_cash")
    result["pe"] = cap / ni if cap and ni and ni > 0 else None
    result["pb"] = cap / equity if cap and equity and equity > 0 else None
    ev = cap + (debt or 0) - (cash or 0) if cap else None
    result["ev_ebitda"] = ev / ebitda if ev and ebitda and ebitda > 0 else None
    result["debt_to_equity"] = debt / equity * 100 if debt is not None and equity and equity > 0 else None
    for key in scoring.SCORE_METRICS["quality"]:
        result[key] = m.get(key)
    prices = prices.loc[:as_of]
    benchmark = benchmark.loc[:as_of]
    if not prices.empty:
        close = prices.adj_close
        result["momentum_12m"] = technicals._pct_change_n(close, config.MOMENTUM_LONG_DAYS)
        short = technicals._pct_change_n(close, config.MOMENTUM_SHORT_DAYS)
        bench = technicals._pct_change_n(benchmark.adj_close, config.MOMENTUM_SHORT_DAYS) if not benchmark.empty else None
        result["rel_strength_6m"] = short - bench if short is not None and bench is not None else None
        if len(close) >= config.SMA_LONG:
            result["price_vs_sma200"] = float(close.iloc[-1] / close.tail(config.SMA_LONG).mean() - 1)
        result["volatility"] = risk._annualized_volatility(close.pct_change(fill_method=None).dropna())
        result["max_drawdown"] = risk._max_drawdown(prices)
    return result


def availability(metrics: dict) -> tuple[int, bool]:
    count = sum(finite(metrics.get(m)) for m in METRICS)
    core = all(any(finite(metrics.get(m)) for m in scoring.SCORE_METRICS[b]) for b in ["value", "quality", "momentum"])
    return count, bool(count / len(METRICS) >= scoring.MIN_SCORE_COVERAGE and core)


def read_facts(path: Path) -> dict[str, pd.DataFrame]:
    with sqlite3.connect(path) as conn:
        records: dict = {}
        for cik, payload in conn.execute("SELECT e.cik,o.payload_json FROM entity_observations o JOIN entities e USING(entity_id) "
                                         "WHERE o.dataset='edgar_facts' AND json_extract(o.payload_json,'$.filed_date')<'2016-01-01'"):
            if cik:
                records.setdefault(cik, []).append(json.loads(payload))
    return {cik: pd.DataFrame(rows).drop_duplicates(["tag", "unit", "start_date", "end_date", "accn"])
            for cik, rows in records.items()}


def compare_prices(yahoo: pd.DataFrame, archive: pd.DataFrame) -> dict:
    """Compare returns, not differently adjusted price levels. Not identity proof."""
    aligned = pd.concat([yahoo.adj_close.rename("yahoo"), archive.adj_close.rename("archive")], axis=1, sort=True).dropna()
    returns = aligned.pct_change(fill_method=None).dropna()
    if len(returns) < 60:
        return {"overlap_returns": len(returns), "status": "insufficient_overlap", "p99_return_difference": None}
    difference = (returns.yahoo - returns.archive).abs()
    q = float(difference.quantile(0.99))
    return {"overlap_returns": len(returns), "status": "consistent_overlap" if q <= 0.005 else "disagreement",
            "p99_return_difference": q, "max_return_difference": float(difference.max())}


def run() -> dict:
    output = DIRECTORY / "coverage"
    output.mkdir(exist_ok=True)
    manifest = json.loads((Path(__file__).with_name("resources") / "historical_sources_1996_2015.json").read_text())
    with storage.get_connection() as conn:
        members = pd.read_sql_query("SELECT date,tickers FROM historical_membership WHERE source_id=? ORDER BY date", conn,
                                    params=[manifest["membership_source_id"]])
        candidates = pd.read_sql_query("SELECT symbol,cik,date_added,observed_from AS created_at FROM historical_issuer_candidates WHERE source_id=?", conn,
                                       params=[manifest["issuer_source_id"]])
        stored = dict(conn.execute("SELECT symbol,cik FROM edgar_metrics"))
        raw = pd.read_sql_query("SELECT symbol,date,close,adj_close FROM prices WHERE date<'2016-01-01' AND adj_close>0 AND close>0", conn)
        archived = pd.read_sql_query("SELECT symbol,date,close,adj_close FROM historical_prices WHERE source_id=? AND date<'2016-01-01'", conn,
                                    params=[manifest["price_source_id"]])
        splits = pd.read_sql_query("SELECT symbol,date,ratio FROM splits", conn)
        aliases = pd.read_sql_query("SELECT * FROM entity_aliases", conn)
    live_frame = pd.read_csv(config.DATA_DIR / "sec_cik_map.csv", dtype=str)
    live = dict(zip(live_frame.symbol, live_frame.cik.str.zfill(10), strict=True))
    targets = {s for value in members.tickers for s in value.split(",")}
    mappings, blocked = historical_archive.unique_historical_ciks(candidates, targets, live, stored)
    # Pilot documents provide issuer evidence for extraction; still not dated aliases.
    pilot = json.loads((Path(__file__).with_name("resources") / "legacy_filings_pilot.json").read_text())
    mappings.update({r["symbol"]: r["cik"] for r in pilot if r["symbol"] not in mappings})
    empty_prices = pd.DataFrame(columns=["close", "adj_close"], index=pd.DatetimeIndex([]))
    def price_groups(frame):
        frame["date"] = pd.to_datetime(frame.date)
        return {s: g.set_index("date")[["close", "adj_close"]].sort_index() for s, g in frame.groupby("symbol")}
    yahoo, archive = price_groups(raw), price_groups(archived)
    print("Price sources loaded", flush=True)
    facts = read_facts(config.DB_PATH)
    before = read_facts(DIRECTORY / "before_validation.db")
    first_filed = {cik: frame.filed_date.min() for cik, frame in facts.items()}
    before_first_filed = {cik: frame.filed_date.min() for cik, frame in before.items()}
    print("Exact issuer facts loaded", flush=True)
    spy = yahoo.get("SPY", empty_prices)
    comparisons = {s: compare_prices(yahoo.get(s, empty_prices), archive.get(s, empty_prices)) for s in sorted(targets)}
    pd.DataFrame([dict(symbol=s, **r) for s, r in comparisons.items()]).to_csv(output / "price-validation.csv", index=False)
    split_map = {s: g for s, g in splits.groupby("symbol")}
    sessions = xcals.get_calendar("XNYS", start="1994-01-01", end="2016-01-01").sessions
    details, quarters = [], []
    for as_of in pd.date_range("1996-03-31", "2015-12-31", freq="QE"):
        day = as_of.date().isoformat()
        expected_sessions = sessions[sessions <= as_of][-253:]
        symbols = members[members.date <= day].iloc[-1].tickers.split(",")
        quarter_rows = []
        for symbol in symbols:
            cik = mappings.get(symbol, "")
            yf_prices, ar_prices = yahoo.get(symbol, empty_prices).loc[:day], archive.get(symbol, empty_prices).loc[:day]
            yf_recent = not yf_prices.empty and (as_of - yf_prices.index[-1]).days <= 10
            ar_recent = not ar_prices.empty and (as_of - ar_prices.index[-1]).days <= 10
            source = "yahoo" if yf_recent and (len(yf_prices) >= 253 or not ar_recent) else "archive" if ar_recent else "none"
            price = yf_prices if source == "yahoo" else ar_prices if source == "archive" else empty_prices
            nominal = float(price.close.iloc[-1]) if not price.empty else None
            if nominal is not None and source == "yahoo" and symbol in split_map:
                nominal *= float(split_map[symbol].loc[split_map[symbol].date > day, "ratio"].prod())
            frame = facts.get(cik, pd.DataFrame()) if first_filed.get(cik, "9999") <= day else pd.DataFrame()
            old_frame = before.get(cik, pd.DataFrame()) if before_first_filed.get(cik, "9999") <= day else pd.DataFrame()
            metrics = metric_row(frame, price, spy, day, nominal_price=nominal)
            old_metrics = metric_row(old_frame, empty_prices, empty_prices, day, nominal_price=nominal)
            for key in ["momentum_12m", "rel_strength_6m", "price_vs_sma200", "volatility", "max_drawdown"]:
                old_metrics[key] = metrics[key]
            n, eligible = availability(metrics)
            old_n, old_eligible = availability(old_metrics)
            filed = frame[frame.filed_date <= day].filed_date.max() if not frame.empty else None
            fresh = isinstance(filed, str) and (as_of - pd.Timestamp(filed)).days <= 460
            missing_sessions = len(expected_sessions.difference(price.index))
            full_prices = missing_sessions == 0 and len(expected_sessions) == 253
            proven = aliases[(aliases.symbol == symbol) & (aliases.valid_from <= day)
                             & (aliases.valid_to.isna() | (aliases.valid_to > day)) & (aliases.confidence >= 0.9)]
            identity_verified = bool(cik and set(proven.entity_id) == {f"cik:{cik}"})
            # No pre-2016 GICS snapshots have been independently accredited in
            # this import. SIC is retained in SEC SUB, not silently mapped to GICS.
            row = dict(date=day, symbol=symbol, cik_candidate=cik or "", metrics_available=n,
                       all_13=n == 13, eligible_by_metric_rule=eligible, before_metrics_available=old_n,
                       before_all_13=old_n == 13, before_eligible_by_metric_rule=old_eligible,
                       price_source=source, prices_253_recent=full_prices, missing_price_sessions=missing_sessions,
                       fresh_filing=bool(fresh),
                       identity_verified=identity_verified, sector_verified=False,
                       fully_validated=False, missing_metrics=";".join(m for m in METRICS if not finite(metrics[m])),
                       mapping_block=blocked.get(symbol, ""), source_comparison=comparisons[symbol]["status"])
            details.append(row)
            quarter_rows.append(row)
        group = pd.DataFrame(quarter_rows)
        counts = {key: int(group[key].sum()) for key in ["all_13", "eligible_by_metric_rule", "before_all_13",
                   "before_eligible_by_metric_rule", "prices_253_recent", "fresh_filing", "identity_verified", "sector_verified", "fully_validated"]}
        counts["all_13_fresh_prices_and_filing"] = int((group.all_13 & group.prices_253_recent & group.fresh_filing).sum())
        quarters.append(dict(date=day, members=len(symbols), **counts))
        print(day, "complete metrics", counts["all_13"], "/", len(symbols), flush=True)
    pd.DataFrame(details).to_csv(output / "company-quarter.csv", index=False)
    pd.DataFrame(quarters).to_csv(output / "quarterly.csv", index=False)
    missing = pd.DataFrame(details).assign(metric=lambda f: f.missing_metrics.str.split(";")).explode("metric")
    missing[missing.metric != ""].groupby(["date", "metric"]).size().rename("companies").reset_index().to_csv(output / "missing-metrics.csv", index=False)
    summary = dict(quarters=len(quarters), company_quarters=len(details), metrics=METRICS,
                   numerical_only=True, sector_verified=False,
                   source_comparison=pd.Series([r["status"] for r in comparisons.values()]).value_counts().to_dict(),
                   final_quarter=quarters[-1])
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    run()
