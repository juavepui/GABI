"""Align broker movements with cached prices without changing the saved originals (#305).

Broker quantities and unit prices are nominal on ``basis_date`` (movement date by
default). A broker export restated after a split must declare that date for BOTH
shares and price. Amounts, commissions and dividends never change on conversion.
The internal common base is the cached series' current split base, including later
splits when valuing an earlier date. Display quantities/prices are dated separately.
"""

import math
from datetime import date

import pandas as pd

from gabi.domain.portfolio.split_basis import split_factor


def prepare(lots: list[dict], histories: dict[str, pd.DataFrame], as_of: date
            ) -> tuple[list[dict], dict[str, pd.DataFrame], list[dict]]:
    converted, frames, warnings = [], {}, []
    factors = {}
    for symbol in dict.fromkeys(lot['symbol'] for lot in lots):
        frame = histories.get(symbol)
        frame = frame.copy() if frame is not None else pd.DataFrame()
        metadata = frame.attrs
        events = metadata.get('splits', [])
        try:
            pairs = [(pd.Timestamp(day), float(ratio)) for day, ratio in events]
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{symbol}: no se puede interpretar el historial de desdoblamientos.') from exc
        if any(pd.isna(day) or not math.isfinite(ratio) or ratio <= 0 for day, ratio in pairs):
            raise ValueError(f"{symbol}: hay un desdoblamiento inválido; actualiza los precios de mi cartera.")
        dates = [day for day, _ in pairs]
        if len(set(dates)) != len(dates):
            raise ValueError(f"{symbol}: hay desdoblamientos duplicados; actualiza los precios de mi cartera.")
        splits = pd.Series(dict(pairs), dtype=float)
        factors[symbol] = splits
        if metadata.get('basis') not in (None, 'today_splits'):
            raise ValueError(f"{symbol}: la base de precios es desconocida; actualiza los precios de mi cartera.")
        basis_dates = [str(lot.get('basis_date') or lot['purchase_date']) for lot in lots if lot['symbol'] == symbol]
        fetched = str(metadata.get('fetched_at') or '')[:10]
        if not metadata.get('actions_verified', False) or (fetched and max(basis_dates) > fetched):
            warnings.append({'symbol': symbol, 'reason': 'unverified_actions',
                             'message': f'{symbol}: no se han verificado los desdoblamientos de estos precios. '
                                        'Pulsa «Actualizar precios de mi cartera» antes de usar sus resultados.'})
        frames[symbol] = frame.loc[frame.index <= pd.Timestamp(as_of)].copy() if not frame.empty else frame
    for lot in lots:
        row = dict(lot)
        if row.get('kind', 'buy') != 'dividend':
            day = pd.Timestamp(row.get('basis_date') or row['purchase_date'])
            factor = float(split_factor(pd.DatetimeIndex([day]), factors[row['symbol']]).iloc[0])
            if not math.isfinite(factor) or factor <= 0:
                raise ValueError(f"{row['symbol']}: no se puede conciliar la base de acciones.")
            row['shares'] *= factor
            row['price'] /= factor
        converted.append(row)
    for symbol, frame in histories.items():
        if symbol not in frames:
            frames[symbol] = frame.loc[frame.index <= pd.Timestamp(as_of)].copy() if not frame.empty else frame
    return converted, frames, warnings


def display(valuation: dict, histories: dict[str, pd.DataFrame]) -> dict:
    """Shares and unit prices on their valuation date, preserving value, cost and all returns."""
    for row in valuation['positions']:
        if row['price_date'] is None:
            continue
        frame = histories.get(row['symbol'])
        events = [] if frame is None else frame.attrs.get('splits', [])
        splits = pd.Series({pd.Timestamp(day): ratio for day, ratio in events}, dtype=float)
        factor = float(split_factor(pd.DatetimeIndex([row['price_date']]), splits).iloc[0])
        row['shares'] /= factor
        for field in ('price', 'average_price'):
            if row[field] is not None:
                row[field] *= factor
    return valuation
