"""Descriptive fundamental Checklist of one company (#167): read-only query plus explicit threshold commands."""

import threading
from collections import OrderedDict
from collections.abc import Callable
from datetime import date
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.market import cached_data
from gabi.application.market.company_research import normalize_symbol
from gabi.application.research.historical import _json_value
from gabi.domain.market import checklist
from gabi.domain.market.sec_reads import companyfacts


class FactsReader(Protocol):
    def facts(self, symbol: str, *, entity_id: str | None = None, tags: list[str] | None = None,
              as_of: str | None = None, unit: str | None = None) -> pd.DataFrame: ...
    def last_filed(self, symbols: list[str], as_of: str | None = None) -> dict[str, str]: ...


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


SECTOR_CACHE_ENTRIES = 16


class CompanyChecklist:
    def __init__(self, facts: FactsReader, cache: cached_data.CacheReader, insiders: InsiderReader, store: ThresholdStore,
                 today: Callable[[], date], universe: Callable[[], list[tuple[str, str]]] = list):
        self.facts, self.cache, self.insiders, self.store, self.today = facts, cache, insiders, store, today
        # (symbol, sector) of the current universe; sector peers come from it, as in the ranking.
        self.universe = universe
        # In-process memo of peer multiples, keyed by the peers' last filings and prices: a new
        # sync changes the key, so stale medians are never served. Nothing is written.
        self._sector_cache: OrderedDict[tuple, dict] = OrderedDict()
        self._sector_lock = threading.Lock()

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

    def _shares(self, symbol: str, facts: dict, price: float | None, info: dict,
                today: date) -> tuple[float | None, str | None, str | None, bool]:
        """Latest SEC shares in today's split basis, checked against Yahoo's market cap."""
        series, source = checklist.share_basis(facts)
        known = [day for day in series if day <= today.isoformat()]
        shares_date = max(known) if known else None
        shares = series[shares_date] * self._split_factor_after(symbol, shares_date) if shares_date else None
        shares, source, history_ok = checklist.verified_shares(shares, source, price, _finite(info.get("marketCap")))
        return shares, shares_date if source and source.startswith("sec_") else None, source, history_ok

    def _close_on(self, symbol: str, day: str) -> float | None:
        row = self.cache.last_price(symbol, day)
        return _finite(row[0]) if row else None

    def company(self, symbol: str) -> dict:
        symbol = normalize_symbol(symbol)
        today = self.today()
        frame = self.facts.facts(symbol, as_of=today.isoformat())
        facts = companyfacts(frame, today.isoformat())
        latest = self.cache.latest_adjusted([symbol]).get(symbol)
        record = cached_data.fundamentals(self.cache, [symbol]).get(symbol) or {}
        info = record.get("info") or {}
        price = _finite(latest[1]) if latest else None
        shares, shares_date, source, history_ok = self._shares(symbol, facts, price, info, today)
        market = checklist.MarketInputs(
            price=price, price_date=str(latest[0]) if latest else None, shares=shares, shares_date=shares_date,
            shares_source=source, share_history_ok=history_ok, forward_eps=_finite(info.get("forwardEps")),
            beta=_finite(info.get("beta")), insiders_pct=_finite(info.get("heldPercentInsiders")),
            yahoo_fetched_at=record.get("fetched_at"))
        insiders = self.insiders.insider_transactions(symbol)
        values, edited, warning = self._thresholds()
        result = checklist.evaluate(
            facts, market, sector=info.get("sector"), thresholds=values, edited=edited,
            insider_rows=insiders.to_dict("records"), today=today,
            split_factor_between=lambda start, end: (self._split_factor_after(symbol, start)
                                                     / self._split_factor_after(symbol, end)))
        history = checklist.multiples_history(
            facts, close_on=lambda day: self._close_on(symbol, day),
            split_factor_after=lambda day: self._split_factor_after(symbol, day),
            financial=result["financial_sector"], share_history_ok=history_ok)
        filed = frame["filed_date"].dropna() if not frame.empty else pd.Series(dtype=str)
        return _json({
            "symbol": symbol, "as_of": today.isoformat(), "sector": info.get("sector"),
            "thresholds_version": checklist.THRESHOLDS_VERSION, "thresholds_warning": warning,
            "sources": {"sec_last_filed": str(filed.max()) if len(filed) else None, "price_date": market.price_date,
                        "shares_date": shares_date, "shares_source": source,
                        "yahoo_fetched_at": market.yahoo_fetched_at},
            **result,
            "multiples_history": history,
        })

    def sector_multiples(self, symbol: str) -> dict:
        """Median PER and EV multiples of the company's sector peers in the current universe."""
        symbol = normalize_symbol(symbol)
        today = self.today()
        sectors = {peer: sector for peer, sector in self.universe() if isinstance(sector, str) and sector}
        sector = sectors.get(symbol)
        base = {"symbol": symbol, "as_of": today.isoformat(), "sector": sector}
        if not sector:
            return _json({**base, "peers": 0, "reason": "not_in_universe", "cached": False,
                          "medians": checklist.sector_medians({}, financial=False)})
        financial = sector in checklist.FINANCIAL_SECTORS
        # Every sector member is computed once and shared by all its companies; each excludes itself.
        members = sorted(peer for peer, peer_sector in sectors.items() if peer_sector == sector)
        prices = self.cache.latest_adjusted(members)
        filed = self.facts.last_filed(members, today.isoformat())
        # Yahoo's market cap checks each peer's shares, so its snapshot is part of the key too.
        yahoo = dict(self.cache.fundamentals_fetched_at(members))
        key = (sector, today.isoformat(), tuple((peer, filed.get(peer), tuple(prices.get(peer) or ()),
                                                 yahoo.get(peer)) for peer in members))
        with self._sector_lock:
            values = self._sector_cache.get(key)
            if values is not None:
                self._sector_cache.move_to_end(key)
        cached = values is not None
        if values is None:
            values = {}
            infos = cached_data.fundamentals_info(self.cache, members)
            for peer in members:
                frame = self.facts.facts(peer, tags=checklist.MULTIPLE_TAGS, as_of=today.isoformat())
                if not frame.empty:  # quarterly USD rows never reach annual multiples: skip rebuilding them
                    frame = frame[(frame["unit"] == "shares") | frame["form"].isin(checklist.ANNUAL_FORMS)]
                facts = companyfacts(frame, today.isoformat())
                latest = prices.get(peer)
                price = _finite(latest[1]) if latest else None
                shares = self._shares(peer, facts, price, infos.get(peer) or {}, today)[0]
                values[peer] = checklist.current_multiples(facts, price, shares)
            with self._sector_lock:
                self._sector_cache[key] = values
                while len(self._sector_cache) > SECTOR_CACHE_ENTRIES:
                    self._sector_cache.popitem(last=False)
        peers = {peer: row for peer, row in values.items() if peer != symbol}
        return _json({**base, "peers": len(peers), "reason": None, "cached": cached,
                      "medians": checklist.sector_medians(peers, financial=financial)})
