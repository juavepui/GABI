"""Descriptive fundamental Checklist of one company (#167): read-only query plus explicit threshold commands."""

from collections.abc import Callable
from datetime import date
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.market import cached_data
from gabi.application.market.company_research import normalize_symbol
from gabi.application.research.historical import _json_value
from gabi.domain.market import checklist
from gabi.domain.market.sec_facts import SHARES_TAGS
from gabi.domain.market.sec_reads import companyfacts


class FactsReader(Protocol):
    def facts(self, symbol: str, *, entity_id: str | None = None, tags: list[str] | None = None,
              as_of: str | None = None, unit: str | None = None) -> pd.DataFrame: ...


class InsiderReader(Protocol):
    def insider_transactions(self, symbol: str) -> pd.DataFrame: ...


class ThresholdStore(Protocol):
    def load(self) -> tuple[dict, str | None]: ...
    def save(self, overrides: dict[str, float]) -> None: ...
    def reset(self) -> None: ...


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) and abs(number) != float("inf") else None


def _json(value):
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json(item) for item in value]
    return _json_value(value)


class CompanyChecklist:
    def __init__(self, facts: FactsReader, cache: cached_data.CacheReader, insiders: InsiderReader, store: ThresholdStore,
                 today: Callable[[], date]):
        self.facts, self.cache, self.insiders, self.store, self.today = facts, cache, insiders, store, today

    def _thresholds(self) -> tuple[dict[str, float], set[str], str | None]:
        overrides, warning = self.store.load()
        try:
            cleaned = checklist.validate_thresholds(overrides)
        except ValueError:
            cleaned, warning = {}, "invalid_saved_thresholds"
        return checklist.defaults() | cleaned, set(cleaned), warning

    def thresholds(self) -> dict:
        values, edited, warning = self._thresholds()
        return {"version": checklist.THRESHOLDS_VERSION, "values": values, "edited": sorted(edited),
                "warning": warning, "catalog": checklist.threshold_catalog()}

    def save_thresholds(self, overrides: dict) -> dict:
        try:
            cleaned = checklist.validate_thresholds(overrides)
        except ValueError as exc:
            raise QueryError("invalid_thresholds", str(exc), 422) from exc
        # Only values that differ from the Excel defaults are kept as edits.
        defaults = checklist.defaults()
        self.store.save({key: value for key, value in cleaned.items() if value != defaults[key]})
        return self.thresholds()

    def reset_thresholds(self) -> dict:
        self.store.reset()
        return self.thresholds()

    def _split_factor_after(self, symbol: str, day: str) -> float:
        factor = 1.0
        for ratio in self.cache.split_ratios_after(symbol, day):
            if ratio:
                factor *= float(ratio)
        return factor

    def company(self, symbol: str) -> dict:
        symbol = normalize_symbol(symbol)
        today = self.today()
        frame = self.facts.facts(symbol, as_of=today.isoformat())
        facts = companyfacts(frame, today.isoformat())
        shares, shares_date = None, None
        if not frame.empty:
            rows = frame[frame["tag"].isin(SHARES_TAGS) & (frame["unit"] == "shares") & (frame["val"] > 0)]
            if not rows.empty:
                last = rows.sort_values(["filed_date", "end_date"]).iloc[-1]
                shares_date = str(last["end_date"])
                shares = float(last["val"]) * self._split_factor_after(symbol, shares_date)
        latest = self.cache.latest_adjusted([symbol]).get(symbol)
        record = cached_data.fundamentals(self.cache, [symbol]).get(symbol) or {}
        info = record.get("info") or {}
        market = checklist.MarketInputs(
            price=_finite(latest[1]) if latest else None, price_date=str(latest[0]) if latest else None,
            shares=shares, shares_date=shares_date, forward_eps=_finite(info.get("forwardEps")),
            beta=_finite(info.get("beta")), insiders_pct=_finite(info.get("heldPercentInsiders")),
            yahoo_fetched_at=record.get("fetched_at"))
        insiders = self.insiders.insider_transactions(symbol)
        values, edited, warning = self._thresholds()
        result = checklist.evaluate(
            facts, market, sector=info.get("sector"), thresholds=values, edited=edited,
            insider_rows=insiders.to_dict("records"), today=today,
            split_factor_between=lambda start, end: (self._split_factor_after(symbol, start)
                                                     / self._split_factor_after(symbol, end)))
        filed = frame["filed_date"].dropna() if not frame.empty else pd.Series(dtype=str)
        return _json({
            "symbol": symbol, "as_of": today.isoformat(), "sector": info.get("sector"),
            "thresholds_version": checklist.THRESHOLDS_VERSION, "thresholds_warning": warning,
            "sources": {"sec_last_filed": str(filed.max()) if len(filed) else None, "price_date": market.price_date,
                        "shares_date": shares_date, "yahoo_fetched_at": market.yahoo_fetched_at},
            **result,
        })
