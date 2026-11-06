"""Declared versions of the operating model and the active one (ADR 0008).

The values are declared here instead of read from `config.py`, which stays as the
sealed snapshot of the studies. Changing the active model is a commit that changes
`ACTIVE_MODEL_ID`; a new version starts without evidence."""

from types import MappingProxyType

from gabi.domain.market import engine_fundamentals, input_checks, revenue_growth, sec_metrics_v2
from gabi.domain.market.model_policy import FROZEN_LABEL, FROZEN_MODEL_ID, FROZEN_WEIGHTS
from gabi.domain.market.model_version import ModelVersion
from gabi.domain.market.technicals import TechnicalParameters

GABI_MF_V1 = ModelVersion(FROZEN_MODEL_ID, FROZEN_LABEL, FROZEN_WEIGHTS,
                          TechnicalParameters(sma_short=50, sma_long=200, rsi_period=14,
                                              momentum_short_days=126, momentum_long_days=252),
                          benchmark_symbol="SPY", risk_free_rate=0.04, sealed_hypothesis=True)

# #245: the same weights, technical parameters, benchmark and risk-free rate, scored with the SEC metrics V2.1.
# Activated by the owner on 2026-11-02 after the comparison with real data; it starts without evidence and
# inherits none from GABI-MF-v1, which stays sealed for the running studies.
GABI_MF_V2 = ModelVersion("GABI-MF-v2", "GABI multifactor v2 · métricas SEC V2.1", FROZEN_WEIGHTS,
                          GABI_MF_V1.technical, benchmark_symbol="SPY", risk_free_rate=0.04,
                          metrics_version=sec_metrics_v2.VERSION)

# #295: GABI-MF-v2 with the plausibility policy input-checks-v1: an impossible Yahoo value or an
# unexplained price jump scores as missing. Activated by the owner on 2026-11-04; it starts without evidence
# and inherits none from GABI-MF-v2.
GABI_MF_V3 = ModelVersion("GABI-MF-v3", "GABI multifactor v3 · métricas SEC V2.1 y controles de entrada",
                          FROZEN_WEIGHTS, GABI_MF_V1.technical, benchmark_symbol="SPY", risk_free_rate=0.04,
                          metrics_version=sec_metrics_v2.VERSION, input_checks=input_checks.VERSION)

# #339: GABI-MF-v3 with the revenue growth of revenue-growth-v1 (SEC metrics V2.2): the series starts from the
# tag with the latest year and a series behind the latest annual report scores as missing. Activated by the
# owner on 2026-11-06 after its effect on the day's ranking (#339: same Top-20, 23 companies change that
# metric); it starts without evidence and inherits none from GABI-MF-v3, which stays declared.
GABI_MF_V4 = ModelVersion("GABI-MF-v4", "GABI multifactor v4 · métricas SEC V2.2 y controles de entrada",
                          FROZEN_WEIGHTS, GABI_MF_V1.technical, benchmark_symbol="SPY", risk_free_rate=0.04,
                          metrics_version=revenue_growth.METRICS_VERSION, input_checks=input_checks.VERSION)

# #347: the model as it was tested on past data. The eight company metrics of the Composite come from the
# historical engine (screener_asof, operational mode of #237, fiscal alignment of #38), stored daily as
# engine-fundamentals-v1; prices, momentum and risk were already the same. Same weights, technical parameters,
# benchmark and risk-free rate; no input checks (the tested engine had none; their report stays as a warning).
# On 2026-11-06 its Top-20 equals the engine's (20/20; v4 shared 8). Decided on 2026-11-06 by Claude, to whom the
# owner delegated the decision; it starts without evidence of its own and inherits none from GABI-MF-v4. The
# evidence it reproduces is #35 (operativo-38: 20.1 % a year against 15.0 % for SPY, 2016-2025, t = 1.98).
GABI_MF_V5 = ModelVersion("GABI-MF-v5", "GABI multifactor v5 · el modelo probado (métricas SEC del motor histórico)",
                          FROZEN_WEIGHTS, GABI_MF_V1.technical, benchmark_symbol="SPY", risk_free_rate=0.04,
                          metrics_version=engine_fundamentals.METRICS_VERSION)

VERSIONS = MappingProxyType({version.model_id: version
                             for version in (GABI_MF_V1, GABI_MF_V2, GABI_MF_V3, GABI_MF_V4, GABI_MF_V5)})
ACTIVE_MODEL_ID = GABI_MF_V5.model_id


def active_model(model_id: str = ACTIVE_MODEL_ID) -> ModelVersion:
    try:
        return VERSIONS[model_id]
    except KeyError:
        raise ValueError(f"Unknown model version: {model_id}") from None
