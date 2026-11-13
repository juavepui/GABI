"""Issuer identity and the existing SEC audit policy, with an explicit clock."""

from datetime import datetime, timedelta

KEYS = ["tag", "unit", "start_date", "end_date", "accn"]
FIELDS = ["val", "form", "fp", "fy", "filed_date"]


def normalize_cik(cik: str) -> str:
    value = str(cik).strip()
    if not value.isdigit() or len(value) > 10 or int(value) == 0:
        raise ValueError("CIK must contain 1-10 digits and be nonzero")
    return value.zfill(10)


def facts_due(checkpoint: dict, recent: dict, has_facts: bool, cached: dict | None,
              now: datetime, full_refresh: bool) -> bool:
    audited = checkpoint.get("facts_audited_at")
    audit_due = not audited or (now - datetime.fromisoformat(audited)).total_seconds() >= 7 * 86400
    dates = recent.get("filingDate", [])
    filing_recent = bool(dates and max(dates) >= (now - timedelta(days=2)).date().isoformat())
    return bool(full_refresh or not has_facts or not cached or audit_due or filing_recent
                or checkpoint.get("status") == "failed")
