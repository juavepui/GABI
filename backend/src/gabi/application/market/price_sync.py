"""Incremental Yahoo price synchronization over explicit stores, checkpoints, retry and download."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

import pandas as pd

from gabi.domain.market import price_sync as rules
from gabi.domain.market.observations import change_status, delta_rows
from gabi.domain.market.sync_events import totals


class PriceStore(Protocol):
    def adjusted_span(self, symbol: str) -> tuple[str | None, str | None]: ...
    def prices_from(self, symbol: str, start: str) -> pd.DataFrame: ...
    def prices(self, symbol: str) -> pd.DataFrame: ...
    def write(self, symbol: str, frame: pd.DataFrame, entity_id: str | None) -> None: ...


class Attempt(Protocol):
    calls: int
    payload_bytes: int

    def finish(self, status: str, *, state: dict | None = None, new: int = 0, revised: int = 0,
               unchanged: int = 0, reason: str = "", skipped: bool = False) -> dict: ...


def run(symbols: list, *, store: PriceStore, owner: Callable[[str, str], str | None],
        attempt: Callable[[str, str, str], Attempt], checkpoint: Callable[[str, str, str], dict],
        due: Callable[[dict, float, datetime], bool], retry: Callable, download: Callable[..., object],
        classify: Callable[[Exception], str], payload_size: Callable[[pd.DataFrame], int], now: datetime,
        session: str, force: bool = False,
        full_refresh: bool = False) -> dict:
    events, failed = [], {}
    plans = []
    groups: dict[tuple, list] = {}
    downloads: dict[tuple, object] = {}
    for symbol in dict.fromkeys(symbols):
        entity_id = owner(symbol, now.date().isoformat())
        entity = entity_id or f"ticker:{symbol}"
        planned = attempt("yahoo", entity, f"prices:{symbol}")
        cp = checkpoint("yahoo", entity, f"prices:{symbol}")
        first, latest = store.adjusted_span(symbol)
        if rules.already_checked(latest, session, cp, force=force, full_refresh=full_refresh,
                                 due=due(cp, 24, now)):
            events.append(planned.finish("unchanged", reason="sesión ya consultada; revisión diaria no vencida",
                                         skipped=True))
            continue
        start = rules.overlap_start(latest)
        groups.setdefault((None if full_refresh else start, full_refresh, ""), []).append(symbol)
        plans.append((symbol, entity_id, entity, first, latest, start))

    end = rules.end_date(now)
    for symbol, entity_id, entity, first, latest, start in plans:
        current = attempt("yahoo", entity, f"prices:{symbol}")

        def fetch(from_date, full=False, *, repair=False, symbol=symbol, current=current):
            key = (from_date, full, symbol if repair else "")
            if key not in downloads:
                members = groups.get(key, [symbol])
                params = rules.download_params(from_date, full, end)
                try:
                    downloads[key] = retry(lambda: download([rules.yahoo_symbol(s) for s in members],
                                                            interval="1d", group_by="ticker", threads=6,
                                                            auto_adjust=False, progress=False, **params), current)
                except Exception as exc:
                    downloads[key] = exc
            cached = downloads[key]
            if isinstance(cached, Exception):
                raise cached
            data = rules.ticker_frame(cached, symbol)
            current.payload_bytes += payload_size(data)
            return rules.clean_prices(data, session)

        try:
            data = fetch(None if full_refresh else start, full_refresh)
            if full_refresh and rules.first_session_missing(data, first):
                raise ValueError("El full-refresh no cubre el inicio de la serie cacheada.")
            old = store.prices_from(symbol, data.index.min().date().isoformat())
            incoming = data.rename(columns=rules.COLS)
            changed_basis = not full_refresh and rules.adjustment_changed(old, incoming)
            reason = "full-refresh solicitado" if full_refresh else "solape de 14 días para correcciones"
            if changed_basis:
                data = fetch(first, repair=True)
                if rules.first_session_missing(data, first):
                    raise ValueError("La reparación de ajustes no cubre el inicio de la serie cacheada.")
                incoming = data.rename(columns=rules.COLS)
                old = store.prices(symbol).reindex(columns=list(rules.COLS.values()))
                reason = "reparación histórica: cambió el ajuste por dividendos/splits"
            if (changed_basis or full_refresh) and not old.index.isin(incoming.index).all():
                raise ValueError("La revisión histórica omite sesiones ya cacheadas; se conserva la serie anterior.")
            changed, new, revised = delta_rows(old, incoming)
            if not changed.empty:
                store.write(symbol, changed.rename(columns={v: k for k, v in rules.COLS.items()}), entity_id)
            watermark = max(latest or "", data.index.max().date().isoformat())
            events.append(current.finish(change_status(new, revised),
                                         state={"watermark": watermark, "checked_session": session,
                                                "overlap_days": rules.OVERLAP_DAYS},
                                         new=new, revised=revised, unchanged=len(data) - new - revised, reason=reason))
        except Exception as exc:
            reason = classify(exc)
            failed[symbol] = reason
            events.append(current.finish("failed", reason=reason))
    return {"failed": failed, "events": events, "metrics": totals(events)}
