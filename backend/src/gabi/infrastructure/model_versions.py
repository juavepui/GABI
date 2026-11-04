"""Declared versions of the operating model and the active one (ADR 0008).

The values are declared here instead of read from `config.py`, which stays as the
sealed snapshot of the studies. Changing the active model is a commit that changes
`ACTIVE_MODEL_ID`; a new version starts without evidence."""

from types import MappingProxyType

from gabi.domain.market import input_checks, sec_metrics_v2
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

VERSIONS = MappingProxyType({version.model_id: version for version in (GABI_MF_V1, GABI_MF_V2, GABI_MF_V3)})
ACTIVE_MODEL_ID = GABI_MF_V3.model_id


def active_model(model_id: str = ACTIVE_MODEL_ID) -> ModelVersion:
    try:
        return VERSIONS[model_id]
    except KeyError:
        raise ValueError(f"Unknown model version: {model_id}") from None
