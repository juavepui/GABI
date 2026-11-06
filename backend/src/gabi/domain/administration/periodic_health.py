"""Whether the daily follow-up is running (#290): age of the last recorded live decision.

The scheduled maintenance records one live decision per run (Tuesday to Saturday, after the
New York close). A decision with status ERROR was recorded but did not work. When no working
decision exists, or the last one is more than ``MAX_BUSINESS_DAYS`` weekdays old, the follow-up
is not running: that evidence is lost and can never be filled in afterwards.

Weekdays, not exchange sessions: the notice asks for a check, it does not date a decision.
"""

from datetime import date, datetime

import numpy as np

MAX_BUSINESS_DAYS = 3


def _day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def assess(last: dict | None, last_working: dict | None, today: date,
           max_business_days: int = MAX_BUSINESS_DAYS) -> dict:
    """``last``/``last_working``: {"created_at", "status", "model_id"} of the newest decision and of the
    newest one whose status is not ERROR, or None.

    status: ``never`` (no working decision), ``late`` (older than the limit) or ``ok``."""
    working_day = _day((last_working or {}).get("created_at"))
    days = None if working_day is None else max(0, int(np.busday_count(working_day, today)))
    if working_day is None:
        status = "never"
    elif days is not None and days > max_business_days:
        status = "late"
    else:
        status = "ok"
    return {"status": status, "last_run_at": (last or {}).get("created_at"),
            "last_status": (last or {}).get("status"),
            "last_working_at": (last_working or {}).get("created_at"),
            "business_days": days, "max_business_days": max_business_days,
            "model_id": (last_working or {}).get("model_id")}
