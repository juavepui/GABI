"""Refresh the local research data from free sources, with backup and coverage audit.

Run: python -m gabi.history_refresh
The reviewed membership ledger deliberately has a fixed verification horizon.
"""
import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from io import StringIO

import exchange_calendars as xcals
import pandas as pd
import requests
import yfinance as yf

from . import config, data_fetch, edgar, macro, storage, universe
from .membership_extension import LEDGER_PATH, extend_membership, symbols


def last_completed_session(now: datetime) -> str:
    calendar = xcals.get_calendar("XNYS")
    session = calendar.date_to_session(now.date().isoformat(), direction="previous")
    if calendar.session_close(session) > pd.Timestamp(now):
        session = calendar.previous_session(session)
    return session.date().isoformat()


def period_symbols(history: pd.DataFrame, start: str, end: str) -> list[str]:
    selected = pd.concat([history[history["date"] <= start].tail(1),
                          history[(history["date"] > start) & (history["date"] <= end)]])
    return sorted(set().union(*(symbols(s) for s in selected["tickers"])))


def database_coverage() -> dict:
    with storage.get_connection() as conn:
        result = {}
        for table, column in [("prices", "date"), ("edgar_facts", "filed_date"), ("macro_series", "date")]:
            row = conn.execute(f"SELECT COUNT(*),MIN({column}),MAX({column}) FROM {table}").fetchone()
            result[table] = dict(zip(["rows", "first", "last"], row, strict=True))
        result["macro_by_series"] = {
            sid: {"first": lo, "last": hi, "rows": count}
            for sid, lo, hi, count in conn.execute(
                "SELECT series_id,MIN(date),MAX(date),COUNT(*) FROM macro_series GROUP BY series_id")
        }
        return result


def restore_share_class_spelling(end: str) -> dict:
    """Reuse existing Yahoo rows for BRK.B/BF.B under Yahoo's dash spelling.

    Require matching recent closes and adjustment basis; never overwrite a
    canonical observation or treat an issuer rename as a spelling change.
    """
    restored = {}
    for original in ("BRK.B", "BF.B"):
        canonical = original.replace(".", "-")
        source, target = storage.get_prices(original), storage.get_prices(canonical)
        if source.empty or target.empty:
            continue
        overlap = source.index.intersection(target.index).sort_values()[-5:]
        columns = ["close", "adj_close"]
        if len(overlap) < 5:
            continue
        difference = (source.loc[overlap, columns] - target.loc[overlap, columns]).abs()
        if not (difference <= 1e-6).all().all():
            continue
        missing = source[(source.index > overlap.max()) & (source.index < pd.Timestamp(end))
                         & ~source.index.isin(target.index)].dropna(subset=columns)
        if missing.empty:
            continue
        frame = missing.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close",
                                        "adj_close": "Adj Close", "volume": "Volume"})
        storage.upsert_prices(canonical, frame)
        restored[canonical] = {"source_symbol": original, "dates": missing.index.strftime("%Y-%m-%d").tolist()}
    return restored


def refresh_prices(symbol: str, download_symbol: str, end: str, valid_to: str | None = None) -> int:
    """Replace a complete provider series, excluding incomplete sessions.

    Former tickers may use an explicitly reviewed successor, only before the
    ticker change. Never copy an acquired company's acquirer series.
    """
    frame = yf.Ticker(download_symbol).history(period="max", end=end, auto_adjust=False)
    if frame.empty or "Adj Close" not in frame or frame["Adj Close"].dropna().empty:
        raise ValueError("No adjusted prices returned")
    splits = ({d.strftime("%Y-%m-%d"): float(v) for d, v in frame["Stock Splits"].items()
               if pd.notna(v) and v != 0} if "Stock Splits" in frame else {})
    cutoff = min(end, valid_to) if valid_to else end
    frame = frame.loc[frame.index.strftime("%Y-%m-%d") < cutoff].dropna(subset=["Close", "Adj Close"])
    if frame.empty:
        raise ValueError("No prices before cutoff")
    from . import identity
    owner = identity.resolve(symbol, datetime.now(UTC).date().isoformat())["entity_id"]
    storage.upsert_prices(symbol, frame, entity_id=owner)
    # Later splits also adjust earlier prices, even after a ticker rename.
    storage.upsert_splits(symbol, splits, entity_id=owner)
    return len(frame)


def run() -> dict:
    now = datetime.now(UTC)
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    today = now.date().isoformat()
    if today != ledger["verified_through"]:
        raise ValueError("Review the membership ledger through today before running a new refresh")
    directory = config.DATA_DIR / "history_refresh" / now.strftime("%Y%m%dT%H%M%S")
    directory.mkdir(parents=True, exist_ok=False)
    yf.set_tz_cache_location(str(config.DATA_DIR / "history_refresh" / "yfinance_cache"))
    report: dict = {"started_at": now.isoformat(), "directory": str(directory), "cost_eur": 0,
                    "membership_verified_through": today, "latest_completed_session": last_completed_session(now)}

    def save():
        (directory / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # A SQLite backup includes committed WAL pages, unlike a plain file copy.
    with storage.get_connection() as conn, sqlite3.connect(directory / "gabi_before.db") as backup:
        conn.backup(backup)
    for path in [universe.HISTORICAL_MEMBERSHIP_CACHE, config.SP500_CACHE, edgar.CIK_CACHE]:
        if path.exists():
            shutil.copy2(path, directory / path.name)
    report["before"] = database_coverage()
    save()
    print(f"Backup saved: {directory}", flush=True)

    history = pd.read_csv(universe.HISTORICAL_MEMBERSHIP_CACHE, dtype=str)
    extended = extend_membership(history, ledger)
    current_response = requests.get(universe.WIKI_URL, headers={"User-Agent": config.SEC_USER_AGENT}, timeout=60)
    current_response.raise_for_status()
    (directory / "current.html").write_bytes(current_response.content)
    current = universe._normalize(pd.read_html(StringIO(current_response.text))[0])
    if set(current["symbol"]) != set(ledger["endpoint_symbols"]):
        raise ValueError("Current constituents differ from reviewed endpoint; review new changes first")
    temporary = universe.HISTORICAL_MEMBERSHIP_CACHE.with_suffix(".csv.tmp")
    extended.to_csv(temporary, index=False)
    temporary.replace(universe.HISTORICAL_MEMBERSHIP_CACHE)
    current.to_csv(config.SP500_CACHE, index=False)
    report["membership"] = {"original_rows": len(history), "rows": len(extended),
                            "events": len(ledger["events"]), "current_symbols": len(current),
                            "ledger_sha256": hashlib.sha256(LEDGER_PATH.read_bytes()).hexdigest()}
    targets = period_symbols(extended, "2025-01-01", today)
    report["target_symbols"] = targets
    live = edgar.get_cik_map(force_refresh=True)
    live_ciks = dict(zip(live["symbol"], live["cik"], strict=True))
    former_issuers = json.loads(LEDGER_PATH.with_name("former_issuers_2025_2026.json").read_text(encoding="utf-8"))
    with storage.get_connection() as conn:
        stored_ciks = dict(conn.execute("SELECT symbol,cik FROM edgar_metrics"))
    renamed = {e["removed"]: e for e in ledger["events"] if e["kind"] in {"ticker_change", "merger_rename"}}
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
    report["identity_unresolved"] = blocked
    report["successor_sources"] = list(renamed.values())
    end = (pd.Timestamp(report["latest_completed_session"]) + timedelta(days=1)).date().isoformat()
    coverage = storage.get_price_coverage(targets + [config.BENCHMARK_SYMBOL])
    report["prices"] = {"updated": {}, "failed": {}, "preserved_inactive": []}
    for i, symbol in enumerate(targets + [config.BENCHMARK_SYMBOL], 1):
        event = renamed.get(symbol)
        provider_symbol = event["added"] if event else symbol
        if symbol in blocked:
            report["prices"]["preserved_inactive"].append(symbol)
            continue
        latest = coverage.get(symbol, {}).get("latest_adjusted_date") or ""
        required = event["effective_date"] if event else report["latest_completed_session"]
        if not event and latest >= required:
            continue
        try:
            report["prices"]["updated"][symbol] = refresh_prices(
                symbol, provider_symbol, end, event["effective_date"] if event else None)
        except Exception as exc:
            report["prices"]["failed"][symbol] = data_fetch._classify_error(exc)[1]
        save()
        print(f"Prices {i}/{len(targets) + 1}: {symbol}", flush=True)
    report["share_class_spelling"] = restore_share_class_spelling(end)
    save()

    def progress(done, total, symbol):
        if done % 25 == 0 or done == total:
            print(f"SEC EDGAR {done}/{total}: {symbol}", flush=True)

    report["edgar"] = {"requested": len(ciks)}
    save()
    # One downloader limits traffic to SEC and avoids large concurrent responses.
    failures = edgar.fetch_edgar_batch(sorted(ciks), ciks, max_workers=1, progress_cb=progress)
    report["edgar"].update(refreshed=len(ciks) - len(failures), failed=failures)
    save()

    existing_fundamentals = storage.get_fundamentals_fetched_at(current["symbol"].tolist())
    missing_fundamentals = [s for s in current["symbol"] if s not in existing_fundamentals]
    report["yahoo_fundamentals"] = {
        "requested": missing_fundamentals,
        "failed": data_fetch.fetch_fundamentals_batch(missing_fundamentals, max_workers=2),
    }
    save()

    report["macro"] = {"updated": {}, "failed": {}}
    key = config.load_fred_key()
    for sid, settings in macro.SERIES.items():
        if not key:
            report["macro"]["failed"][sid] = "No free FRED API key configured"
            continue
        try:
            # The normal 260-observation refresh misses most of 2025 for daily series.
            observations = macro.fetch_series(sid, key, units=settings["units_param"], limit=10000)
            macro.upsert_series(sid, observations)
            report["macro"]["updated"][sid] = len(observations)
        except Exception:
            # A requests exception can contain the API key in its URL.
            report["macro"]["failed"][sid] = "FRED download failed; API key omitted from log"
        save()
    report["after"] = database_coverage()
    report["current_price_coverage"] = storage.get_price_coverage(current["symbol"].tolist())
    report["completed_at"] = datetime.now(UTC).isoformat()
    save()
    print(f"Report saved: {directory / 'report.json'}", flush=True)
    return report


if __name__ == "__main__":
    run()
