"""Explicit FRED refresh; queries never invoke this command."""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

import pandas as pd

from gabi.domain.market.fred import refresh_window
from gabi.domain.market.observations import change_status, delta_rows


class FredRepository(Protocol):
    def fetched_at(self, series_ids: Sequence[str]) -> dict: ...
    def failed(self, series_ids: Sequence[str]) -> set[str]: ...
    def history(self, series_id: str) -> pd.DataFrame: ...
    def upsert(self, series_id: str, observations: list) -> None: ...
    def record_errors(self, failed: dict) -> None: ...


class Attempt(Protocol):
    calls: int
    def payload(self, value) -> None: ...
    def finish(self, status: str, *, state: dict | None = None, new: int = 0, revised: int = 0,
               unchanged: int = 0, reason: str = "", skipped: bool = False) -> dict: ...


def synchronize(repository: FredRepository, series: Mapping[str, Mapping[str, str]],
                key: Callable[[], str | None], fetch: Callable[..., list],
                checkpoint: Callable[[str, str, str], dict],
                attempt_factory: Callable[[str, str, str], Attempt], retry: Callable,
                classify: Callable[[Exception], str], clock: Callable[[], datetime], *,
                force: bool = False, max_age_hours: int = 24, full_refresh: bool = False,
                progress_cb: Callable[[int, int, str], None] | None = None) -> dict:
    api_key = key()
    if not api_key:
        return {"ok": False, "reason": "no_api_key", "refreshed": 0, "failed": {}}
    ids = tuple(series)
    fetched_at = repository.fetched_at(ids)
    now = clock()
    failed_series = repository.failed(ids)
    stale = [sid for sid in ids
             if force or full_refresh or sid in failed_series or fetched_at.get(sid) is None
             or (now - fetched_at[sid]).total_seconds() > max_age_hours * 3600]
    failed = {}
    for i, sid in enumerate(stale):
        dataset = f"observations:{series[sid]['units_param']}"
        attempt = attempt_factory("fred", sid, dataset)
        cp = checkpoint("fred", sid, dataset)
        try:
            old = repository.history(sid)
            audit, start = refresh_window(old, cp, now, full_refresh)
            obs = retry(lambda: fetch(sid, api_key, units=series[sid]["units_param"],
                                     limit=100000, observation_start=start, include_missing=True), attempt)
            attempt.payload(obs)
            if not obs:
                raise ValueError("FRED devolvió una ventana vacía; checkpoint conservado.")
            incoming = pd.DataFrame(obs, columns=["date", "value"]).set_index("date")
            incoming.index = pd.to_datetime(incoming.index)
            changed, new, revised = delta_rows(old, incoming)
            repository.upsert(sid, [(d.date().isoformat(), None if pd.isna(v) else float(v))
                                    for d, v in changed.value.items()])
            state = {}
            valid_dates = incoming.loc[incoming.value.notna()].index
            if len(valid_dates):
                state["watermark"] = max(cp.get("watermark", ""), valid_dates.max().date().isoformat())
            if audit:
                state["full_audited_at"] = now.isoformat()
            attempt.finish(change_status(new, revised), state=state, new=new, revised=revised,
                           unchanged=len(incoming) - new - revised,
                           reason="auditoría mensual de revisiones antiguas" if audit
                           else "solape de 400 días para revisiones; incluye valores retirados")
        except Exception as exc:
            reason = classify(exc)
            failed[sid] = reason
            attempt.finish("failed", reason=reason)
        if progress_cb:
            progress_cb(i + 1, len(stale), sid)
    repository.record_errors(failed)
    return {"ok": True, "refreshed": len(stale) - len(failed), "failed": failed}
