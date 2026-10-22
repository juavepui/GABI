"""Descriptive fundamental Checklist (#167): verdicts against explicit thresholds, never a score or a signal."""

from typing import Any, Literal

from pydantic import BaseModel

Verdict = Literal["pass", "fail", "missing", "not_applicable", "info"]
AlarmStatus = Literal["active", "clear", "missing", "not_applicable", "manual", "info"]
Unit = Literal["fraction", "ratio", "USD", "count"]


class ChecklistAlternative(BaseModel):
    """The same concept as shown elsewhere on the company page, with its own source and period (#169)."""
    metric: str
    value: float
    source: Literal["yahoo", "sec_10k", "prices"]
    period: Literal["ttm", "mrq", "snapshot", "5y_monthly", "fiscal_year", "cached_history"]
    difference: Literal["period", "formula", "share_count", "method"]
    explanation: str


class ChecklistCriterion(BaseModel):
    key: str
    block: str
    label: str
    formula: str
    unit: Unit
    comparison: str
    value: float | None
    threshold: float | None
    default_threshold: float | None
    edited: bool
    verdict: Verdict
    reason: str | None
    source: Literal["sec_10k", "price+sec", "yahoo", "price+yahoo", "prices"]
    period: Literal["fiscal_year", "snapshot", "cached_history"]
    alternative: ChecklistAlternative | None
    reference: str
    explanation: str
    caveat: Literal["share_classes"] | None
    detail: dict[str, Any]


class ChecklistAlarm(BaseModel):
    key: str
    label: str
    check: str
    explanation: str
    status: AlarmStatus
    reason: str | None
    caveat: Literal["share_classes"] | None
    detail: dict[str, Any]


class ChecklistDcf(BaseModel):
    dcf_discount_rate: float
    dcf_terminal_growth: float
    dcf_years: float
    dcf_max_implied_growth: float
    edited: list[str]
    fcf: float | None
    shares: float | None
    price: float | None
    implied_growth: float | None
    historical_cfo_cagr: float | None
    value_per_share_at_history: float | None
    verdict: Literal["reasonable", "demanding", "discard", "missing", "not_applicable"]
    reason: str | None


class ChecklistSummary(BaseModel):
    passed: int
    failed: int
    evaluated: int
    missing: int
    score: float | None
    alarms_active: int
    alarms_evaluated: int


class ChecklistSources(BaseModel):
    sec_last_filed: str | None
    price_date: str | None
    shares_date: str | None
    shares_source: Literal["sec_outstanding", "sec_diluted_average", "yahoo_market_cap",
                           "yahoo_no_sec_shares"] | None
    yahoo_fetched_at: str | None


class ChecklistQualitative(BaseModel):
    key: str
    label: str
    hint: str


class ChecklistMedian(BaseModel):
    median: float | None
    count: int
    reason: str | None


class ChecklistMultiplesYear(BaseModel):
    fiscal_year_end: str
    price: float | None
    shares_date: str | None
    market_cap: float | None
    pe: float | None
    ev_ebitda: float | None
    ev_ebit: float | None
    ev_fcf: float | None


class ChecklistMultiplesHistory(BaseModel):
    years: int
    by_year: list[ChecklistMultiplesYear]
    median: dict[str, ChecklistMedian]


class ChecklistSectorMultiples(BaseModel):
    symbol: str
    as_of: str
    sector: str | None
    peers: int
    reason: str | None
    cached: bool
    medians: dict[str, ChecklistMedian]


class CompanyChecklistResponse(BaseModel):
    symbol: str
    as_of: str
    sector: str | None
    fiscal_year_end: str | None
    financial_sector: bool
    thresholds_version: int
    thresholds_warning: str | None
    sources: ChecklistSources
    summary: ChecklistSummary
    criteria: list[ChecklistCriterion]
    alarms: list[ChecklistAlarm]
    dcf: ChecklistDcf
    qualitative: list[ChecklistQualitative]
    multiples_history: ChecklistMultiplesHistory


class ChecklistThreshold(BaseModel):
    key: str
    label: str
    block: str
    unit: Unit
    comparison: str
    default: float | None
    minimum: float
    maximum: float
    reference: str
    explanation: str


class ChecklistThresholds(BaseModel):
    version: int
    values: dict[str, float]
    edited: list[str]
    warning: str | None
    catalog: list[ChecklistThreshold]


class ChecklistThresholdsRequest(BaseModel):
    values: dict[str, float]
