"""Free 1996-2015 source archive and conservative additions to operational data.

Run with python -m gabi.historical_backfill. Inputs are pinned CSV/JSON, never
remote code or pickle. The existing post-2015 membership and audit stay intact.
"""
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from . import config, edgar, historical_archive, storage
from .history_refresh import database_coverage, last_completed_session, period_symbols

MANIFEST = Path(__file__).with_name("resources") / "historical_sources_1996_2015.json"


def download_pinned(item: dict, directory: Path) -> Path:
    path = directory / item["filename"]
    if path.exists():
        with path.open("rb") as existing:
            if hashlib.file_digest(existing, "sha256").hexdigest() == item["sha256"]:
                return path
    temporary = path.with_suffix(".part")
    with requests.get(item["url"], stream=True, timeout=(20, 90)) as response:
        response.raise_for_status()
        with temporary.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                output.write(chunk)
    with temporary.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != item["sha256"]:
            raise ValueError(f"Source hash mismatch: {item['filename']}")
    temporary.replace(path)
    return path


def overlaps_membership(prices: pd.DatetimeIndex, history: pd.DataFrame, symbol: str, end: str) -> bool:
    history = history[history["date"] < end].sort_values("date")
    dates = history["date"].tolist() + [end]
    present = [symbol in {s.replace(".", "-") for s in tickers.split(",")} for tickers in history["tickers"]]
    first = None
    for i, member in enumerate(present + [False]):
        if member and first is None:
            first = dates[i]
        if not member and first is not None:
            if ((prices >= pd.Timestamp(first)) & (prices < pd.Timestamp(dates[i]))).any():
                return True
            first = None
    return False


def fetch_missing_history(symbol: str, history: pd.DataFrame, end: str) -> int:
    frame = yf.Ticker(symbol).history(period="max", end=end, auto_adjust=False)
    if frame.empty or "Adj Close" not in frame:
        raise ValueError("No adjusted history")
    frame = frame.dropna(subset=["Close", "Adj Close"])
    market_dates = pd.to_datetime(frame.index.strftime("%Y-%m-%d"))
    frame = frame[market_dates < pd.Timestamp(end)]
    market_dates = pd.to_datetime(frame.index.strftime("%Y-%m-%d"))
    if not overlaps_membership(market_dates, history, symbol, "2016-01-01"):
        raise ValueError("Provider history does not overlap historical membership")
    storage.upsert_prices(symbol, frame)
    if "Stock Splits" in frame:
        storage.upsert_splits(symbol, {d.strftime("%Y-%m-%d"): float(v)
                                      for d, v in frame["Stock Splits"].items() if pd.notna(v) and v > 0})
    return len(frame)


def run() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    directory = config.DATA_DIR / "history_refresh" / "1996_2015"
    directory.mkdir(parents=True, exist_ok=True)
    files = {key: download_pinned(item, directory) for key, item in manifest["sources"].items()}
    now = datetime.now(UTC)
    run_dir = directory / now.strftime("%Y%m%dT%H%M%S")
    run_dir.mkdir()
    with storage.get_connection() as conn, sqlite3.connect(run_dir / "gabi_before.db") as backup:
        conn.backup(backup)
    start, end = manifest["start"], manifest["end_exclusive"]
    history = pd.read_csv(files["membership"], dtype=str)
    issuers = pd.read_csv(files["issuers"], dtype=str).fillna("")
    targets = set(period_symbols(history, start, "2015-12-31"))
    report: dict = {"started_at": now.isoformat(), "cost_eur": 0, "manifest": manifest,
                    "before": database_coverage(), "target_symbols": sorted(targets)}

    def save():
        (run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    save()
    print(f"Backup: {run_dir}", flush=True)
    for kind, source_id in [("membership", "membership_source_id"), ("issuers", "issuer_source_id"), ("prices", "price_source_id")]:
        historical_archive.register_source(manifest[source_id], {
            **manifest["sources"][kind], "start": start, "end_exclusive": end,
            "quality": "community_reference" if kind != "prices" else "research_archive_unverified_identity",
        })
    report["membership_snapshots"] = historical_archive.import_membership(manifest["membership_source_id"], history, start, end)
    report["issuer_candidates"] = historical_archive.import_issuer_candidates(manifest["issuer_source_id"], issuers)
    report["archived_prices"] = {"accepted": 0, "rejected": 0}
    for n, chunk in enumerate(pd.read_csv(files["prices"], chunksize=200000), 1):
        counts = historical_archive.import_price_chunk(manifest["price_source_id"], chunk, targets, start, end)
        for key, count in counts.items():
            report["archived_prices"][key] += count
        if n % 5 == 0:
            print(f"Price archive: {report['archived_prices']}", flush=True)
    save()

    live_frame = edgar.get_cik_map()
    live = dict(zip(live_frame["symbol"], live_frame["cik"], strict=True))
    with storage.get_connection() as conn:
        stored = dict(conn.execute("SELECT symbol,cik FROM edgar_metrics"))
        old_facts = {s for s, in conn.execute("SELECT DISTINCT symbol FROM edgar_facts WHERE filed_date<?", (end,))}
        old_prices = {s for s, in conn.execute("SELECT DISTINCT symbol FROM prices WHERE date<? AND adj_close IS NOT NULL", (end,))}
    safe, blocked = historical_archive.unique_historical_ciks(issuers, targets, live, stored)
    report["historical_cik_candidates"] = safe
    report["blocked_operational_imports"] = blocked
    report["before_old_coverage"] = {"symbols_with_prices": len(targets & old_prices), "symbols_with_facts": len(targets & old_facts)}
    report["yahoo"] = {"updated": {}, "failed": {}}
    yf.set_tz_cache_location(str(config.DATA_DIR / "history_refresh" / "yfinance_cache"))
    completed_end = (pd.Timestamp(last_completed_session(now)) + pd.Timedelta(days=1)).date().isoformat()
    for symbol in sorted(set(safe) & set(live) - old_prices):
        try:
            report["yahoo"]["updated"][symbol] = fetch_missing_history(symbol, history, completed_end)
        except Exception as exc:
            report["yahoo"]["failed"][symbol] = str(exc)[:150]
        print(f"Yahoo: {symbol}", flush=True)
        save()

    report["sec"] = {"updated": {}, "failed": {}, "no_pre2016_facts": []}
    needed = sorted(set(safe) - old_facts)
    raw_dir = directory / "companyfacts"
    raw_dir.mkdir(exist_ok=True)
    for n, symbol in enumerate(needed, 1):
        cik = safe[symbol]
        try:
            raw_path = raw_dir / f"CIK{cik}.json"
            if raw_path.exists():
                facts = json.loads(raw_path.read_text(encoding="utf-8"))
            else:
                facts = edgar.fetch_company_facts(cik)
                raw_path.write_text(json.dumps(facts), encoding="utf-8")
            if str(facts["cik"]).zfill(10) != cik:
                raise ValueError("SEC response CIK mismatch")
            rows = edgar._extract_raw_facts(facts, edgar.TRACKED_TAGS, unit="USD")
            rows += edgar._extract_raw_facts(facts, edgar.SHARES_TAGS, unit="shares")
            rows = [r for r in rows if r.get("filed_date") and start <= r["filed_date"] < end]
            if rows:
                historical_archive.import_sec_facts(manifest["issuer_source_id"], symbol, cik, rows)
                report["sec"]["updated"][symbol] = {"cik": cik, "name": facts.get("entityName"), "rows": len(rows)}
            else:
                report["sec"]["no_pre2016_facts"].append(symbol)
        except Exception as exc:
            report["sec"]["failed"][symbol] = type(exc).__name__
        if n % 20 == 0 or n == len(needed):
            print(f"SEC: {n}/{len(needed)}; imported {len(report['sec']['updated'])}", flush=True)
        save()
    report["after"] = database_coverage()
    with storage.get_connection() as conn:
        report["archive_coverage"] = dict(zip(["rows", "symbols", "first", "last"], conn.execute(
            "SELECT COUNT(*),COUNT(DISTINCT symbol),MIN(date),MAX(date) FROM historical_prices WHERE source_id=?",
            (manifest["price_source_id"],)).fetchone(), strict=True))
        old_facts = {s for s, in conn.execute("SELECT DISTINCT symbol FROM edgar_facts WHERE filed_date<?", (end,))}
        old_prices = {s for s, in conn.execute("SELECT DISTINCT symbol FROM prices WHERE date<? AND adj_close IS NOT NULL", (end,))}
        report["after_old_coverage"] = {"symbols_with_prices": len(targets & old_prices), "symbols_with_facts": len(targets & old_facts)}
        report["archived_sec_facts"] = dict(zip(["rows", "candidate_symbols", "issuers", "first_filed", "last_filed"],
            conn.execute("SELECT COUNT(*),COUNT(DISTINCT candidate_symbol),COUNT(DISTINCT cik),"
                         "MIN(filed_date),MAX(filed_date) FROM historical_facts WHERE source_id=?",
                         (manifest["issuer_source_id"],)).fetchone(), strict=True))
        report["sqlite_integrity"] = conn.execute("PRAGMA quick_check").fetchone()[0]
    report["completed_at"] = datetime.now(UTC).isoformat()
    save()
    print(f"Report: {run_dir / 'report.json'}", flush=True)
    return report


def import_price_archive(start: str, end: str) -> dict:
    """Import the pinned FINSABER file for ``[start, end)`` and every symbol (#34).

    #26 imported it only up to 2016 and for 2010-2015 members. The rows stay
    in the research archive (never the operational cache) and are attributed
    to an issuer only by the price audit. Reruns are idempotent.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    item = manifest["sources"]["prices"]
    path = config.DATA_DIR / "history_refresh" / "1996_2015" / item["filename"]
    with path.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != item["sha256"]:
            raise ValueError(f"Source hash mismatch: {item['filename']}")
    counts = {"accepted": 0, "rejected": 0}
    for chunk in pd.read_csv(path, chunksize=200000, dtype={"symbol": str, "date": str}):
        symbols = set(chunk["symbol"].dropna().str.replace(".", "-", regex=False))
        result = historical_archive.import_price_chunk(manifest["price_source_id"], chunk, symbols, start, end)
        for key, value in result.items():
            counts[key] += value
    return {"source_id": manifest["price_source_id"], "window": [start, end], **counts}


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["--import-prices"]:
        print(json.dumps(import_price_archive(sys.argv[2], sys.argv[3])))
    else:
        run()
