"""Explicit temporary sources for ranking tracking and full-cache reader comparison."""
from datetime import date
from pathlib import Path

import pandas as pd

from gabi import storage
from gabi.application.market.snapshot_math import SnapshotCalculations
from gabi.application.market.snapshots import snapshot_name
from gabi.infrastructure.storage.signals import SqliteSignals
from gabi.infrastructure.storage.snapshot_prices import SqliteSnapshotPrices


class RankingFixture:
    def __init__(self, root: Path, today: date):
        self.repo = SqliteSignals(root)
        self.prices = SqliteSnapshotPrices(root, today)
        self.today = today

    def save_snapshot(self, table, as_of_date, top_n=10, name=None):
        return self.repo.save_snapshot(table, as_of_date, snapshot_name(name or f"Ranking {as_of_date}"), top_n)

    def list_snapshots(self):
        return pd.DataFrame(self.repo.snapshots())

    def snapshot_symbols(self, snapshot_id):
        return self.repo.snapshot(snapshot_id).index.tolist()

    def rename_snapshot(self, snapshot_id, name):
        return self.repo.rename(snapshot_id, snapshot_name(name))

    def _latest_cached_date(self, symbols):
        return self.prices.latest_date(symbols)

    @staticmethod
    def _adjusted_at(symbol, target, after=False):
        # Deliberately full-cache reference: bounded SQL is independently compared
        # with the former lookup's inclusive seven-day pandas slices.
        frame = storage.get_prices(symbol)
        if frame.empty or "adj_close" not in frame:
            return None
        values = frame["adj_close"].dropna()
        if after:
            values = values.loc[target:target + pd.Timedelta(days=7)]
            return float(values.iloc[0]) if not values.empty else None
        values = values.loc[target - pd.Timedelta(days=7):target]
        return float(values.iloc[-1]) if not values.empty else None

    def progress_for(self, symbols, as_of, *, data_as_of, today=None):
        return SnapshotCalculations.progress(symbols, as_of, data_as_of=data_as_of,
                                             price_at=self._adjusted_at, today=today or self.today)

    def evaluate(self, symbols, as_of, months=6, cost_bps=0, *, today=None):
        return SnapshotCalculations.evaluate(symbols, as_of, months, cost_bps=cost_bps,
                                             price_at=self._adjusted_at, today=today or self.today)

    def snapshot_progress(self, snapshot_id):
        row = self.repo.snapshot_meta(snapshot_id)
        symbols = self.snapshot_symbols(snapshot_id)
        return self.progress_for(symbols, row["as_of_date"],
                                 data_as_of=self.prices.latest_date([*symbols, "SPY"]))

    def snapshot_price_curve(self, snapshot_id):
        row = self.repo.snapshot_meta(snapshot_id)
        symbols = self.snapshot_symbols(snapshot_id)
        return SnapshotCalculations.curve(symbols, row["as_of_date"],
                                          storage.get_prices_multi([*symbols, "SPY"]))
