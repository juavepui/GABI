"""Fixed-window Tiingo refresh and pinned imports with explicit checkpoints."""

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from gabi.domain.research.tiingo_prices import PACE_SECONDS, PriceWindow, new_observations, price_frame, source_metadata


@dataclass(frozen=True)
class PriceResponse:
    status: int = 0
    body: bytes = b""
    payload: object = None
    error_name: str | None = None


@dataclass(frozen=True)
class RawSnapshot:
    symbol: str
    body: bytes
    sha256: str


class TiingoSource(Protocol):
    def request(self, symbol: str, first: str, last: str) -> PriceResponse: ...


class TiingoCache(Protocol):
    def ensure_directory(self) -> None: ...
    def contains(self, symbol: str) -> bool: ...
    def save(self, symbol: str, body: bytes) -> None: ...
    def snapshots(self) -> Iterator[RawSnapshot]: ...


class Attempt(Protocol):
    calls: int
    payload_bytes: int
    def finish(self, status: str, *, state: dict | None = None, new: int = 0, revised: int = 0,
               unchanged: int = 0, reason: str = "", skipped: bool = False) -> dict: ...


class Checkpoints(Protocol):
    def get(self, source: str, entity: str, dataset: str) -> dict: ...


class TiingoArchive(Protocol):
    def pinned(self, source_id: str) -> dict: ...
    def register(self, source_id: str, metadata: dict) -> None: ...
    def dates(self, source_id: str, symbol: str, first: str, last: str) -> pd.DatetimeIndex: ...
    def import_prices(self, source_id: str, frame: pd.DataFrame, symbols: set[str], start: str, end: str) -> dict: ...


def fetch(symbols: list[str], spec: PriceWindow, cache: TiingoCache, source: TiingoSource, *,
          attempt_factory: Callable[[str, str], Attempt], wait: Callable[[float], None],
          progress: Callable[[str], None], pace: float = PACE_SECONDS, max_symbols: int = 1000,
          max_rows: int = 10_000) -> dict:
    if len(symbols) > max_symbols:
        raise ValueError("Tiingo symbol limit exceeded")
    cache.ensure_directory()
    fetched = cached = failed = 0
    for symbol in symbols:
        if cache.contains(symbol):
            cached += 1
            continue
        attempt_metrics = attempt_factory(symbol, f"download:{spec.name}")
        response = None
        for attempt in range(12):
            attempt_metrics.calls += 1
            candidate = source.request(symbol, spec.first, spec.last)
            if candidate.error_name:
                progress(f"Tiingo {symbol}: network error ({candidate.error_name}); retrying in 5 min")
                wait(300)
                continue
            # Preserve the last HTTP response even if later retries lose connectivity.
            response = candidate
            if response.status == 429 and attempt < 11:
                progress(f"Tiingo hourly allocation reached; waiting ({symbol})")
                wait(900)
                continue
            break
        if response is not None and response.status == 429:
            progress(f"Tiingo: cupo agotado en {symbol}; reanudar más adelante")
            attempt_metrics.finish("failed", reason="cupo Tiingo agotado; cola reanudable sin marcar el símbolo")
            return {"fetched": fetched, "cached": cached, "failed": failed, "stopped_at": symbol}
        payload = response.payload if response is not None and response.status == 200 else None
        if isinstance(payload, dict):
            progress(f"Tiingo: respuesta sin precios en {symbol} ({str(payload.get('detail'))[:80]}); detenido")
            attempt_metrics.finish("failed", reason="respuesta de cupo/error en vez de serie; no se guarda como dato")
            return {"fetched": fetched, "cached": cached, "failed": failed, "stopped_at": symbol}
        if response is None or response.status != 200:
            failed += 1
            code = response.status if response is not None else "no response"
            progress(f"Tiingo {symbol}: HTTP {code}")
            attempt_metrics.finish("failed", reason=f"HTTP {code}")
        else:
            if not isinstance(payload, list):
                attempt_metrics.finish("failed", reason="JSON sin lista de precios")
                failed += 1
                continue
            if len(payload) > max_rows:
                raise ValueError("Tiingo response row limit exceeded")
            cache.save(symbol, response.body)
            attempt_metrics.payload_bytes = len(response.body)
            attempt_metrics.finish("new", state={"fingerprint": hashlib.sha256(response.body).hexdigest(),
                                                 "watermark": max((r.get("date", "")[:10] for r in payload), default="")},
                                   new=len(payload), reason="snapshot de ventana histórica fija; escritura atómica")
            fetched += 1
            progress(f"Tiingo {symbol}: {len(payload)} rows")
        wait(pace)
    return {"fetched": fetched, "cached": cached, "failed": failed}


def import_cached(spec: PriceWindow, cache: TiingoCache, archive: TiingoArchive, checkpoints: Checkpoints, *,
                  attempt_factory: Callable[[str, str], Attempt], max_rows: int = 2_000_000,
                  max_rows_per_file: int = 10_000) -> dict:
    digests: dict[str, str] = {}
    frames = []
    pinned = archive.pinned(spec.source_id)
    count = 0
    for snapshot in cache.snapshots():
        symbol, digest = snapshot.symbol, snapshot.sha256
        digests[symbol] = digest
        if symbol in pinned and pinned[symbol] != digest:
            raise ValueError(f"Snapshot Tiingo archivado alterado: {symbol}; requiere una fuente con ID nuevo.")
        cp = checkpoints.get("tiingo", symbol, f"import:{spec.name}")
        if cp.get("fingerprint") == digest:
            del snapshot
            continue
        if cp.get("fingerprint"):
            raise ValueError(f"Snapshot Tiingo archivado alterado: {symbol}; requiere una fuente con ID nuevo.")
        rows = json.loads(snapshot.body.decode("utf8"))
        del snapshot
        if not rows:
            attempt_factory(symbol, f"import:{spec.name}").finish(
                "unchanged", state={"fingerprint": digest}, reason="snapshot válido sin observaciones")
            continue
        count += len(rows)
        if len(rows) > max_rows_per_file or count > max_rows:
            raise ValueError("Tiingo import row limit exceeded")
        frames.append(price_frame(symbol, rows))
    archive.register(spec.source_id, source_metadata(spec, digests))
    if not frames:
        return {"files": len(digests), "accepted": 0, "rejected": 0}
    accepted = rejected = 0
    for frame in frames:
        symbol = str(frame.symbol.iloc[0])
        attempt_metrics = attempt_factory(symbol, f"import:{spec.name}")
        try:
            before = archive.dates(spec.source_id, symbol, spec.first, spec.end_exclusive)
            result = archive.import_prices(spec.source_id, frame, {symbol}, spec.first, spec.end_exclusive)
            accepted += result["accepted"]
            rejected += result["rejected"]
            if result["rejected"]:
                attempt_metrics.finish("failed", reason=f"{result['rejected']} observaciones inválidas; revisión pendiente")
                continue
            new_count = new_observations(frame, before, spec)
            attempt_metrics.finish("new" if new_count else "unchanged",
                                   state={"fingerprint": digests[symbol], "watermark": str(frame.date.max())},
                                   new=new_count, unchanged=result["accepted"] - new_count,
                                   reason="sólo fichero no importado; fuente histórica fijada")
        except Exception as exc:
            attempt_metrics.finish("failed", reason=str(exc))
            raise
    return {"files": len(digests), "accepted": accepted, "rejected": rejected}
