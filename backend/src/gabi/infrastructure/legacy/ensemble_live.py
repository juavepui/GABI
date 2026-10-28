"""Live inputs of the prospective ENS record (#237) through the frozen and legacy engines.

Nothing is reimplemented: features come from ``screener_asof`` (the code behind the
retrospective rankings) in its opt-in operational mode, blocks from the frozen ``strategy_discovery.score_frame`` and the
dated SIC from the frozen ``factor_sector_stability.assign``. Only its filings source changes:
EDGAR submissions fetched when recording (decision D2), with the SIC current on that day.
The #38 fiscal alignment is enabled once at command start, never per request.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pandas as pd

from gabi.domain.research.ensemble_robustness import fingerprint
from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
from gabi.infrastructure.storage.sec_reads import SqliteSecReads

PERIODIC = {"10-K", "10-Q", "10-K/A", "10-Q/A"}
FILING_COLUMNS = ["accn", "cik", "sic", "form", "filed_date", "accepted", "source_url"]


def _eastern(accepted: str | None) -> str:
    """EDGAR acceptance times are UTC; SUB's, which the frozen rule compares, are naive Eastern."""
    if not accepted:
        return ""
    try:
        moment = pd.Timestamp(accepted)
    except ValueError:
        return ""  # the frozen rule treats an unknown acceptance date explicitly
    if moment.tzinfo is not None:
        moment = moment.tz_convert("America/New_York").tz_localize(None)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def filings_from_submissions(cik: str, payload: dict, pages: Callable[[str], dict], max_age_days: int,
                             signal: date) -> pd.DataFrame:
    """Every filing on the pages needed to reach a periodic report older than the signal, or the age limit.

    Issuers with thousands of 424B2 fill the 1,000 ``recent`` entries in weeks; older pages are
    read until a periodic filing before the signal is found or the pages are older than the limit."""
    sic = str(payload.get("sic") or "")
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    rows: list[dict] = []

    def add(block: dict, source: str) -> None:
        for accn, form, filed, accepted in zip(block.get("accessionNumber", []), block.get("form", []),
                                               block.get("filingDate", []), block.get("acceptanceDateTime", []),
                                               strict=True):
            rows.append({"accn": accn, "cik": cik, "sic": sic, "form": form, "filed_date": filed,
                         "accepted": _eastern(accepted), "source_url": source})

    def reached() -> bool:
        return any(row["form"] in PERIODIC and row["filed_date"] < signal.isoformat() for row in rows)

    add(payload.get("filings", {}).get("recent", {}), url)
    oldest = (pd.Timestamp(signal) - pd.Timedelta(days=max_age_days)).date().isoformat()
    for page in payload.get("filings", {}).get("files", []):
        if reached() or page.get("filingTo", "") < oldest:
            break
        add(pages(page["name"]), f"https://data.sec.gov/submissions/{page['name']}")
    return pd.DataFrame(rows, columns=FILING_COLUMNS)


@contextmanager
def fiscally_aligned() -> Iterator[None]:
    """#38 alignment for one command process, as the retrospective rankings ran; never per request."""
    from gabi import edgar

    with edgar.fiscal_alignment(True):
        yield


def check_engine_data(data_dir: Path) -> None:
    """The engines read the configured project database; it must be the command's."""
    from gabi import config

    if config.DATA_DIR.resolve() != data_dir.resolve():
        raise ValueError("El registro usa la base de GABI_DATA_DIR; configura el mismo directorio para el motor.")


def frozen_inputs() -> dict:
    from gabi import factor_sector_stability

    return {"fiscal_alignment": True, "sic_spec_sha256": factor_sector_stability.SPEC_SHA256,
            "scorer": "gabi.strategy_discovery.score_frame", "sic_rules": "gabi.factor_sector_stability.assign"}


class _Calls:
    source, calls = "sec", 0


class LegacyEnsembleSources:
    def __init__(self, data_dir: Path, *, submissions: Callable[[str], dict], pages: Callable[[str], dict],
                 retry: Callable, sessions: Callable[[date, date], list[date]]):
        self.db = data_dir / "gabi.db"
        self._submissions, self._pages, self._retry, self._sessions = submissions, pages, retry, sessions

    def sessions(self, start: date, end: date) -> list[date]:
        return self._sessions(start, end)

    def constituents(self) -> tuple[list[str], dict]:
        from gabi import universe

        frame = universe.get_sp500_constituents(force_refresh=True)
        symbols = sorted(dict.fromkeys(frame["symbol"].astype(str)))
        return symbols, {"source": "sp500_constituents", "cache_after_error": bool(frame.attrs.get("cache_after_error")),
                         "symbols_sha256": fingerprint(symbols)}

    def ranking(self, signal: date, symbols: list[str]) -> pd.DataFrame:
        from gabi import screener_asof

        # Decision D1: issuers by the CIK stored by the SEC sync (current map, reviewed successions
        # included) where no attributed alias resolves the signal; prices from the ticker cache.
        stored = SqliteSecReads(self.db).stored_ciks()
        current = {symbol: f"cik:{int(cik):010d}" for symbol, cik in stored.items()
                   if symbol in set(symbols) and str(cik).strip().isdigit()}
        return screener_asof.build_ranking_as_of(signal.isoformat(), symbols=symbols,
                                                 operational_entities=current)["table"]

    def divisions(self, frame: pd.DataFrame, signal: date) -> pd.DataFrame:
        from gabi import factor_sector_stability as sic

        spec = sic.specification()
        if frame.empty:  # the frozen rule cannot index an empty result
            return pd.DataFrame(columns=["entity_id", "division", "reason"]).rename_axis("symbol")
        probe = _Calls()
        filings = []
        for entity in sorted({str(value) for value in frame["entity_id"].dropna() if str(value).startswith("cik:")}):
            cik = entity[4:]
            payload = self._retry(lambda cik=cik: self._submissions(cik), probe)
            filings.append(filings_from_submissions(
                cik, payload, lambda name: self._retry(lambda: self._pages(name), probe), spec["max_age_days"], signal))
        table = pd.concat(filings, ignore_index=True) if filings else pd.DataFrame(columns=FILING_COLUMNS)
        return sic.assign(frame[["entity_id"]].astype({"entity_id": str}), signal.isoformat(), table, spec)

    def score(self, frame: pd.DataFrame) -> pd.DataFrame:
        from gabi import strategy_discovery

        return strategy_discovery.score_frame(frame)

    def entry_prices(self, symbols: list[str], signal: date) -> dict[str, dict]:
        found = SqliteCacheReads(self.db).latest_adjusted(symbols, signal.isoformat())
        return {symbol: {"date": str(day), "close": close, "adj_close": adjusted}
                for symbol, (day, close, adjusted) in found.items()}
