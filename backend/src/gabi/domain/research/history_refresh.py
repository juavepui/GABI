"""Rules of the free-source research data refresh: targets, issuer identity and price windows; no I/O."""

from datetime import timedelta

import pandas as pd

from gabi.domain.research.membership import symbols

SHARE_CLASS_SPELLINGS = ("BRK.B", "BF.B")
PRICE_COLUMNS = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "adj_close": "Adj Close",
                 "volume": "Volume"}


def period_symbols(history: pd.DataFrame, start: str, end: str) -> list[str]:
    """Every member from the composition in force at ``start`` through the changes up to ``end``."""
    selected = pd.concat([history[history["date"] <= start].tail(1),
                          history[(history["date"] > start) & (history["date"] <= end)]])
    return sorted(set().union(*(symbols(s) for s in selected["tickers"])))


def renamed_events(ledger: dict) -> dict[str, dict]:
    """Reviewed ticker changes and merger renames, by the removed ticker."""
    return {e["removed"]: e for e in ledger["events"] if e["kind"] in {"ticker_change", "merger_rename"}}


def issuer_ciks(targets: list[str], renamed: dict[str, dict], live_ciks: dict, stored_ciks: dict,
                former_issuers: dict) -> tuple[dict[str, str], dict[str, str]]:
    """SEC CIK per target, and the targets blocked until an identity review.

    A stored CIK that differs from the live issuer, or a reviewed former issuer that differs,
    blocks the symbol instead of silently switching issuers."""
    ciks, blocked = {}, {}
    for symbol in targets:
        successor = renamed.get(symbol, {}).get("added", symbol)
        reviewed_cik = former_issuers.get(symbol, {}).get("cik")
        cik = live_ciks.get(successor) or stored_ciks.get(symbol) or reviewed_cik
        previous = stored_ciks.get(symbol)
        if (previous and cik and previous != cik) or (reviewed_cik and cik != reviewed_cik):
            blocked[symbol] = "Stored CIK differs from live issuer; requires identity review"
        elif cik:
            ciks[symbol] = cik
        else:
            blocked[symbol] = "No confirmed SEC CIK available"
    return ciks, blocked


def download_end(latest_completed_session: str) -> str:
    """Exclusive end date of a provider download that stops at the last completed session."""
    return (pd.Timestamp(latest_completed_session) + timedelta(days=1)).date().isoformat()


def needs_price_refresh(event: dict | None, latest_adjusted: str, latest_session: str) -> bool:
    """Renamed tickers are always replaced up to their change; others only when stale."""
    return bool(event) or latest_adjusted < latest_session


def complete_series(frame: pd.DataFrame, end: str, valid_to: str | None) -> tuple[pd.DataFrame, dict[str, float]]:
    """Provider rows before the cutoff with close and adjusted close, and the series' splits.

    Former tickers stop at their reviewed change (``valid_to``); an acquirer's series is never copied."""
    if frame.empty or "Adj Close" not in frame or frame["Adj Close"].dropna().empty:
        raise ValueError("No adjusted prices returned")
    splits = ({d.strftime("%Y-%m-%d"): float(v) for d, v in frame["Stock Splits"].items()
               if pd.notna(v) and v != 0} if "Stock Splits" in frame else {})
    cutoff = min(end, valid_to) if valid_to else end
    frame = frame.loc[frame.index.strftime("%Y-%m-%d") < cutoff].dropna(subset=["Close", "Adj Close"])
    if frame.empty:
        raise ValueError("No prices before cutoff")
    return frame, splits


def share_class_rows(source: pd.DataFrame, target: pd.DataFrame, end: str) -> pd.DataFrame | None:
    """Rows of the dotted spelling missing under Yahoo's dash spelling, in provider columns.

    Only when the last five common closes and adjustment basis match; never overwrites a
    canonical observation or treats an issuer rename as a spelling change."""
    if source.empty or target.empty:
        return None
    overlap = source.index.intersection(target.index).sort_values()[-5:]
    columns = ["close", "adj_close"]
    if len(overlap) < 5:
        return None
    difference = (source.loc[overlap, columns] - target.loc[overlap, columns]).abs()
    if not (difference <= 1e-6).all().all():
        return None
    missing = source[(source.index > overlap.max()) & (source.index < pd.Timestamp(end))
                     & ~source.index.isin(target.index)].dropna(subset=columns)
    return None if missing.empty else missing.rename(columns=PRICE_COLUMNS)
