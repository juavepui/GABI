"""Descriptive fundamental Checklist (#167): verdicts against explicit thresholds, never a score or a signal."""

from typing import Any, Literal

from pydantic import BaseModel

Verdict = Literal["pass", "fail", "missing", "not_applicable", "info"]
AlarmStatus = Literal["active", "clear", "missing", "not_applicable", "manual", "info"]
Unit = Literal["fraction", "ratio", "USD", "count"]


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
    source: str
    reference: str
    detail: dict[str, Any]


class ChecklistAlarm(BaseModel):
    key: str
    label: str
    check: str
    status: AlarmStatus
    reason: str | None
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
    yahoo_fetched_at: str | None


class ChecklistQualitative(BaseModel):
    key: str
    label: str
    hint: str


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


class ChecklistThresholds(BaseModel):
    version: int
    values: dict[str, float]
    edited: list[str]
    warning: str | None
    catalog: list[ChecklistThreshold]


class ChecklistThresholdsRequest(BaseModel):
    values: dict[str, float]
