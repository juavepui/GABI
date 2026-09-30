"""Public research catalog contracts; no operational holdout results."""

from typing import Any, Literal

from pydantic import BaseModel


class Diagnostic(BaseModel):
    family: str
    specification_ref: str | None = None
    result_ref: str | None = None
    classification: str


class ResearchOverview(BaseModel):
    as_of: str
    scope: str
    counts: dict[str, int]
    exhaustive_search_history: bool
    global_error_control_established: bool
    limitations: list[str]
    diagnostics: list[Diagnostic]
    unresolved_groups: list[Any]
    families: list[str]


class SearchTrial(BaseModel):
    id: str
    family: str
    configuration_sha256: str
    specification_ref: str
    result_ref: str | None
    observed_sample: dict[str, Any] | None
    planned_sample: dict[str, Any] | None
    state: str
    decision: str
    failures: list[str] | None
    demonstrated_superiority: bool


class SearchTrials(BaseModel):
    total: int
    offset: int
    items: list[SearchTrial]


class HistoricalRow(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    composite_score: float | None = None
    score_coverage: float | None = None
    confidence: float | None = None
    identity_status: str | None = None
    sector_is_approximate: bool | None = None
    price: float | None = None


class HistoricalPreview(BaseModel):
    job_id: str
    as_of: str
    status: str
    independent_advantage_demonstrated: bool
    universe_info: dict[str, Any]
    total: int
    shown: int
    rows: list[HistoricalRow]
    result_sha256: str


class BlindIntegrity(BaseModel):
    ok: bool
    broken_at: str | None
    n_periods: int


class BlindStatus(BaseModel):
    id: int
    name: str
    status: str
    unlock_date: str
    n_periods: int
    next_rebalance_due: str
    days_to_unlock: int
    integrity: BlindIntegrity
    revealed: bool


class BlindStatuses(BaseModel):
    items: list[BlindStatus]


class EstimateCaptureStatus(BaseModel):
    period: Literal["0q"]
    batches_total: int
    batches_eligible: int
    first_eligible: str | None
    last_eligible: str | None
    span_days: int
    batches_needed: int
    span_days_needed: int
    symbols_per_batch_needed: int
    history_threshold_met: bool
    evaluation_status: Literal["not_run"]
    independent_advantage_demonstrated: bool


class EstimateAnalysisRow(BaseModel):
    horizonte: int
    ic_mean: float | None
    ic_std: float | None
    icir: float | None
    pct_ic_positive: float | None
    n_periods: int


class EstimateAnalysisPreview(BaseModel):
    job_id: str
    status: Literal["insufficient_data", "ok"]
    observed_cutoff: str
    period: Literal["0q"]
    horizons_months: list[int]
    batches_available: int
    batches_needed: int
    span_days: int
    span_days_needed: int
    reason: str | None
    summary: list[EstimateAnalysisRow]
    independent_advantage_demonstrated: bool
    result_sha256: str


class TailLevel(BaseModel):
    confidence: float
    n_obs: int
    tail_mass: float
    tail_observations: int
    var: float | None
    expected_shortfall: float | None
    status: Literal["empty", "below_resolution", "sparse", "descriptive"]


class TailSummary(BaseModel):
    n_obs: int
    skewness: float | None
    excess_kurtosis: float | None
    kurtosis_convention: str
    horizon: str
    method: str
    annualized: bool
    level_95: TailLevel
    level_99: TailLevel


class TailSeries(BaseModel):
    name: str
    summary: TailSummary | None
    error: str | None


class BacktestTail(BaseModel):
    horizon: str | None
    message: str | None
    series: list[TailSeries]


class TaxYear(BaseModel):
    year: int
    realized_net: float
    taxable: float
    tax: float


class TaxDrag(BaseModel):
    initial_capital: float
    final_value_pretax: float
    final_value_aftertax: float
    pretax_return: float
    aftertax_return: float
    tax_drag_pct_points: float
    total_tax_paid: float
    unrealized_gain_remaining: float
    n_periods: int
    n_years: int
    tax_by_year: list[TaxYear]


class BacktestTax(BaseModel):
    capital: float
    strategy: TaxDrag | None
    spy_buy_and_hold: TaxDrag | None
    limitations: list[str]
    error: str | None


class BacktestDiagnosticsResponse(BaseModel):
    job_id: str
    kind: Literal["backtest_v1", "backtest_v2"]
    tail: BacktestTail
    tax: BacktestTax | None
    result_sha256: str


class FactorRegression(BaseModel):
    n_obs: int
    dof: int
    r2: float | None
    coef: dict[str, float | None]
    se: dict[str, float | None]
    t_stat: dict[str, float | None]
    t_stat_ols: dict[str, float | None]
    hac_lags: int
    periods_per_year: float
    alpha_anualizado: float | None
    periodos_alineados: int
    periodos_totales: int


class StabilityFit(BaseModel):
    n_obs: int
    dof: int
    status: str
    window: int | None = None
    start: str | None = None
    end: str | None = None
    alpha_anualizado: float | None = None
    coef: dict[str, float | None] | None = None
    t_stat: dict[str, float | None] | None = None
    ci95_pointwise: dict[str, list[float | None]] | None = None


class StabilityAttribution(BaseModel):
    contribution_to_full_quarterly_alpha: float | None


class StabilityEvent(BaseModel):
    id: str
    label: str
    n_obs: int
    compounded_return: float | None
    attribution: StabilityAttribution
    local_regression: StabilityFit | dict[str, str]
    without_episode: StabilityFit | None


class StabilityYear(BaseModel):
    year_of_start: int
    n_obs: int
    compounded_return: float | None
    adjusted_sum: float | None
    contribution_to_full_quarterly_alpha: float | None


class FactorStability(BaseModel):
    n_obs: int
    full: StabilityFit
    halves: list[StabilityFit]
    rolling: list[StabilityFit]
    events: list[StabilityEvent]
    calendar_years: list[StabilityYear]
    limitations: list[str]


class BenchmarkMetrics(BaseModel):
    total_return: float | None
    cagr: float | None


class BenchmarkActive(BaseModel):
    mean_active_per_quarter: float | None
    cagr_difference: float | None
    relative_wealth_return: float | None


class BenchmarkPeriod(BaseModel):
    fecha: str
    hasta: str
    wealth: dict[str, float | None]


class BenchmarkComparison(BaseModel):
    status: str | None = None
    n_obs: int
    start: str | None = None
    end: str | None = None
    metrics: dict[str, BenchmarkMetrics] = {}
    active: dict[str, BenchmarkActive] = {}
    periods: list[BenchmarkPeriod] = []


class BenchmarkMethod(BaseModel):
    min_train: int
    embargo_quarters: int


class FactorBenchmark(BaseModel):
    method: BenchmarkMethod
    in_sample: BenchmarkComparison
    expanding: BenchmarkComparison
    limitations: list[str]


class FactorsSource(BaseModel):
    file: str
    sha256: str
    first_month: str
    last_month: str
    url: str


class BacktestFactorsPreview(BaseModel):
    job_id: str
    status: str
    independent_advantage_demonstrated: bool
    source_job_id: str
    source_result_sha256: str
    hac_lags_requested: int | None
    factors_source: FactorsSource
    regression: FactorRegression | None
    regression_error: str | None
    stability: FactorStability | None
    stability_error: str | None
    benchmark: FactorBenchmark | None
    benchmark_error: str | None
    result_sha256: str


class FactorSummaryRow(BaseModel):
    factor: str
    horizonte: int
    sector_neutral: bool
    ic_mean: float | None = None
    ic_std: float | None = None
    icir: float | None = None
    pct_ic_positive: float | None = None
    q_spread: float | None = None
    n_periods: int


class FactorTurnoverRow(BaseModel):
    factor: str
    quantil: int
    turnover: float | None = None


class FactorQuantileMean(BaseModel):
    factor: str
    horizonte: int
    quantil: int
    retorno_medio: float | None = None
    retorno_medio_neutral: float | None = None


class FactorSkippedPeriod(BaseModel):
    fecha: str
    motivo: str


class FactorPreview(BaseModel):
    job_id: str
    start: str
    end: str
    months: int
    mode: str
    max_symbols: int | None
    status: str
    independent_advantage_demonstrated: bool
    summary: list[FactorSummaryRow]
    turnover: list[FactorTurnoverRow]
    quantile_means: list[FactorQuantileMean]
    skipped: list[FactorSkippedPeriod]
    skipped_count: int
    result_sha256: str


class BacktestSeriesMetrics(BaseModel):
    name: Literal["estrategia", "universo_ew", "spy"]
    total_return: float | None
    anualizado: float | None
    vol_anualizada: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None


class BacktestPeriod(BaseModel):
    fecha: str
    hasta: str
    candidatas: str | None = None
    cobertura_universo: str | None = None
    retorno: float | None = None
    spy: float | None = None
    universo_ew: float | None = None
    held: str | None = None
    sold: str | None = None
    bought: str | None = None
    turnover_pct: float | None = None
    comision_pagada: float | None = None
    spread_pagado: float | None = None
    coste_total: float | None = None


class BacktestCurvePoint(BaseModel):
    fecha: str
    estrategia: float | None
    universo_ew: float | None = None
    spy: float | None


class BacktestExitEvent(BaseModel):
    symbol: str
    fecha: str
    estado: str
    estricto: bool


class BacktestPreview(BaseModel):
    job_id: str
    kind: Literal["backtest_v1", "backtest_v2"]
    status: str
    independent_advantage_demonstrated: bool
    start: str
    end: str
    months: int
    top_n: int
    rotation_hurdle_points: float
    cost_bps: float | None = None
    universe_size: int | None = None
    mode: Literal["validation", "fast_dev"] | None = None
    max_symbols: int | None = None
    initial_capital: float | None = None
    commission_usd: float | None = None
    spread_bps: float | None = None
    series: list[BacktestSeriesMetrics]
    turnover_medio: float | None
    capital_final: float | None = None
    comision_total: float | None = None
    spread_total: float | None = None
    coste_total: float | None = None
    calmar: float | None = None
    recovery_days: int | None = None
    beta: float | None = None
    information_ratio: float | None = None
    capture_upside: float | None = None
    capture_downside: float | None = None
    strict_result: bool | None = None
    exit_events: list[BacktestExitEvent]
    periods: list[BacktestPeriod]
    skipped: list[FactorSkippedPeriod]
    curve: list[BacktestCurvePoint]
    result_sha256: str


class PublishedSicWindow(BaseModel):
    period: str
    ic_mean: float | None
    n_periods: int


class PublishedSicDivision(BaseModel):
    division: str
    name: str
    ic_mean: float | None
    icir: float | None
    n_periods: int
    positive_fraction: float | None
    status: str
    windows: list[PublishedSicWindow]


class PublishedFactor(BaseModel):
    metric: str
    ic_mean: float | None
    icir: float | None
    p_holm: float | None
    classification: str
    n_periods: int
    q_spread: float | None
    sic_divisions: list[PublishedSicDivision]


class PublishedSicCoverage(BaseModel):
    date: str
    stratum: str
    n_eligible: int
    n_identity: int
    n_selected_filing: int
    n_classified: int
    classified_fraction: float | None


class PublishedFactors(BaseModel):
    status: Literal["RETROSPECTIVE_DESCRIPTIVE"]
    independent_advantage_demonstrated: bool
    holm_significant_count: int
    factor_zoo_sha256: str
    sic_sha256: str
    n_dates: int
    minimum_pairs: int
    minimum_summary_periods: int
    n_eligible: int
    n_classified: int
    classified_fraction: float | None
    factors: list[PublishedFactor]
    coverage: list[PublishedSicCoverage]
