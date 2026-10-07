"""Legacy compatibility; calculations live in ``gabi.domain.portfolio.broker_costs``."""

import gabi.domain.portfolio.broker_costs as _implementation

CRYPTO_FEE_PCT = _implementation.CRYPTO_FEE_PCT
DEPOSIT_FX_PCT_BANK_TRANSFER = _implementation.DEPOSIT_FX_PCT_BANK_TRANSFER
DEPOSIT_FX_PCT_CARD = _implementation.DEPOSIT_FX_PCT_CARD
STOCK_FEE_USD = _implementation.STOCK_FEE_USD
STOCK_FEE_USD_HK = _implementation.STOCK_FEE_USD_HK
UK_STAMP_DUTY_PCT = _implementation.UK_STAMP_DUTY_PCT
effective_trade_cost_bps = _implementation.effective_trade_cost_bps
position_size_usd = _implementation.position_size_usd
