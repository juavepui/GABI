"""Explicit refresh and read-only cache access for monthly academic factors."""

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from gabi.domain.research.academic_factors import _parse_monthly_csv


class FactorCache(Protocol):
    def load(self) -> pd.DataFrame | None: ...
    def save(self, frame: pd.DataFrame) -> None: ...


class FactorSource(Protocol):
    def tables(self) -> tuple[str, str]: ...


@dataclass(frozen=True)
class FactorSnapshot:
    factors: pd.DataFrame
    source: dict


class FactorSnapshots(Protocol):
    def load_snapshot(self) -> FactorSnapshot | None: ...
    def save_snapshot(self, frame: pd.DataFrame) -> FactorSnapshot: ...


def read_cached_factors(cache: FactorCache) -> pd.DataFrame | None:
    """A query does not have a download or write port."""
    return cache.load()


def refresh_factors(cache: FactorCache, source: FactorSource, *, force_refresh: bool = False) -> pd.DataFrame:
    if not force_refresh:
        cached = cache.load()
        if cached is not None:
            return cached
    merged = new_factors(source)
    cache.save(merged)
    return merged


def new_factors(source: FactorSource) -> pd.DataFrame:
    five_csv, momentum_csv = source.tables()
    five = _parse_monthly_csv(five_csv, ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"])
    momentum = _parse_monthly_csv(momentum_csv, ["Mom"])
    return five.join(momentum, how="inner")


def prepare_factor_snapshot(cache: FactorSnapshots, source: FactorSource, *, force_refresh: bool = False) -> FactorSnapshot:
    """Explicit job action; cache data and its hash describe the same bytes."""
    if not force_refresh:
        snapshot = cache.load_snapshot()
        if snapshot is not None:
            return snapshot
    return cache.save_snapshot(new_factors(source))
