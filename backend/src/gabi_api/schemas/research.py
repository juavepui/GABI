"""Public research catalog contracts; no operational holdout results."""

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class HistoricalCoverageLayer(BaseModel):
    members: int
    identity_accredited: int
    accredited_prices: int
    scored: int
    excluded: dict[str, int]


class HistoricalIdentity(BaseModel):
    ambiguous: int
    unresolved: int


class HistoricalCoverage(BaseModel):
    threshold: float
    historical_coverage: HistoricalCoverageLayer | None
    identity: HistoricalIdentity | None
    with_fundamentals: int
    with_price: int
    sector_approximate: int
    no_sector: int
    warnings: list[str]


class HistoricalColumn(BaseModel):
    key: str
    label: str
    unit: Literal["text", "USD", "ratio", "fraction", "count", "points_0_100"]
    colored: bool


class HistoricalTableRow(BaseModel):
    symbol: str
    values: dict[str, float | str | None]
    colors: dict[str, float | None]


class HistoricalTable(BaseModel):
    job_id: str
    columns: list[HistoricalColumn]
    total: int
    offset: int
    rows: list[HistoricalTableRow]
    result_sha256: str


class OutcomeResult(BaseModel):
    months: int
    status: Literal["complete", "incomplete", "pending", "reserved"]
    end_date: str
    requested: int | None = None
    available: int | None = None
    portfolio_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    missing: list[str] = []


class BlockOutcome(BaseModel):
    block: str
    column: str
    symbols: list[str]
    outcome: OutcomeResult


class HistoricalOutcomes(BaseModel):
    job_id: str
    status: str
    independent_advantage_demonstrated: bool
    as_of: str
    source_job_id: str
    source_result_sha256: str
    top_n: int
    cost_bps: float
    observed_cutoff: str
    candidates: list[str]
    horizons: list[OutcomeResult]
    blocks: list[BlockOutcome]
    result_sha256: str


class HistoricalPreview(BaseModel):
    job_id: str
    as_of: str
    status: str
    independent_advantage_demonstrated: bool
    universe_info: dict[str, Any]
    total: int
    shown: int
    rows: list[HistoricalRow]
    coverage: HistoricalCoverage
    result_sha256: str


class BlindIntegrity(BaseModel):
    ok: bool
    broken_at: str | None
    n_periods: int


class BlindPlan(BaseModel):
    issue: int
    looks: list[str]
    sha256: str
    source: str


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
    revealed_through: str | None
    next_look: str | None
    rebalance_due: bool
    preregistered: BlindPlan | None


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


class PeriodQualityWarning(BaseModel):
    fecha: str
    messages: list[str]


class BacktestDiagnosticsResponse(BaseModel):
    job_id: str
    kind: Literal["backtest_v1", "backtest_v2"]
    tail: BacktestTail
    tax: BacktestTax | None
    quality_threshold: float
    quality_warnings: list[PeriodQualityWarning]
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


class PreparationFailure(BaseModel):
    symbol: str
    etapa: Literal["edgar", "precio"]
    motivo: str


class PreparationResult(BaseModel):
    job_id: str
    start: str
    end: str | None
    scope: Literal["date", "backtest"]
    symbols: int
    universe_note: str | None
    universe_is_exact: bool
    edgar_refreshed: int | None
    prices_deep_fetched: int | None
    prices_already_covered: int | None
    failed_symbols: int
    failures: list[PreparationFailure]
    failures_truncated: bool


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


class ExperimentStage(BaseModel):
    id: str
    emoji: str
    label: str
    help: str


class ExperimentSummary(BaseModel):
    id: int
    created_at: str
    model_id: str
    stage: str
    family: str | None
    n_positions: int | None
    rebalance: str | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None
    hypothesis_registered: bool
    git_commit: str | None
    notes: str | None
    periods_per_year: float | None
    has_returns: bool


class ExperimentList(BaseModel):
    total: int
    offset: int
    items: list[ExperimentSummary]
    families: list[str]
    stages: list[ExperimentStage]


class ExperimentDependency(BaseModel):
    package: str
    version: str


class ExperimentDetail(ExperimentSummary):
    data_cutoff: str | None
    universe: str | None
    factors: str | None
    weights: dict[str, Any] | None
    cost_model: str | None
    is_start: str | None
    is_end: str | None
    oos_start: str | None
    oos_end: str | None
    total_return: float | None
    annualized_return: float | None
    n_periods: int | None
    python_version: str | None
    env_fingerprint: str | None
    data_fingerprint: str | None
    backtest_job_id: str | None
    deps: list[ExperimentDependency]
    returns_count: int
    returns_first: str | None
    returns_last: str | None


class DeflatedSharpe(BaseModel):
    experiment_id: int
    model_id: str
    family: str | None
    sharpe: float
    n_obs: int
    periods_per_year: float
    skew: float
    kurtosis: float
    moments: Literal["returns", "normal_approximation"]
    psr: float
    dsr: float
    sr0_benchmark: float
    n_trials: int
    trial_ids: list[int]


class ExperimentTailRisk(BaseModel):
    experiment_id: int
    horizon: str
    message: str
    series: list[TailSeries]


class ExperimentProvenance(BaseModel):
    id: int
    model_id: str
    git_commit: str | None
    data_fingerprint: str | None
    stage: str
    family: str | None


class PboExperiment(ExperimentProvenance):
    label: str
    n_returns: int


class ExperimentPboPreview(BaseModel):
    job_id: str
    result_sha256: str
    status: str
    independent_advantage_demonstrated: bool
    experiments: list[PboExperiment]
    n_common_dates: int
    first_date: str | None
    last_date: str | None
    n_splits: int | None
    pbo: float | None
    n_combinations: int | None
    tied_splits: int | None
    tie_policy: str | None
    message: str | None


class BootstrapInterval(BaseModel):
    block_size: int
    series: str
    series_label: str
    metric: str
    metric_label: str
    observed: float | None
    valid_draws: int
    undefined_draws: int
    lower: float | None
    median: float | None
    upper: float | None
    bootstrap_mean: float | None


class BootstrapFraction(BaseModel):
    series: str
    condition: str
    fraction: float | None
    valid_draws: int
    undefined_draws: int


class BootstrapComparison(BaseModel):
    block_size: int
    series: str
    mean: float | None
    bootstrap_lower: float | None
    bootstrap_upper: float | None
    hac_lower: float | None
    hac_upper: float | None
    hac_lags: int
    zero_conclusion_differs: bool


class HistogramBin(BaseModel):
    start: float
    end: float
    fraction: float


class BootstrapHistogram(BaseModel):
    column: str
    label: str
    observed: float | None
    valid_draws: int
    lower: float | None
    upper: float | None
    bins: list[HistogramBin]


class BlockBootstrapView(BaseModel):
    primary_block: int
    n_obs: int
    periods_per_year: int
    n_boot: int
    ci: float
    start: str
    end: str
    has_series: bool
    tail_sparse: bool
    tail_mass: float
    limitations: list[str]
    intervals: list[BootstrapInterval]
    fractions: list[BootstrapFraction]
    comparisons: list[BootstrapComparison]
    histograms: list[BootstrapHistogram]


class BootstrapExperiments(BaseModel):
    strategy: ExperimentProvenance
    benchmark: ExperimentProvenance | None = None


class ExperimentBootstrapPreview(BaseModel):
    job_id: str
    result_sha256: str
    status: str
    independent_advantage_demonstrated: bool
    experiments: BootstrapExperiments
    message: str | None
    view: BlockBootstrapView | None


class ManualExperimentRequest(BaseModel):
    """The fields of the Streamlit manual form; 0 in a metric means "no value", as before."""

    model_config = {"extra": "forbid"}

    model_id: str = Field(max_length=80)
    n_positions: int = Field(ge=1, le=100)
    rebalance: Literal["Quarterly", "Semiannual", "Annual", "Monthly"]
    universe: str = Field(max_length=200)
    cost_model: str = Field(max_length=200)
    family: str = Field(default="", max_length=120)
    data_cutoff: str = Field(max_length=10)
    is_start: str = Field(max_length=10)
    is_end: str = Field(max_length=10)
    sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0
    n_periods: int = Field(ge=1, le=100_000)
    periods_per_year: float = Field(ge=1, le=366)
    stage: Literal["RESEARCH", "IN_SAMPLE", "OUT_OF_SAMPLE", "LIVE_FORWARD"]
    hypothesis_registered: bool
    data_fingerprint: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=4_000)


class DeletedExperiment(BaseModel):
    deleted: int


class SavedAuditsOverview(BaseModel):
    overfitting_audit: bool
    factor_benchmark: bool
    factor_stability: bool
    block_bootstrap: bool
    rank_stability: bool


class OverfittingTrial(BaseModel):
    trial_id: str
    role: str
    months: int
    cost_bps: float
    sharpe: float | None


class PboSensitivity(BaseModel):
    splits: int
    pbo: float


class ExcludedTrial(BaseModel):
    trial: str
    reason: str


class SavedOverfittingAudit(BaseModel):
    pbo: float
    dsr: float
    n_trials: int
    n_obs: int
    max_symbols: int
    trials: list[OverfittingTrial]
    pbo_sensitivity: list[PboSensitivity]
    excluded: list[ExcludedTrial]


class SavedBootstrapDataset(BaseModel):
    id: str
    label: str


class UnavailableBootstrapDataset(SavedBootstrapDataset):
    reason: str


class SavedBlockBootstrap(BaseModel):
    datasets: list[SavedBootstrapDataset]
    unavailable: list[UnavailableBootstrapDataset]
    selected: str
    view: BlockBootstrapView


class RankAggregate(BaseModel):
    metric: str
    mean: float | None
    min: float | None
    max: float | None


class RankCompany(BaseModel):
    symbol: str
    base_rank: float | None
    rank_min: float | None
    rank_max: float | None
    rank_std: float | None
    top10_inclusion: float | None
    top20_inclusion: float | None
    top30_inclusion: float | None
    diagnosis: str | None


class SavedRankStability(BaseModel):
    stability_score: float
    n_dates: int
    aggregate: list[RankAggregate]
    dates: list[str]
    selected: str
    companies: list[RankCompany]
    sectors_complete: bool
    limitations: list[str]


class LedgerIntegrity(BaseModel):
    ok: bool
    reason: str | None
    seq: int | None
    broken_at: int | None


class LedgerDecision(BaseModel):
    seq: int
    stage: str | None
    market_date: str | None
    status: str | None
    candidates: int
    git_commit: str | None
    model_version: str | None
    has_inputs: bool


class LiveLedgerOverview(BaseModel):
    integrity: LedgerIntegrity
    n_events: int
    events_by_kind: dict[str, int]
    decisions: list[LedgerDecision]
    live_versions: list[str]


class LedgerDecisionSummary(LedgerDecision):
    reason: str | None
    created_at: str | None
    top_n: list[str]
    data_fingerprint: str | None
    quality: dict[str, Any] | None


class LedgerReplay(BaseModel):
    fingerprint_matches: bool
    scores_match: bool
    ranking_matches: bool
    replayed_top_n: list[str]
    actual_top_n: list[str]


class LiveLedgerDecision(BaseModel):
    seq: int
    record_hash: str
    summary: LedgerDecisionSummary
    replay: LedgerReplay | None
    replay_error: str | None


class LiveInterval(BaseModel):
    seq: int
    record_hash: str
    status: str
    entry: str
    end: str
    end_basis: str
    requested: int
    missing: list[str]
    gross_return: float | None
    turnover_notional: float | None
    cost_fraction: float | None
    net_return: float | None
    nav: float | None


class LiveForwardReport(BaseModel):
    job_id: str
    result_sha256: str
    stage: str
    model_version: str | None
    available_versions: list[str]
    as_of: str
    generated_at: str
    intervals: list[LiveInterval]
    complete: bool
    cumulative_return: float | None
    benchmark_return: float | None
    policy: str
    limitations: list[str]
    outcome_data_fingerprint: str


class SaveEvaluationRequest(BaseModel):
    model_config = {"extra": "forbid"}

    job_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class SavedEvaluation(BaseModel):
    seq: int
    record_hash: str
    report_sha256: str


class BlindWeights(BaseModel):
    model_config = {"extra": "forbid"}

    value: float = Field(ge=0, le=100)
    quality: float = Field(ge=0, le=100)
    momentum: float = Field(ge=0, le=100)
    risk: float = Field(ge=0, le=100)


class BlindCreateRequest(BaseModel):
    """The Streamlit creation form; weights in percent."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=200)
    weights_pct: BlindWeights
    n_positions: int = Field(ge=1, le=50)
    rebalance_months: Literal[1, 3, 6, 12]
    start_date: str = Field(max_length=10)
    unlock_date: str = Field(max_length=10)


class BreakSealRequest(BaseModel):
    model_config = {"extra": "forbid"}

    reason: str = Field(min_length=1, max_length=2_000)


class BlindRebalanceResult(BaseModel):
    job_id: str
    validation_id: int
    recorded: bool
    reason: str | None = None
    rebalance_date: str | None = None
    n_positions: int | None = None
    record_hash: str | None = None


class BlindPeriod(BaseModel):
    rebalance_date: str
    retorno: float | None
    retorno_spy: float | None
    capital: float
    capital_spy: float


class BlindPerformance(BaseModel):
    job_id: str
    result_sha256: str
    validation_id: int
    revealed: bool
    revealed_through: str | None
    periods: list[BlindPeriod]
    cumulative: float | None
    cumulative_spy: float | None


class BlindExport(BaseModel):
    job_id: str
    validation_id: int
    revealed_through: str | None
    experiment_id: int
