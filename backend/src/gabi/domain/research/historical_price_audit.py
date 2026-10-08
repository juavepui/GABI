"""Historical source selection, holding coverage and audit summaries over supplied evidence."""
from datetime import date

import numpy as np
import pandas as pd

from gabi.domain.market import identity
from gabi.domain.research import issuer_evidence
from gabi.domain.research.periods import P2010
from gabi.domain.research.price_accreditation import (
    ADJUSTED,
    MAX_EVENT_RETURN_DIFFERENCE,
    MAX_P99_RETURN_DIFFERENCE,
    MIN_OVERLAP,
    _adjacent_returns,
    qualify_fallback,
)

QUARTERS = P2010.quarters
MAX_UNCORROBORATED_ARCHIVE_RETURN = 0.25
FORWARD_SLACK_DAYS = 7
ACCEPTED_ADJUSTMENTS = {"dividends_reconciled", "no_dividends_consistent"}

def assess_series(frame: pd.DataFrame, sessions: pd.DatetimeIndex) -> dict:
    """Count real exchange sessions with both nominal and adjusted closes."""
    if frame.empty:
        return {"sessions": 0, "first": None, "last": None, "complete": False,
                "complete_from_first": False}
    valid = frame.reindex(sessions)[["close", "adj_close"]].apply(pd.to_numeric, errors="coerce")
    present = valid.notna().all(axis=1) & np.isfinite(valid).all(axis=1) & valid.gt(0).all(axis=1)
    observed = sessions[present]
    tail = present[present.idxmax():] if present.any() else present
    return {"sessions": len(observed),
            "first": observed[0].date().isoformat() if len(observed) else None,
            "last": observed[-1].date().isoformat() if len(observed) else None,
            "complete": len(observed) == len(sessions),
            # Every session from the first observation to the rebalance date.
            "complete_from_first": bool(len(observed)) and bool(tail.all())}


def same_traded_prices(yahoo: pd.DataFrame, archive: pd.DataFrame, sessions: pd.DatetimeIndex) -> bool:
    """Unadjusted close returns agree on nearly every common day.

    Yahoo closes are split-adjusted and archive closes as traded, so returns
    (not levels) are compared; split days are the only allowed differences.
    """
    common = yahoo[["close"]].join(archive[["close"]], how="inner", lsuffix="_y", rsuffix="_a").astype(float)
    returns = _adjacent_returns(common[(common > 0).all(axis=1)], sessions)
    if len(returns) < MIN_OVERLAP:
        return False
    return bool(((returns["close_y"] - returns["close_a"]).abs() < 1e-3).mean() >= 0.98)


def archive_adjustment(window: pd.DataFrame, facts: dict[str, list[dict]], start: str, end: str,
                       yahoo: pd.DataFrame, sessions: pd.DatetimeIndex) -> tuple[str, list[dict]]:
    """Reconcile an archive window's implied splits and cash events with SEC."""
    events = issuer_evidence.implied_events(window)
    if not events.empty and events.kind.eq("unexplained").any():
        return "unexplained_adjustment", [{"kind": "adjustment", "dates": [
            day.date().isoformat() for day in events[events.kind == "unexplained"].date]}]
    splits_ok, split_refs = issuer_evidence.verify_splits(events, facts)
    if not splits_ok:
        return "split_unverified", split_refs
    returns = _adjacent_returns(window[["adj_close"]].astype(float), sessions)["adj_close"]
    jumps = returns[returns.abs() > MAX_UNCORROBORATED_ARCHIVE_RETURN]
    if not jumps.empty:
        confirmed = yahoo["adj_close"].astype(float).pct_change(fill_method=None).reindex(jumps.index)
        if confirmed.isna().any() or (confirmed - jumps).abs().gt(MAX_EVENT_RETURN_DIFFERENCE).any():
            return "unexplained_jump", [{"kind": "adjustment", "dates": [
                day.date().isoformat() for day in jumps.index]}]
    status, detail = issuer_evidence.reconcile_dividends(events, facts, start, end)
    refs = [{"kind": "adjustment", "method": "split_dividend_reconciliation", "status": status,
             "source_url": issuer_evidence.FRAME_URL.format(
                 taxonomy="us-gaap", tag="CommonStockDividendsPerShareDeclared",
                 unit="USD-per-shares", period="CY{year}Q{quarter}"),
             **detail}, *split_refs]
    return status, refs


def choose_source(identity_tier: str | None, recycled: bool, yahoo: dict,
                  archive: dict, overlap: str, *, issuer: dict | None = None,
                  fallback_proof: dict | None = None, archive_name: str = "finsaber") -> tuple[str | None, str]:
    """Select one full window with identity, SEC listing life and series identity.

    ``issuer`` holds the per-source SEC checks: ``listing`` (failure reason or
    None), ``yahoo_level``/``archive_level`` (``passed``, or ``fingerprint``
    when no level check exists but cash events match the CIK's SEC dividends)
    and ``yahoo_adjustment``/``archive_adjustment``. Yahoo is preferred, but a
    disagreeing archive blocks it unless SEC dividends show Yahoo is right and
    the archive is not (the archive then lacks dividend adjustments).
    """
    if recycled:
        return None, "multiple_ciks_in_window"
    if not identity_tier:
        return None, "identity_unresolved"
    if not yahoo["complete"] and not archive["complete"]:
        return None, "incomplete_prices"
    if issuer is None:
        return None, "issuer_evidence_missing"
    if issuer["listing"]:
        return None, issuer["listing"]
    identified = {"passed", "fingerprint"}
    if overlap in {"divergent_overlap", "divergent_event"}:
        # Only when both sources quote the same traded prices (the difference is
        # purely in adjustments) can SEC dividends decide which one is right.
        resolved = (yahoo["complete"] and issuer["yahoo_level"] in identified and
                    issuer.get("same_traded_prices", False) and
                    issuer.get("yahoo_adjustment") in ACCEPTED_ADJUSTMENTS and
                    issuer.get("archive_adjustment") not in ACCEPTED_ADJUSTMENTS | {"not_assessed"})
        return ("yahoo", "complete_divergence_resolved_by_sec") if resolved else (None, f"sources_{overlap}")
    if yahoo["complete"] and issuer["yahoo_level"] in identified:
        return "yahoo", "complete"
    if archive["complete"]:
        if issuer["archive_level"] not in identified:
            return None, f"price_level_{issuer['archive_level']}"
        if issuer["archive_adjustment"] not in ACCEPTED_ADJUSTMENTS:
            return None, f"archive_{issuer['archive_adjustment']}"
        accepted, reason = qualify_fallback(identity_tier=identity_tier, recycled=recycled,
                                            archive=archive, overlap=overlap, proof=fallback_proof)
        return (archive_name if accepted else None), reason
    return None, f"price_level_{issuer['yahoo_level']}"


def series_identity(checks: list[dict], adjustment: str, refs: list[dict]) -> str:
    """``passed`` level check, else a dividend ``fingerprint``, else the level status."""
    status = issuer_evidence.level_status(checks)
    if status == "missing" and adjustment == "dividends_reconciled" and refs and refs[0].get("fingerprint"):
        return "fingerprint"
    return status


def continued_price_symbols(label: str, symbols: dict[str, str], life: dict | None, complete) -> dict[str, str]:
    """Price symbols that follow the issuer after a ticker change (#34).

    Yahoo keeps an issuer's whole history under its *current* ticker, and a
    label that is no longer the CIK's symbol may now be another company's
    (FB -> META, PCLN -> BKNG). When SEC lists current tickers for the CIK and
    the label is not one of them, Yahoo tries those first; archives try the
    label first. ``complete(source, symbol)`` says whether that series covers
    the window; the first complete one is used. Reviewed nominations win.
    Choosing a symbol is not attribution: listing, level and adjustment
    checks still decide.
    """
    current = [identity.normalize_symbol(ticker) for ticker in (life or {}).get("current_tickers", []) if ticker]
    result = dict(symbols)
    for name, symbol in symbols.items():
        if symbol != label:
            continue
        if name == "yahoo":
            order = [*[t for t in current if t != label], label] if current and label not in current else [label]
        else:
            order = [label, *[t for t in current if t != label]]
        result[name] = next((ticker for ticker in order if complete(name, ticker)), order[0])
    return result


def _as_traded_yahoo(yahoo: pd.DataFrame, splits: pd.DataFrame) -> pd.Series:
    """Yahoo stores closes on today's split basis; known later splits undo it.
    Unknown splits leave the close too low, so the level check fails closed."""
    close = yahoo["close"].astype(float)
    factor = pd.Series(1.0, index=close.index)
    for row in splits.itertuples(index=False):
        factor[factor.index < pd.Timestamp(row.date)] *= float(row.ratio)
    return close * factor


def _level_checks(facts: dict, close: pd.Series, start: str, end: str, *, until: str,
                  splits: pd.Series) -> list[dict]:
    """Float checks inside the window; later floats (up to ``until``) only for
    issuers with none there, e.g. XBRL filers whose first float came later."""
    checks = issuer_evidence.price_level_checks(facts, close, start, end, splits=splits)
    if issuer_evidence.level_status(checks) != "missing" or until <= end:
        return checks
    return issuer_evidence.price_level_checks(facts, close, start, end, until=until, splits=splits)


def _split_ratios(frame: pd.DataFrame) -> pd.Series:
    """Split ratios by ex-date implied by an as-traded archive series."""
    if frame.empty:
        return pd.Series(dtype=float)
    events = issuer_evidence.implied_events(frame)
    splits = events[events.kind == "split"] if not events.empty else events
    return pd.Series(splits.ratio.astype(float).to_numpy(), index=pd.DatetimeIndex(splits.date))         if not splits.empty else pd.Series(dtype=float)


def _proof(listing_refs: list[dict], adjustment_refs: list[dict], start: str, end: str) -> dict:
    first = next(ref for ref in listing_refs if ref["kind"] == "first_trade")
    last = next(ref for ref in listing_refs if ref["kind"] == "last_trade")
    return {"first_trade": first["date"], "last_trade": last["date"],
            "boundary_evidence": [first, last], "adjustment_basis": ADJUSTED,
            "adjustment_evidence": adjustment_refs,
            "corporate_action_evidence": [{"kind": "corporate_actions", "valid_from": start,
                                           "valid_to": end, "source_url": last["source_url"]}]}


def _short_history(member: dict, sessions: pd.DatetimeIndex, yahoo: pd.DataFrame, archive: pd.DataFrame,
                   yc: dict, ac: dict, life: dict | None, facts: dict, splits: pd.DataFrame
                   ) -> tuple[str | None, str, dict]:
    """Accredit a series that starts at a SEC-registered listing inside the window."""
    for name, frame, stats in (("yahoo", yahoo, yc), ("finsaber", archive, ac)):
        if not stats["complete_from_first"] or stats["first"] == sessions[0].date().isoformat():
            continue
        start_ref = issuer_evidence.listing_start(life, stats["first"])
        if start_ref is None:
            continue
        end = sessions[-1].date().isoformat()
        reason, refs = issuer_evidence.listing_checks(
            {**life, "first_periodic": stats["first"]} if life else None, stats["first"], end)
        if reason:
            return None, reason, {}
        close = _as_traded_yahoo(frame, splits) if name == "yahoo" else frame["close"].astype(float)
        checks = issuer_evidence.price_level_checks(facts, close, stats["first"], end)
        if issuer_evidence.level_status(checks) == "failed":
            return None, "price_level_failed", {}
        detail = {"listing_refs": [start_ref, *refs[1:]], "level_checks": checks}
        if name == "finsaber":
            status, adj_refs = archive_adjustment(frame.loc[stats["first"]:], facts, stats["first"], end,
                                                  yahoo, sessions[sessions >= pd.Timestamp(stats["first"])])
            if status not in ACCEPTED_ADJUSTMENTS:
                return None, f"archive_{status}", {}
            detail["adjustment_refs"] = adj_refs
        return name, "short_history", detail
    return None, "incomplete_prices", {}


def forward_coverage(series: pd.DataFrame, calendar, window_end: str, horizon: str, life: dict | None,
                     *, archive: bool, identity_end: str | None = None) -> tuple[str | None, str]:
    """Verify the holding period after an accredited window on the same source.

    Returns the last session covered and a status: ``covered`` (every
    session to the next rebalance), ``terminal`` (the series ends at an SEC
    delisting, whose economic treatment is a terminal event), ``succession``
    (cut before a holding-company succession), ``gap`` (missing sessions) or
    ``unreconciled_event`` (cut before an unexplained archive adjustment).
    """
    start = pd.Timestamp(window_end)
    bound = pd.Timestamp(horizon) + pd.Timedelta(days=FORWARD_SLACK_DAYS)
    status = "covered"
    delisting = (life or {}).get("delisting")
    if delisting and start < pd.Timestamp(delisting["filed"]) <= bound:
        bound, status = pd.Timestamp(delisting["filed"]), "terminal"
    for event in (life or {}).get("successions", []):
        filed = pd.Timestamp(event["filed"])
        if start < filed <= bound:
            bound, status = filed - pd.Timedelta(days=1), "succession"
    # The label may pass to another CIK (ticker change or reuse): the holding
    # of this issuer's series is never extended across that boundary.
    if identity_end and start < pd.Timestamp(identity_end) <= bound:
        bound, status = pd.Timestamp(identity_end) - pd.Timedelta(days=1), "identity_boundary"
    expected = calendar.sessions[(calendar.sessions > start) & (calendar.sessions <= bound)]
    if expected.empty:
        return window_end, status
    frame = series.reindex(expected)[["close", "adj_close"]].apply(pd.to_numeric, errors="coerce")
    present = frame.notna().all(axis=1) & frame.gt(0).all(axis=1)
    if not present.all():
        first_missing = present.index[~present.to_numpy()][0]
        covered = present.index[present.index < first_missing]
        # A series that stops a few sessions before the SEC delisting is the
        # end of trading, not a gap.
        tail_ok = status == "terminal" and not present.loc[first_missing:].any() and \
            len(present.loc[first_missing:]) <= 10
        last = covered[-1].date().isoformat() if len(covered) else window_end
        return last, (status if tail_ok else "gap")
    if archive:
        window = series.loc[start:bound, ["close", "adj_close"]].astype(float)
        events = issuer_evidence.implied_events(window)
        returns = window["adj_close"].pct_change(fill_method=None)
        bad = sorted([*events.loc[events.kind == "unexplained", "date"]] if not events.empty else [])
        bad += list(returns[returns.abs() > MAX_UNCORROBORATED_ARCHIVE_RETURN].index)
        if bad:
            first = min(bad)
            before = expected[expected < first]
            return (before[-1].date().isoformat() if len(before) else window_end), "unreconciled_event"
    return expected[-1].date().isoformat(), status


def _next_rebalance(as_of: str, quarters: list[str] = QUARTERS) -> str:
    index = quarters.index(as_of) if as_of in quarters else -1
    if 0 <= index < len(quarters) - 1:
        return quarters[index + 1]
    day = date.fromisoformat(as_of)
    return (pd.Timestamp(day) + pd.offsets.QuarterEnd(1)).date().isoformat()

def _nominated_price_symbol(label: str, cik: str | None, as_of: str, source: str, nominations: tuple[dict, ...]) -> str:
    for row in nominations:
        if (row["label"] == label and row["cik"] == cik and
                row["valid_from"] <= as_of < row["valid_to"] and source in row.get("price_symbols", {})):
            return row["price_symbols"][source]
    return label

def summarize(result: pd.DataFrame, database_name: str, price_source_id: str, extra_sources: dict) -> dict:
    summary: dict = {"database": database_name, "price_source_id": price_source_id,
                     "session_definition": "last 253 XNYS sessions through each rebalance date",
                     "fallback_rule": "SEC listing life, SEC public-float price level and split/dividend "
                     f"reconciliation; any Yahoo overlap needs >= {MIN_OVERLAP} returns, p99 difference <= "
                     f"{MAX_P99_RETURN_DIFFERENCE} and no day above {MAX_EVENT_RETURN_DIFFERENCE}",
                     "price_attribution": "entity intervals stored separately from legacy prices",
                     "years": []}
    members = result[result.symbol != "SPY"].copy()
    members["usable"] = members.price_attribution.eq("accredited_entity_interval")
    members["usable_full"] = members.usable & members.history.eq("full_window")
    for year, group in members.groupby("year"):
        summary["years"].append({"year": int(year), "members": len(group),
                                 "identity_accredited": int(group.cik.notna().sum()),
                                 "yahoo_complete": int(group.yahoo_sessions.eq(group.expected_sessions).sum()),
                                 "finsaber_complete": int(group.finsaber_sessions.eq(group.expected_sessions).sum()),
                                 "tier_a": int((group.usable & group.selected_source.eq("yahoo")).sum()),
                                 "tier_b": int((group.usable & group.selected_source.isin(["finsaber", *extra_sources])).sum()),
                                 "tier_b_by_source": {name: int((group.usable & group.selected_source.eq(name)).sum())
                                                      for name in ("finsaber", *extra_sources)},
                                 "usable_full_window": int(group.usable_full.sum()),
                                 "usable_short_history": int((group.usable & ~group.usable_full).sum()),
                                 "excluded": int((~group.usable).sum()),
                                 "reasons": group[~group.usable].coverage_status.value_counts().to_dict()})
    summary["rebalances"] = [{"as_of": as_of, "members": len(group),
                               "identity_accredited": int(group.cik.notna().sum()),
                               "usable_full_window": int(group.usable_full.sum()),
                               "usable_including_short_history": int(group.usable.sum()),
                               "usable_pct": round(100 * group.usable.mean(), 2),
                               "usable_full_window_pct": round(100 * group.usable_full.mean(), 2),
                               "forward": group.forward_status.value_counts().to_dict(),
                               "excluded_reasons": group[~group.usable].coverage_status.value_counts().to_dict()}
                              for as_of, group in members.groupby("as_of")]
    summary["spy_complete_all_years"] = bool(result[result.symbol == "SPY"].coverage_status.eq("complete").all())
    members["sic_2digit"] = members.sic.fillna("unknown").astype(str).str[:2]
    members["float_quintile"] = members.groupby("as_of").public_float_usd.transform(
        lambda values: pd.qcut(values.rank(method="first"), 5, labels=False) + 1 if values.notna().sum() >= 5 else np.nan)
    summary["bias_diagnostics"] = {
        "sic_2digit": [{"sic_2digit": code, "observations": len(group), "usable": int(group.usable.sum())}
                       for code, group in members.groupby("sic_2digit")],
        "membership_exit_next_365d": [{"exit_next_year": bool(flag), "observations": len(group),
                                       "usable": int(group.usable.sum())}
                                      for flag, group in members.groupby("membership_exit_next_365d")],
        "public_float_quintile": [{"quintile": int(q), "observations": len(group), "usable": int(group.usable.sum())}
                                  for q, group in members.dropna(subset=["float_quintile"]).groupby("float_quintile")],
        "public_float_missing": {"observations": int(members.public_float_usd.isna().sum()),
                                 "usable": int(members[members.public_float_usd.isna()].usable.sum())},
        "note": "SIC is an issuer-level proxy, not historical GICS; public float (SEC dei, latest before the "
                "rebalance) is a size proxy; repeated quarterly members are not independent"}
    return summary
