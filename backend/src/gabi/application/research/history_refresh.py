"""Refresh the local research data from free sources, with backup and coverage audit.

An explicit, long write: it requires the reviewed membership ledger verified through the run
date, backs up SQLite and the CSV caches first and records every download and failure.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd

from gabi.domain.research import history_refresh as rules
from gabi.domain.research import membership

MEMBERSHIP_START = "2025-01-01"


class RefreshFiles(Protocol):
    def start(self, stamp: str) -> str: ...  # creates the run folder (never reused); returns its path
    def save(self, report: dict) -> None: ...
    def backup(self) -> None: ...
    def membership(self) -> pd.DataFrame: ...
    def write_page(self, page: bytes) -> None: ...
    def publish_membership(self, extended: pd.DataFrame, current: pd.DataFrame) -> None: ...
    def report_path(self) -> str: ...


@dataclass(frozen=True)
class RefreshPorts:
    files: RefreshFiles
    now: Callable[[], datetime]
    today: Callable[[], date]
    session: Callable[[datetime], str]  # last completed market session
    ledger: Callable[[], dict]
    ledger_sha256: Callable[[], str]
    former_issuers: Callable[[], dict]
    page: Callable[[], bytes]
    constituents: Callable[[bytes], pd.DataFrame]
    coverage: Callable[[], dict]
    price_coverage: Callable[[list[str]], dict]
    live_ciks: Callable[[], dict]
    stored_ciks: Callable[[], dict]
    refresh_prices: Callable[[str, str, str, str | None], int]
    classify: Callable[[Exception], str]
    restore_share_classes: Callable[[str], dict]
    edgar_batch: Callable[[list[str], dict, Callable], dict]
    fundamentals_fetched_at: Callable[[list[str]], dict]
    fetch_fundamentals: Callable[[list[str]], dict]
    fred_key: Callable[[], str | None]
    fred_series: Mapping[str, Mapping[str, str]]
    fetch_fred: Callable[[str, str, str], list]
    store_fred: Callable[[str, list], None]
    benchmark: str
    log: Callable[[str], None]


def refresh(ports: RefreshPorts) -> dict:
    now = ports.now()
    ledger = ports.ledger()
    today = now.date().isoformat()
    if today != ledger["verified_through"]:
        raise ValueError("Review the membership ledger through today before running a new refresh")
    files = ports.files
    directory = files.start(now.strftime("%Y%m%dT%H%M%S"))
    report: dict = {"started_at": now.isoformat(), "directory": directory, "cost_eur": 0,
                    "membership_verified_through": today, "latest_completed_session": ports.session(now)}
    files.backup()
    report["before"] = ports.coverage()
    files.save(report)
    ports.log(f"Backup saved: {directory}")

    history = files.membership()
    extended = membership.extend_membership(history, ledger, today=ports.today())
    page = ports.page()
    files.write_page(page)
    current = ports.constituents(page)
    if set(current["symbol"]) != set(ledger["endpoint_symbols"]):
        raise ValueError("Current constituents differ from reviewed endpoint; review new changes first")
    files.publish_membership(extended, current)
    report["membership"] = {"original_rows": len(history), "rows": len(extended),
                            "events": len(ledger["events"]), "current_symbols": len(current),
                            "ledger_sha256": ports.ledger_sha256()}
    targets = rules.period_symbols(extended, MEMBERSHIP_START, today)
    report["target_symbols"] = targets
    live_ciks = ports.live_ciks()
    former_issuers = ports.former_issuers()
    stored_ciks = ports.stored_ciks()
    renamed = rules.renamed_events(ledger)
    ciks, blocked = rules.issuer_ciks(targets, renamed, live_ciks, stored_ciks, former_issuers)
    report["identity_unresolved"] = blocked
    report["successor_sources"] = list(renamed.values())
    end = rules.download_end(report["latest_completed_session"])
    coverage = ports.price_coverage(targets + [ports.benchmark])
    report["prices"] = {"updated": {}, "failed": {}, "preserved_inactive": []}
    for i, symbol in enumerate(targets + [ports.benchmark], 1):
        event = renamed.get(symbol)
        if symbol in blocked:
            report["prices"]["preserved_inactive"].append(symbol)
            continue
        latest = coverage.get(symbol, {}).get("latest_adjusted_date") or ""
        if not rules.needs_price_refresh(event, latest, report["latest_completed_session"]):
            continue
        try:
            report["prices"]["updated"][symbol] = ports.refresh_prices(
                symbol, event["added"] if event else symbol, end, event["effective_date"] if event else None)
        except Exception as exc:
            report["prices"]["failed"][symbol] = ports.classify(exc)
        files.save(report)
        ports.log(f"Prices {i}/{len(targets) + 1}: {symbol}")
    report["share_class_spelling"] = ports.restore_share_classes(end)
    files.save(report)

    def progress(done, total, symbol):
        if done % 25 == 0 or done == total:
            ports.log(f"SEC EDGAR {done}/{total}: {symbol}")

    report["edgar"] = {"requested": len(ciks)}
    files.save(report)
    # One downloader limits traffic to SEC and avoids large concurrent responses.
    failures = ports.edgar_batch(sorted(ciks), ciks, progress)
    report["edgar"].update(refreshed=len(ciks) - len(failures), failed=failures)
    files.save(report)

    existing = ports.fundamentals_fetched_at(current["symbol"].tolist())
    missing = [s for s in current["symbol"] if s not in existing]
    report["yahoo_fundamentals"] = {"requested": missing, "failed": ports.fetch_fundamentals(missing)}
    files.save(report)

    report["macro"] = {"updated": {}, "failed": {}}
    key = ports.fred_key()
    for sid, settings in ports.fred_series.items():
        if not key:
            report["macro"]["failed"][sid] = "No free FRED API key configured"
            continue
        try:
            # The normal 260-observation refresh misses most of 2025 for daily series.
            observations = ports.fetch_fred(sid, key, settings["units_param"])
            ports.store_fred(sid, observations)
            report["macro"]["updated"][sid] = len(observations)
        except Exception:
            # A requests exception can contain the API key in its URL.
            report["macro"]["failed"][sid] = "FRED download failed; API key omitted from log"
        files.save(report)
    report["after"] = ports.coverage()
    report["current_price_coverage"] = ports.price_coverage(current["symbol"].tolist())
    report["completed_at"] = ports.now().isoformat()
    files.save(report)
    ports.log(f"Report saved: {files.report_path()}")
    return report
