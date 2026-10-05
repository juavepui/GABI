"""Company research formulas and the explicit per-company downloads (estimates, surprises, insiders)."""

from datetime import date
from pathlib import Path

import pandas as pd

from gabi.domain.research import estimates


class LegacyCompanyMath:
    @staticmethod
    def revision(history: pd.DataFrame, lookback_days: int, as_of: date) -> dict | None:
        return estimates.compute_revision(history, lookback_days, as_of=as_of)

    @staticmethod
    def insiders(symbol: str, transactions: pd.DataFrame, months: int) -> dict:
        from gabi import insider

        return insider.summarize_insider_activity(symbol, months, transactions=transactions)

    @staticmethod
    def transaction_labels() -> dict[str, str]:
        from gabi import insider

        return dict(insider.TRANSACTION_CODES)


def sync_company(data_dir: Path, symbol: str, dataset: str) -> dict:
    """Worker only: the per-company network syncs of the old Ficha buttons."""
    from gabi import events_calendar, insider
    from gabi.infrastructure.legacy.estimates import sync_estimates

    if dataset == "insiders":  # «Actualizar insiders de esta empresa»: the latest Form 4, ignoring the 24 h cache.
        failed = insider.ensure_insider_data([symbol], max_age_hours=0)["failed"]
    elif dataset == "surprises":
        failed = events_calendar.sync_earnings_surprises([symbol])
    else:
        failed = sync_estimates(data_dir, [symbol])
    return {"kind": "company_sync", "symbol": symbol, "dataset": dataset, "synced": not failed,
            "reason": str(failed.get(symbol)) if failed else None}


def analysis_prompt(table: pd.DataFrame, symbol: str) -> str:
    """The prompt text over the ranking row and scoring.explain_row, as the old Ficha."""
    from gabi import scoring
    from gabi.application.market.prompt_text import build_analysis_prompt

    return build_analysis_prompt(table.loc[symbol], scoring.explain_row(table, symbol), symbol)
