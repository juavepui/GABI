"""Legacy compatibility; calculations live in ``gabi.domain.portfolio.capital_allocation``."""

import gabi.domain.portfolio.capital_allocation as _implementation

ACQUISITION_TAGS = _implementation.ACQUISITION_TAGS
BUYBACK_TAGS = _implementation.BUYBACK_TAGS
CAPEX_TAGS = _implementation.CAPEX_TAGS
ISSUANCE_TAGS = _implementation.ISSUANCE_TAGS
OCF_TAGS = _implementation.OCF_TAGS
SHARES_TAGS = _implementation.SHARES_TAGS
_annual_series = _implementation._annual_series
_instant_series = _implementation._instant_series
metrics = _implementation.metrics
