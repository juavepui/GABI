"""Read the depth of genuine point-in-time consensus captures."""

from datetime import datetime
from typing import Protocol

from gabi.application.errors import QueryError

MIN_BATCHES = 6
MIN_SPAN_DAYS = 60
MIN_SYMBOLS_PER_BATCH = 20


class EstimateCaptures(Protocol):
    def coverage(self, period: str, min_symbols: int) -> dict: ...


class EstimateQueries:
    def __init__(self, captures: EstimateCaptures):
        self.captures = captures

    def status(self) -> dict:
        coverage = self.captures.coverage("0q", MIN_SYMBOLS_PER_BATCH)
        first, last = coverage["first_eligible"], coverage["last_eligible"]
        try:
            span_days = (datetime.fromisoformat(last) - datetime.fromisoformat(first)).days \
                if first is not None and last is not None else 0
        except (TypeError, ValueError) as exc:
            raise QueryError("estimate_data_invalid", "Las fechas de captura no son válidas.", 503) from exc
        if span_days < 0:
            raise QueryError("estimate_data_invalid", "Las fechas de captura no son válidas.", 503)
        return {
            "period": "0q", "batches_total": coverage["batches_total"],
            "batches_eligible": coverage["batches_eligible"],
            "first_eligible": first, "last_eligible": last,
            "span_days": span_days, "batches_needed": MIN_BATCHES,
            "span_days_needed": MIN_SPAN_DAYS, "symbols_per_batch_needed": MIN_SYMBOLS_PER_BATCH,
            "history_threshold_met": coverage["batches_eligible"] >= MIN_BATCHES
            and span_days >= MIN_SPAN_DAYS,
            "evaluation_status": "not_run",
            "independent_advantage_demonstrated": False,
        }
