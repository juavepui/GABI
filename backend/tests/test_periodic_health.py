"""Whether the daily follow-up runs (#290): weekdays since the newest working live decision."""

from datetime import date

from gabi.domain.administration.periodic_health import MAX_BUSINESS_DAYS, assess

WEDNESDAY = date(2026, 11, 4)


def decision(created_at: str, status: str = "SIGNAL", model_id: str = "GABI-MF-v2") -> dict:
    return {"created_at": created_at, "status": status, "model_id": model_id}


def test_without_any_working_decision_the_follow_up_never_ran():
    assert assess(None, None, WEDNESDAY)["status"] == "never"
    failed = assess(decision("2026-11-03T22:30:00+00:00", "ERROR"), None, WEDNESDAY)
    assert failed["status"] == "never" and failed["last_status"] == "ERROR" and failed["business_days"] is None


def test_zero_three_and_four_weekdays():
    assert MAX_BUSINESS_DAYS == 3
    same_day = assess(*[decision("2026-11-04T22:30:00+00:00")] * 2, WEDNESDAY)
    assert (same_day["status"], same_day["business_days"]) == ("ok", 0)
    # Friday 2026-10-30 → Wednesday: Friday, Monday and Tuesday.
    three = assess(*[decision("2026-10-30T22:30:00+00:00")] * 2, WEDNESDAY)
    assert (three["status"], three["business_days"]) == ("ok", 3)
    four = assess(*[decision("2026-10-29T22:30:00+00:00")] * 2, WEDNESDAY)
    assert (four["status"], four["business_days"]) == ("late", 4)


def test_a_weekend_without_runs_is_not_a_delay():
    monday = date(2026, 11, 2)
    result = assess(*[decision("2026-10-31T22:30:00+00:00")] * 2, monday)  # Saturday's run, Friday's session
    assert (result["status"], result["business_days"]) == ("ok", 0)


def test_a_recent_failure_after_an_old_working_run_is_late_and_says_why():
    result = assess(decision("2026-11-03T22:30:00+00:00", "ERROR"), decision("2026-10-26T22:30:00+00:00"),
                    WEDNESDAY)
    assert result["status"] == "late" and result["last_status"] == "ERROR"
    assert result["last_working_at"] == "2026-10-26T22:30:00+00:00" and result["business_days"] == 7
    assert result["model_id"] == "GABI-MF-v2"


def test_an_unreadable_date_counts_as_never():
    assert assess(None, decision("ayer"), WEDNESDAY)["status"] == "never"
