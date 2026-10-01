"""Progress of saved rankings with the unchanged evaluation formulas and injected bounded readers."""

from datetime import date

import pandas as pd


class LegacySnapshotMath:
    @staticmethod
    def progress(symbols: list[str], as_of_date: str, *, data_as_of, price_at, today: date) -> dict:
        from gabi import evaluation

        return evaluation.progress_for(symbols, as_of_date, data_as_of=data_as_of, price_at=price_at, today=today)

    @staticmethod
    def curve(symbols: list[str], as_of_date: str, histories: dict) -> pd.DataFrame:
        from gabi import evaluation

        return evaluation.price_curve_for(symbols, as_of_date, histories)

    @staticmethod
    def evaluate(symbols: list[str], as_of_date: str, months: int, *, price_at, today: date) -> dict:
        from gabi import evaluation

        return evaluation.evaluate(symbols, as_of_date, months, price_at=price_at, today=today)
