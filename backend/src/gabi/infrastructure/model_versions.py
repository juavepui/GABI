"""Declared versions of the operating model and the active one (ADR 0008).

The values are declared here instead of read from `config.py`, which stays as the
sealed snapshot of the studies. Changing the active model is a commit that changes
`ACTIVE_MODEL_ID`; a new version starts without evidence."""

from types import MappingProxyType

from gabi.domain.market.model_policy import FROZEN_LABEL, FROZEN_MODEL_ID, FROZEN_WEIGHTS
from gabi.domain.market.model_version import ModelVersion
from gabi.domain.market.technicals import TechnicalParameters

GABI_MF_V1 = ModelVersion(FROZEN_MODEL_ID, FROZEN_LABEL, FROZEN_WEIGHTS,
                          TechnicalParameters(sma_short=50, sma_long=200, rsi_period=14,
                                              momentum_short_days=126, momentum_long_days=252),
                          benchmark_symbol="SPY", risk_free_rate=0.04, sealed_hypothesis=True)

VERSIONS = MappingProxyType({version.model_id: version for version in (GABI_MF_V1,)})
ACTIVE_MODEL_ID = GABI_MF_V1.model_id


def active_model(model_id: str = ACTIVE_MODEL_ID) -> ModelVersion:
    try:
        return VERSIONS[model_id]
    except KeyError:
        raise ValueError(f"Unknown model version: {model_id}") from None
