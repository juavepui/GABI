"""Consensus estimates: the revision signal over bounded readers and the explicit Yahoo capture."""

import concurrent.futures as cf
from datetime import UTC, date, datetime
from pathlib import Path

from gabi.domain.research import estimates
from gabi.infrastructure.storage.estimates import SqliteEstimateAnalysis, store_estimate_snapshot


def run_estimate_analysis(data_dir: Path, cutoff: date) -> dict:
    import exchange_calendars as xcals

    import gabi.domain.research.factors as factor_lab

    reader = SqliteEstimateAnalysis(data_dir, cutoff)

    def sessions(as_of, horizon: int):
        return factor_lab._entry_exit_sessions(xcals.get_calendar(factor_lab._CALENDAR), as_of, horizon)

    return estimates.evaluate_estimate_revision_signal(
        cutoff=cutoff, batch_loader=reader.batches, snapshot_loader=reader.rows,
        price_loader=reader.prices_for_sessions, sessions=sessions, forward_returns=factor_lab._forward_returns,
    )


def _fetch_estimate_snapshot_attempt(symbol: str) -> dict:
    import yfinance as yf

    from gabi.data_fetch import normalize_symbol

    t = yf.Ticker(normalize_symbol(symbol))
    return {
        "earnings_estimate": t.earnings_estimate, "revenue_estimate": t.revenue_estimate,
        "eps_revisions": t.eps_revisions,
    }


def sync_estimates(data_dir: Path, symbols: list, max_workers: int = 6) -> dict:
    """Descarga (red) earnings_estimate/revenue_estimate/eps_revisions por símbolo y los
    persiste con un ÚNICO `captured_at` compartido por toda la llamada -- así todas las
    filas forman un batch cross-seccional genuino (mismo instante de captura)."""
    from gabi.data_fetch import _classify_error

    failed: dict = {}
    if not symbols:
        return failed
    captured_at = datetime.now(UTC).isoformat()
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_estimate_snapshot_attempt, s): s for s in symbols}
        for fut in cf.as_completed(futures):
            sym = futures[fut]
            try:
                raw = fut.result()
                rows = estimates.parse_estimate_snapshot(
                    sym, raw["earnings_estimate"], raw["revenue_estimate"], raw["eps_revisions"], captured_at,
                )
                store_estimate_snapshot(data_dir, rows)
            except Exception as exc:
                _, reason = _classify_error(exc, service="Yahoo Finance")
                failed[sym] = reason
    return failed
