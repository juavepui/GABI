"""Incremental Yahoo prices, with overlap and explicit adjustment repair."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from . import identity, storage
from . import sync_state as sync
from .data_fetch import _classify_error, normalize_symbol, yf
from .history_refresh import last_completed_session

COLS = {"Open": "open", "High": "high", "Low": "low", "Close": "close",
        "Adj Close": "adj_close", "Volume": "volume"}


def run(symbols: list, *, force: bool = False, full_refresh: bool = False, now=None) -> dict:
    now = now or datetime.now(UTC)
    session = last_completed_session(now)
    events, failed = [], {}
    plans = []
    groups: dict[tuple, list] = {}
    downloads: dict[tuple, object] = {}
    for symbol in dict.fromkeys(symbols):
        owner = identity.resolve(symbol, now.date().isoformat())["entity_id"]
        entity = owner or f"ticker:{symbol}"
        attempt = sync.Attempt("yahoo", entity, f"prices:{symbol}")
        cp = sync.get(attempt.source, entity, attempt.dataset)
        with storage.get_connection() as conn:
            conn.executescript(storage.SCHEMA)
            storage._ensure_price_columns(conn)
            first, latest = conn.execute("SELECT MIN(date),MAX(date) FROM prices "
                                         "WHERE symbol=? AND adj_close>0", (symbol,)).fetchone()
        if (not force and not full_refresh and latest and (latest >= session or cp.get("checked_session") == session)
                and not sync.due(cp, 24, now)):
            events.append(attempt.finish("unchanged", reason="sesión ya consultada; revisión diaria no vencida", skipped=True))
            continue
        start = (pd.Timestamp(latest) - timedelta(days=14)).date().isoformat() if latest else None
        key = (None if full_refresh else start, full_refresh, "")
        groups.setdefault(key, []).append(symbol)
        plans.append((symbol, owner, entity, first, latest, start))

    for symbol, owner, entity, first, latest, start in plans:
        attempt = sync.Attempt("yahoo", entity, f"prices:{symbol}")
        end = (now.date() + timedelta(days=1)).isoformat()

        def download(from_date, full=False, *, repair=False):
            params = {"start": from_date, "end": end} if from_date else {"period": "max" if full else "2y"}
            key = (from_date, full, symbol if repair else "")
            if key not in downloads:
                members = groups.get(key, [symbol])
                try:
                    downloads[key] = sync.retry(lambda: yf.download([normalize_symbol(s) for s in members],
                                                                   interval="1d", group_by="ticker", threads=6,
                                                                   auto_adjust=False, progress=False, **params), attempt)
                except Exception as exc:
                    downloads[key] = exc
            cached = downloads[key]
            if isinstance(cached, Exception):
                raise cached
            data = cached
            if not isinstance(data, pd.DataFrame):
                raise ValueError("Yahoo no devolvió una tabla de precios.")
            if isinstance(data.columns, pd.MultiIndex):
                ticker = normalize_symbol(symbol)
                data = data[ticker] if ticker in data.columns.get_level_values(0) else data.xs(ticker, level=1, axis=1)
            attempt.payload_bytes += len(data.to_csv().encode())
            data = data.reindex(columns=list(COLS)).copy()
            data.index = pd.to_datetime(data.index).tz_localize(None).normalize()
            data = data.loc[data.index <= pd.Timestamp(session)]
            valid = np.isfinite(data).all(axis=1) & (data[["Open", "High", "Low", "Close", "Adj Close"]] > 0).all(axis=1)
            valid &= (data.Volume >= 0) & (data.High >= data[["Open", "Close", "Low"]].max(axis=1))
            valid &= data.Low <= data[["Open", "Close", "High"]].min(axis=1)
            if data.empty or not valid.all() or data.index.has_duplicates:
                raise ValueError("Respuesta de precios vacía, duplicada o con observaciones inválidas.")
            return data.sort_index()

        try:
            data = download(None if full_refresh else start, full_refresh)
            if full_refresh and first and data.index.min().date().isoformat() > first:
                raise ValueError("El full-refresh no cubre el inicio de la serie cacheada.")
            with storage.get_connection() as conn:
                old = pd.read_sql_query("SELECT date,open,high,low,close,adj_close,volume FROM prices "
                                        "WHERE symbol=? AND date>=? ORDER BY date", conn,
                                        params=(symbol, data.index.min().date().isoformat()))
            old["date"] = pd.to_datetime(old["date"])
            old = old.set_index("date")
            incoming = data.rename(columns=COLS)
            overlap = old.index.intersection(incoming.index)
            adjustment_changed = False
            if len(overlap) and not full_refresh:
                old_adjust = old.loc[overlap, "adj_close"] / old.loc[overlap, "close"]
                new_adjust = incoming.loc[overlap, "adj_close"] / incoming.loc[overlap, "close"]
                adjustment_changed = bool((~np.isclose(old_adjust, new_adjust, rtol=1e-6, atol=1e-8)).any())
                ratio = incoming.loc[overlap, "close"] / old.loc[overlap, "close"]
                adjustment_changed |= bool(len(ratio) >= 2 and not np.isclose(ratio.median(), 1, rtol=1e-5))
            reason = "full-refresh solicitado" if full_refresh else "solape de 14 días para correcciones"
            if adjustment_changed:
                data = download(first, repair=True)
                if first and data.index.min().date().isoformat() > first:
                    raise ValueError("La reparación de ajustes no cubre el inicio de la serie cacheada.")
                incoming = data.rename(columns=COLS)
                old = storage.get_prices(symbol).reindex(columns=list(COLS.values()))
                reason = "reparación histórica: cambió el ajuste por dividendos/splits"
            if (adjustment_changed or full_refresh) and not old.index.isin(incoming.index).all():
                raise ValueError("La revisión histórica omite sesiones ya cacheadas; se conserva la serie anterior.")
            changed, new, revised = sync.delta_rows(old, incoming)
            if not changed.empty:
                storage.upsert_prices(symbol, changed.rename(columns={v: k for k, v in COLS.items()}), entity_id=owner)
            watermark = max(latest or "", data.index.max().date().isoformat())
            events.append(attempt.finish(sync.change_status(new, revised), state={"watermark": watermark,
                                                                                 "checked_session": session,
                                                                                 "overlap_days": 14},
                                         new=new, revised=revised, unchanged=len(data) - new - revised, reason=reason))
        except Exception as exc:
            _, reason = _classify_error(exc)
            failed[symbol] = reason
            events.append(attempt.finish("failed", reason=reason))
    return {"failed": failed, "events": events, "metrics": sync.totals(events)}
