"""Explicit paired price/action refresh for holdings; all I/O and the clock are injected."""

from collections.abc import Callable
from datetime import datetime

import numpy as np
import pandas as pd

from gabi.domain.market.freshness import last_completed_session
from gabi.domain.market.price_sync import clean_prices


def refresh(symbols: list[str], *, source: Callable[[str], pd.DataFrame],
            save: Callable[[str, pd.DataFrame, str], None], now: Callable[[], datetime]) -> dict:
    failed = {}
    stamp = now()
    for symbol in symbols:
        try:
            raw = source(symbol)
            if 'Stock Splits' not in raw and not symbol.endswith('=X'):
                raise ValueError('La fuente no aportó el historial de desdoblamientos.')
            cleaned = clean_prices(raw, last_completed_session(stamp).isoformat())
            splits = raw.get('Stock Splits', pd.Series(0., index=raw.index)).copy()
            splits.index = pd.to_datetime(splits.index).tz_localize(None).normalize()
            if splits.index.has_duplicates or not np.isfinite(splits).all() or (splits < 0).any():
                raise ValueError('La fuente aportó desdoblamientos inválidos.')
            cleaned['Stock Splits'] = splits.reindex(cleaned.index)
            # An ex-date may already adjust all past prices before today's bar is complete.
            # Keep that event even though its unfinished price bar is not publishable.
            cleaned.attrs['splits'] = [(day.date().isoformat(), float(ratio)) for day, ratio in splits.items()
                                       if ratio and day.date() <= stamp.date()]
            save(symbol, cleaned, stamp.isoformat())
        except Exception as exc:
            failed[symbol] = f'No se pudo verificar precios y desdoblamientos: {exc}'
    return failed
