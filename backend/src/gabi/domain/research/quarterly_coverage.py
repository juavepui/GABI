"""Quarterly coverage rows over explicit candidate identity and bounded inputs."""
from dataclasses import dataclass

import pandas as pd

from gabi.domain.research.coverage import CoverageParameters, availability, finite, metric_row


@dataclass(frozen=True)
class CompanyCoverageInputs:
    yahoo: pd.DataFrame
    archive: pd.DataFrame
    facts: pd.DataFrame
    before: pd.DataFrame
    splits: pd.DataFrame
    aliases: pd.DataFrame


def company_quarter(inputs: CompanyCoverageInputs, benchmark: pd.DataFrame, symbol: str, cik: str,
                    as_of: pd.Timestamp, expected_sessions: pd.DatetimeIndex, mapping_block: str,
                    comparison_status: str, *, parameters: CoverageParameters = CoverageParameters()) -> dict:
    day = as_of.date().isoformat()
    spy = benchmark
    empty_prices = pd.DataFrame(columns=["close", "adj_close"], index=pd.DatetimeIndex([]))
    yf_prices, ar_prices = inputs.yahoo.loc[:day], inputs.archive.loc[:day]
    yf_recent = not yf_prices.empty and (as_of - yf_prices.index[-1]).days <= 10
    ar_recent = not ar_prices.empty and (as_of - ar_prices.index[-1]).days <= 10
    source = "yahoo" if yf_recent and (len(yf_prices) >= 253 or not ar_recent) else "archive" if ar_recent else "none"
    price = yf_prices if source == "yahoo" else ar_prices if source == "archive" else empty_prices
    nominal = float(price.close.iloc[-1]) if not price.empty else None
    if nominal is not None and source == "yahoo" and not inputs.splits.empty:
        nominal *= float(inputs.splits.loc[inputs.splits.date > day, "ratio"].prod())
    frame = inputs.facts if not inputs.facts.empty and inputs.facts.filed_date.min() <= day else pd.DataFrame()
    old_frame = inputs.before if not inputs.before.empty and inputs.before.filed_date.min() <= day else pd.DataFrame()
    metrics = metric_row(frame, price, spy, day, nominal_price=nominal, parameters=parameters)
    old_metrics = metric_row(old_frame, empty_prices, empty_prices, day, nominal_price=nominal, parameters=parameters)
    for key in ["momentum_12m", "rel_strength_6m", "price_vs_sma200", "volatility", "max_drawdown"]:
        old_metrics[key] = metrics[key]
    n, eligible = availability(metrics, parameters=parameters)
    old_n, old_eligible = availability(old_metrics, parameters=parameters)
    filed = frame[frame.filed_date <= day].filed_date.max() if not frame.empty else None
    fresh = isinstance(filed, str) and (as_of - pd.Timestamp(filed)).days <= 460
    missing_sessions = len(expected_sessions.difference(price.index))
    full_prices = missing_sessions == 0 and len(expected_sessions) == 253
    proven = inputs.aliases[(inputs.aliases.symbol == symbol) & (inputs.aliases.valid_from <= day)
                     & (inputs.aliases.valid_to.isna() | (inputs.aliases.valid_to > day)) & (inputs.aliases.confidence >= 0.9)]
    identity_verified = bool(cik and set(proven.entity_id) == {f"cik:{cik}"})
    # No pre-2016 GICS snapshots have been independently accredited in
    # this import. SIC is retained in SEC SUB, not silently mapped to GICS.
    row = dict(date=day, symbol=symbol, cik_candidate=cik or "", metrics_available=n,
               all_13=n == 13, eligible_by_metric_rule=eligible, before_metrics_available=old_n,
               before_all_13=old_n == 13, before_eligible_by_metric_rule=old_eligible,
               price_source=source, prices_253_recent=full_prices, missing_price_sessions=missing_sessions,
               fresh_filing=bool(fresh),
               identity_verified=identity_verified, sector_verified=False,
               fully_validated=False, missing_metrics=";".join(m for m in parameters.metrics if not finite(metrics[m])),
               mapping_block=mapping_block, source_comparison=comparison_status)
    return row
