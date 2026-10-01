"""Company research formulas and explicit downloads through the unchanged estimates/events_calendar."""

from datetime import date

import pandas as pd


class LegacyCompanyMath:
    @staticmethod
    def revision(history: pd.DataFrame, lookback_days: int, as_of: date) -> dict | None:
        from gabi import estimates

        return estimates.compute_revision(history, lookback_days, as_of=as_of)


def sync_company(symbol: str, dataset: str) -> dict:
    """Worker only: the per-company network syncs of the old Ficha buttons."""
    from gabi import estimates, events_calendar

    sync = events_calendar.sync_earnings_surprises if dataset == "surprises" else estimates.sync_estimates
    failed = sync([symbol])
    return {"kind": "company_sync", "symbol": symbol, "dataset": dataset, "synced": not failed,
            "reason": str(failed.get(symbol)) if failed else None}
