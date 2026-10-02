from datetime import date, datetime
from enum import StrEnum
from math import isfinite
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, HttpUrl

from gabi.application.administration.model import ModelState
from gabi.application.market.queries import DataState, RankingResult
from gabi.domain.market.units import BASE_METRICS, metric_unit


class WireModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")


class Unit(StrEnum):
    FRACTION = "fraction"
    PERCENT = "percent"
    POINTS = "points_0_100"
    USD = "USD"
    RATIO = "ratio"
    COUNT = "count"


class Metric(WireModel):
    value: float | None
    unit: Unit


class Identity(WireModel):
    status: Literal["resolved", "ambiguous", "unresolved"]
    entity_id: str | None
    cik: str | None
    candidates: list[str]
    source: str | None
    confidence: float | None
    as_of: date


class Provenance(WireModel):
    price_date: date | None = None
    fundamentals_fetched_at: datetime | None = None
    sec_fetched_at: datetime | None = None
    prices_source: Literal["local_cache_yahoo"] = "local_cache_yahoo"
    fundamentals_source: Literal["local_cache_yahoo"] = "local_cache_yahoo"
    sec_source: Literal["local_cache_sec"] = "local_cache_sec"
    metrics_history: Literal["full_cached_history"] = "full_cached_history"
    universe_source: Literal["local_sp500_cache"] = "local_sp500_cache"
    historical_point_in_time: Literal[False] = False


class Filing(WireModel):
    form: Literal["10-K", "10-Q"]
    filed_date: date | None
    url: HttpUrl | None


class Earnings(WireModel):
    event_date: date
    days_until: int
    is_estimate: bool | None
    source: Literal["Yahoo Finance (info)"] = "Yahoo Finance (info)"


class CompanyRow(WireModel):
    symbol: str
    name: str | None
    sector: str | None
    rank: int  # Position in full universe, before filters and pagination.
    metrics: dict[str, Metric]
    golden_cross_recent: bool | None
    identity: Identity
    provenance: Provenance
    filings: list[Filing]
    next_earnings: Earnings | None


class ModelResponse(WireModel):
    mode: Literal["INVESTOR", "RESEARCH"]
    model_id: str
    status: Literal["FROZEN", "EXPERIMENTAL", "LIVE_FORWARD"]
    weights: dict[str, float]
    weights_unit: Literal["fraction"] = "fraction"
    matches_frozen: bool
    live_forward_source: Literal["blind_validation", "research_lab"] | None
    blind_validation_id: int | None
    independent_advantage_demonstrated: Literal[False] = False
    evidence_note: str = "Congelar pesos o iniciar seguimiento no acredita una ventaja independiente sobre SPY."


class DataResponse(WireModel):
    status: Literal["ready", "empty", "stale"]
    universe_count: int
    prices_available: int
    fundamentals_available: int
    sec_available: int
    scored_count: int
    latest_price_date: date | None
    warnings: list[str]


class RankingResponse(WireModel):
    items: list[CompanyRow]
    total: int
    offset: int
    limit: int
    sectors: list[str]
    model: ModelResponse
    data: DataResponse
    generated_at: datetime
    universe_cached_at: datetime | None
    revision: str  # Ephemeral cache identity, NOT a published evidence hash.
    cache_hit: bool
    risk_free_rate: Metric


class PricePoint(WireModel):
    date: date
    close: float | None
    adj_close: float | None


class CompanyResponse(WireModel):
    company: CompanyRow
    model: ModelResponse
    data: DataResponse
    prices: list[PricePoint]
    price_unit: Literal["USD"] = "USD"
    generated_at: datetime
    revision: str


class ComparisonResponse(WireModel):
    items: list[CompanyRow]
    # metric -> symbol -> 1 best .. 0 worst among the compared companies; None when there is no winner.
    positions: dict[str, dict[str, float | None]]
    model: ModelResponse
    data: DataResponse
    generated_at: datetime
    revision: str


def finite(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return number if isfinite(number) else None


def text_or_none(value) -> str | None:
    return None if value is None or pd.isna(value) else str(value)


def model_response(model: ModelState) -> ModelResponse:
    return ModelResponse.model_validate(vars(model))


def data_response(data: DataState) -> DataResponse:
    return DataResponse.model_validate(vars(data))


def company_row(symbol: str, row: pd.Series, result: RankingResult) -> CompanyRow:
    non_metrics = {"name", "sector", "golden_cross_recent", "latest_10k_url", "latest_10k_date",
                   "latest_10q_url", "latest_10q_date", "next_earnings_date", "next_earnings_days",
                   "next_earnings_is_estimate"}
    keys = list(dict.fromkeys([str(key) for key in row.index if key not in non_metrics] + list(BASE_METRICS)))
    metrics = {key: Metric(value=finite(row.get(key)), unit=Unit(metric_unit(key))) for key in keys}
    sources = result.snapshot.table.attrs.get("sources", {}).get(symbol, {})
    provenance = Provenance.model_validate({key: sources.get(key) for key in
                                           ("price_date", "fundamentals_fetched_at", "sec_fetched_at")})
    filings = []
    for suffix, form in (("10k", "10-K"), ("10q", "10-Q")):
        raw_url = text_or_none(row.get(f"latest_{suffix}_url"))
        url = None
        if raw_url:
            try:
                candidate = HttpUrl(raw_url)
                if candidate.scheme == "https" and candidate.host in {"www.sec.gov", "sec.gov"}:
                    url = candidate
            except ValueError:
                pass
        filed_date = text_or_none(row.get(f"latest_{suffix}_date"))
        if filed_date or url:
            filings.append(Filing.model_validate({"form": form, "filed_date": filed_date, "url": url}))
    earnings_date = text_or_none(row.get("next_earnings_date"))
    estimated = row.get("next_earnings_is_estimate")
    earnings = Earnings.model_validate({"event_date": earnings_date, "days_until": int(row["next_earnings_days"]),
                                        "is_estimate": None if pd.isna(estimated) else bool(estimated)}) if earnings_date else None
    golden = row.get("golden_cross_recent")
    return CompanyRow(symbol=symbol, name=text_or_none(row.get("name")), sector=text_or_none(row.get("sector")),
                      rank=int(result.snapshot.table.index.get_loc(symbol)) + 1, metrics=metrics,
                      golden_cross_recent=None if pd.isna(golden) else bool(golden),
                      identity=Identity.model_validate(result.snapshot.identities[symbol]), provenance=provenance,
                      filings=filings, next_earnings=earnings)


def ranking_response(result: RankingResult) -> RankingResponse:
    sectors = sorted(str(value) for value in result.snapshot.table.get("sector", pd.Series(dtype=str)).dropna().unique())
    return RankingResponse(items=[company_row(str(symbol), row, result) for symbol, row in result.rows.iterrows()],
                           total=result.total, offset=result.offset, limit=result.limit, sectors=sectors,
                           model=model_response(result.model), data=data_response(result.data),
                           generated_at=result.snapshot.generated_at, universe_cached_at=result.snapshot.universe_cached_at,
                           revision=result.snapshot.revision, cache_hit=result.snapshot.cache_hit,
                           risk_free_rate=Metric(value=finite(result.snapshot.table.attrs.get("risk_free_rate")), unit=Unit.FRACTION))


class GlossaryMetric(BaseModel):
    key: str
    label: str
    help: str
    scored: bool


class GlossaryBlock(BaseModel):
    block: str
    label: str
    metrics: list[GlossaryMetric]


class GlossaryTerm(BaseModel):
    key: str
    term: str
    definition: str


class MetricGlossary(BaseModel):
    """Plain-language definitions served by the backend, the single source of metric meaning."""

    blocks: list[GlossaryBlock]
    terms: dict[str, str]
    glossary: list[GlossaryTerm]


class AnalysisPromptResponse(BaseModel):
    """Text to paste into an AI assistant; every number in it comes from GABI's deterministic code."""

    symbol: str
    revision: str
    prompt: str
