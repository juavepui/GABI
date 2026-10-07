"""Legacy compatibility; calculations live in ``gabi.domain.market.fundamentals``."""

import gabi.domain.market.fundamentals as _implementation

_positive_or_none = _implementation._positive_or_none
_revenue_growth_from_quarterly = _implementation._revenue_growth_from_quarterly
compute_fundamental_metrics = _implementation.compute_fundamental_metrics
