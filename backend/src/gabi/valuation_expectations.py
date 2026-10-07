"""Legacy compatibility; calculations live in ``gabi.domain.market.valuation_expectations``."""

import gabi.domain.market.valuation_expectations as _implementation

DEFAULT_DISCOUNT_RATE = _implementation.DEFAULT_DISCOUNT_RATE
DEFAULT_FORECAST_YEARS = _implementation.DEFAULT_FORECAST_YEARS
DEFAULT_TERMINAL_GROWTH = _implementation.DEFAULT_TERMINAL_GROWTH
_present_value = _implementation._present_value
expectations_metrics = _implementation.expectations_metrics
reverse_dcf_growth = _implementation.reverse_dcf_growth
