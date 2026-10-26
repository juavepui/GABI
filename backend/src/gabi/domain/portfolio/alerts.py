"""«Qué requiere tu atención» (#183): alerts from data already cached or computed, never recomputed per request.

Each rule receives what the home page already read and returns plain dicts: kind, severity, date,
symbols and the screen that resolves it. React writes the sentence.
"""

from datetime import date, datetime, timedelta

SEVERITY_ORDER = {"high": 0, "medium": 1, "info": 2}
WINDOW_DAYS = 7
FILING_DAYS = 14
TOP_N = 20
# A thesis is reviewed when its horizon ends; a long one, every year (the journal horizons).
REVIEW_MONTHS = {"Corto (<6 meses)": 6, "Medio (6-12 meses)": 12, "Largo (>12 meses)": 12}


def _alert(kind: str, severity: str, day: str | None, *, symbols: list[str] | None = None, link: str,
           **detail) -> dict:
    return {"kind": kind, "severity": severity, "date": day, "symbols": symbols or [], "link": link,
            "detail": detail}


def _day(value) -> date | None:
    if value is None or value != value:  # None or NaN
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def upcoming_earnings(earnings: dict[str, tuple[str, bool]], symbols: list[str], *, scope: str, today: date,
                      link: str) -> list[dict]:
    """One alert for the scope's companies that publish results within the window."""
    soon = sorted((when.isoformat(), symbol, estimate) for symbol in dict.fromkeys(symbols)
                  if symbol in earnings for day, estimate in [earnings[symbol]]
                  if (when := _day(day)) and 0 <= (when - today).days <= WINDOW_DAYS)
    if not soon:
        return []
    return [_alert("earnings", "medium", soon[0][0], symbols=[symbol for _, symbol, _ in soon], link=link,
                   scope=scope, dates={symbol: day for day, symbol, _ in soon},
                   estimated=[symbol for _, symbol, estimate in soon if estimate])]


def upcoming_dividends(events: list[dict], symbols: list[str], *, today: date) -> list[dict]:
    """Ex-dividend and payment dates within the window, one alert per date and type."""
    wanted = set(symbols)
    grouped: dict[tuple[str, str], list[str]] = {}
    for event in events:
        when = _day(event.get("event_date"))
        if event.get("symbol") in wanted and event.get("event_type") in ("ex_dividend", "dividend_payment") \
                and when and 0 <= (when - today).days <= WINDOW_DAYS:
            grouped.setdefault((when.isoformat(), event["event_type"]), []).append(event["symbol"])
    return [_alert(kind, "info", day, symbols=sorted(set(found)),
                   link="/empresas/" + sorted(found)[0], count=len(set(found)))
            for (day, kind), found in sorted(grouped.items())]


def top_changes(current: list[str], saved: list[str], saved_as_of: str, saved_name: str) -> list[dict]:
    """Entries and exits of today's Top-20 against the latest saved ranking."""
    entered = [symbol for symbol in current if symbol not in saved]
    exited = [symbol for symbol in saved if symbol not in current]
    if not entered and not exited:
        return []
    return [_alert("top_changes", "medium", saved_as_of, symbols=entered + exited, link="/cartera/seguimiento",
                   entered=entered, exited=exited, snapshot=saved_name)]


def filing_changes(events: list[dict], symbols: list[str], *, today: date) -> list[dict]:
    """Material filing changes recorded by «Comprobar filings» in the last two weeks."""
    since = today - timedelta(days=FILING_DAYS)
    found = sorted({event["symbol"] for event in events if str(event.get("event_type", "")).startswith("filing_")
                    and (when := _day(event.get("detected_at"))) and when >= since})
    if not found:
        return []
    latest = max(str(event["detected_at"])[:10] for event in events if event["symbol"] in found
                 and str(event.get("event_type", "")).startswith("filing_"))
    held = [symbol for symbol in found if symbol in set(symbols)]
    return [_alert("filings", "high", latest, symbols=found, link="/cartera/seguimiento", held=held)]


def failed_jobs(jobs: list[dict], *, today: date) -> list[dict]:
    """Recent failures not followed by a success of the same kind (newest first in `jobs`)."""
    since, solved, alerts = today - timedelta(days=WINDOW_DAYS), set(), []
    for job in jobs:
        if job["status"] == "succeeded":
            solved.add(job["kind"])
        elif job["status"] == "failed" and job["kind"] not in solved:
            when = _day(job.get("finished_at") or job.get("created_at"))
            if when and when >= since:
                solved.add(job["kind"])  # One alert per kind: the latest failure.
                alerts.append(_alert("job_failed", "high", when.isoformat(), link="/administracion",
                                     job_kind=job["kind"], error_code=job.get("error_code"),
                                     failures=job.get("failures_total") or 0))
    return alerts


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    for last in (31, 30, 29, 28):
        try:
            return date(year, month, min(day.day, last))
        except ValueError:
            continue
    raise ValueError("Fecha no válida.")


def overdue_theses(entries: list[dict], *, today: date) -> list[dict]:
    """Open theses whose horizon has ended (a long horizon is reviewed yearly), oldest first."""
    alerts = []
    for entry in entries:
        months = REVIEW_MONTHS.get(str(entry.get("horizon") or ""))
        created = _day(entry.get("created_at"))
        if entry.get("status") != "abierta" or months is None or created is None:
            continue
        due = _add_months(created, months)
        while months and str(entry.get("horizon")).startswith("Largo") and _add_months(due, 12) <= today:
            due = _add_months(due, 12)
        if due <= today:
            alerts.append(_alert("thesis_review", "medium", due.isoformat(), symbols=[entry["symbol"]],
                                 link="/cartera/diario", entry_id=entry["id"]))
    return sorted(alerts, key=lambda alert: alert["date"])


def ordered(alerts: list[dict]) -> list[dict]:
    """Most severe first; within a severity, the nearest date first."""
    return sorted(alerts, key=lambda alert: (SEVERITY_ORDER[alert["severity"]], alert["date"] or "9999"))
