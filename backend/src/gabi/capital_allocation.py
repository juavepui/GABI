"""Métricas point-in-time sobre cómo una empresa asigna su capital.

Estas métricas son descriptivas y no modifican el Composite congelado. Solo
usan hechos XBRL cuya fecha de presentación es anterior a ``as_of_date`` y
devuelven ``None`` cuando no existe cobertura suficiente.
"""
from __future__ import annotations

import pandas as pd

BUYBACK_TAGS = [
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsForRepurchaseOfCommonAndPreferredStock",
]
ISSUANCE_TAGS = [
    "ProceedsFromStockOptionsExercised",
    "ProceedsFromStockIssuedUnderIncentiveAndStockOptionPlans",
    "ProceedsFromIssuanceOfCommonStock",
]
ACQUISITION_TAGS = [
    "PaymentsToAcquireBusinessesNetOfCashAcquired",
    "PaymentsToAcquireBusinesses",
    "PaymentsToAcquireInterestInSubsidiariesAndAffiliates",
]
CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForCapitalImprovements"]
OCF_TAGS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]
SHARES_TAGS = ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"]


def _annual_series(facts: pd.DataFrame, tags: list[str], as_of_date: str) -> pd.Series:
    """Último valor anual por fecha de cierre, usando solo filings conocidos."""
    if facts.empty:
        return pd.Series(dtype=float)
    frame = facts[
        facts["tag"].isin(tags)
        & (facts["unit"] == "USD")
        & facts["filed_date"].notna()
        & (facts["filed_date"] <= as_of_date)
        & facts["start_date"].notna()
    ].copy()
    if frame.empty:
        return pd.Series(dtype=float)
    frame["duration"] = (pd.to_datetime(frame["end_date"]) - pd.to_datetime(frame["start_date"])).dt.days
    # Prefer 10-K annual facts; duration fallback handles issuers that omit form.
    frame = frame[((frame["form"] == "10-K") & frame["duration"].between(300, 400))
                  | frame["duration"].between(330, 400)]
    if frame.empty:
        return pd.Series(dtype=float)
    frame = frame.sort_values(["end_date", "filed_date", "tag"])
    return frame.drop_duplicates("end_date", keep="last").set_index("end_date")["val"].astype(float)


def _instant_series(facts: pd.DataFrame, tags: list[str], as_of_date: str) -> pd.Series:
    if facts.empty:
        return pd.Series(dtype=float)
    frame = facts[
        facts["tag"].isin(tags)
        & (facts["unit"] == "shares")
        & facts["filed_date"].notna()
        & (facts["filed_date"] <= as_of_date)
    ].copy()
    if frame.empty:
        return pd.Series(dtype=float)
    frame = frame.sort_values(["end_date", "filed_date", "tag"])
    return frame.drop_duplicates("end_date", keep="last").set_index("end_date")["val"].astype(float)


def metrics(facts: pd.DataFrame, as_of_date: str, *, market_cap: float | None = None) -> dict:
    """Calcula métricas anuales y de acciones conocidas en ``as_of_date``."""
    buybacks = _annual_series(facts, BUYBACK_TAGS, as_of_date)
    issuance = _annual_series(facts, ISSUANCE_TAGS, as_of_date)
    acquisitions = _annual_series(facts, ACQUISITION_TAGS, as_of_date)
    capex = _annual_series(facts, CAPEX_TAGS, as_of_date)
    ocf = _annual_series(facts, OCF_TAGS, as_of_date)
    shares = _instant_series(facts, SHARES_TAGS, as_of_date)

    def latest(series: pd.Series):
        return float(series.iloc[-1]) if not series.empty else None

    latest_buybacks = abs(latest(buybacks)) if latest(buybacks) is not None else None
    latest_issuance = abs(latest(issuance)) if latest(issuance) is not None else None
    latest_acquisitions = abs(latest(acquisitions)) if latest(acquisitions) is not None else None
    latest_capex = abs(latest(capex)) if latest(capex) is not None else None
    latest_ocf = latest(ocf)
    latest_shares = latest(shares)
    prior_shares = float(shares.iloc[-2]) if len(shares) >= 2 else None
    dilution = (latest_shares / prior_shares - 1) if latest_shares and prior_shares and prior_shares > 0 else None
    net_issuance = (latest_issuance or 0) - (latest_buybacks or 0) if latest_issuance is not None or latest_buybacks is not None else None

    available = sum(v is not None for v in (dilution, latest_buybacks, latest_issuance,
                                             latest_capex, latest_acquisitions))
    return {
        "shares_dilution_yoy": dilution,
        "buybacks_latest": latest_buybacks,
        "issuance_latest": latest_issuance,
        "net_share_issuance_latest": net_issuance,
        "buyback_yield": (latest_buybacks / market_cap if latest_buybacks is not None and market_cap and market_cap > 0 else None),
        "capex_latest": latest_capex,
        "capex_to_ocf": (latest_capex / latest_ocf if latest_capex is not None and latest_ocf and latest_ocf > 0 else None),
        "acquisitions_latest": latest_acquisitions,
        "capital_allocation_available": available,
        "capital_allocation_coverage": f"{available}/5",
    }
