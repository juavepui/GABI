"""Company research formulas and explicit downloads through the unchanged estimates/events_calendar."""

from datetime import date

import pandas as pd


class LegacyCompanyMath:
    @staticmethod
    def revision(history: pd.DataFrame, lookback_days: int, as_of: date) -> dict | None:
        from gabi import estimates

        return estimates.compute_revision(history, lookback_days, as_of=as_of)

    @staticmethod
    def insiders(symbol: str, transactions: pd.DataFrame, months: int) -> dict:
        from gabi import insider

        return insider.summarize_insider_activity(symbol, months, transactions=transactions)

    @staticmethod
    def transaction_labels() -> dict[str, str]:
        from gabi import insider

        return dict(insider.TRANSACTION_CODES)


def sync_company(symbol: str, dataset: str) -> dict:
    """Worker only: the per-company network syncs of the old Ficha buttons."""
    from gabi import estimates, events_calendar, insider

    if dataset == "insiders":  # «Actualizar insiders de esta empresa»: the latest Form 4, ignoring the 24 h cache.
        failed = insider.ensure_insider_data([symbol], max_age_hours=0)["failed"]
    else:
        sync = events_calendar.sync_earnings_surprises if dataset == "surprises" else estimates.sync_estimates
        failed = sync([symbol])
    return {"kind": "company_sync", "symbol": symbol, "dataset": dataset, "synced": not failed,
            "reason": str(failed.get(symbol)) if failed else None}


def analysis_prompt(table: pd.DataFrame, symbol: str) -> str:
    """ai_prompt.build_analysis_prompt over the ranking row and scoring.explain_row, as the old Ficha."""
    from gabi import ai_prompt, scoring

    return ai_prompt.build_analysis_prompt(table.loc[symbol], scoring.explain_row(table, symbol), symbol)
