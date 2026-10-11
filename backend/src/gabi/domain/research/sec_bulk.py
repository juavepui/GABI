"""Interpret rounded SEC SUB/NUM records without inventing exact contexts."""

import math
from datetime import datetime

import pandas as pd


def date8(value: str) -> str:
    return datetime.strptime(value, '%Y%m%d').date().isoformat()


def submissions(frame: pd.DataFrame, ciks: set[str], source_url: str) -> list[tuple]:
    frame = frame.copy()
    frame['cik'] = frame['cik'].str.zfill(10)
    selected = frame[frame.cik.isin(ciks) & frame.form.isin(['10-K', '10-Q', '10-K/A', '10-Q/A'])]
    return [(r.adsh, r.cik, r.name, r.sic, r.form, date8(r.filed), r.accepted,
             r.fy, r.fp, r.instance, source_url) for r in selected.itertuples(index=False)]


def facts(frame: pd.DataFrame, accessions: set[str], tracked: set[str], shares: set[str]) -> tuple[list[tuple], int, int]:
    selected = frame[frame.adsh.isin(accessions) & frame.tag.isin(tracked)
                     & frame.version.str.match(r'^(us-gaap|dei)/')]
    consolidated = (selected.coreg == '') & (selected.get('segments', '') == '')
    excluded = int((~consolidated).sum())
    records = []
    invalid = 0
    for r in selected[consolidated].itertuples(index=False):
        try:
            val, qtrs = float(r.value), int(r.qtrs)
            if not math.isfinite(val) or qtrs < 0 or r.uom != ('shares' if r.tag in shares else 'USD'):
                raise ValueError('invalid value or unit')
            records.append((r.adsh, r.tag, r.version, date8(r.ddate), qtrs, r.uom, val))
        except ValueError:
            invalid += 1
    return records, excluded, invalid


QUARTER_URL = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/{key}.zip"
INSTANCE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{instance}"


def quarter_keys(years) -> list[str]:
    return [f"{year}q{quarter}" for year in years for quarter in range(1, 5)]


def quarter_url(key: str) -> str:
    return QUARTER_URL.format(key=key)


def instance_url(cik: str, accn: str, instance: str) -> str:
    return INSTANCE_URL.format(cik=int(cik), folder=accn.replace("-", ""), instance=instance)


def instance_forms(*, quarterly: bool, unmatched: bool) -> list[str]:
    return ["10-Q", "10-Q/A", "10-K/A", "10-K"] if unmatched else ["10-Q", "10-Q/A", "10-K/A"] if quarterly else ["10-K"]


def missing_instances(submissions: pd.DataFrame, existing: set, unmatched: set | None = None) -> pd.DataFrame:
    """Filings lacking exact facts, or exactly the reviewed unmatched accessions."""
    if unmatched is not None:
        return submissions[submissions.accn.isin(unmatched)]
    return submissions[~submissions.accn.isin(existing)]


def instance_facts(contexts: list[tuple], units: list[tuple], nodes: list[tuple], *, cik: str, accn: str,
                   filed_date: str, form: str, fp: str, fy: str, tracked: set[str], shares: set[str]) -> list[dict]:
    """Consolidated standard facts only; exact XBRL context dates, never NUM dates.

    ``contexts``: (id, identifier, dimensional, has_period, instant, start, end);
    ``units``: (id, measures, divide); ``nodes``: (tag, namespace, contextRef, unitRef, text)
    in document order.
    """
    periods = {}
    for context_id, identifier, dimensional, has_period, instant, start, end in contexts:
        if identifier is None or (identifier or "").strip().zfill(10) != cik or dimensional or not has_period:
            continue
        instant, start, end = ((value.strip() if value else None) for value in (instant, start, end))
        end = instant or end
        if end:
            datetime.fromisoformat(end)
            if start:
                datetime.fromisoformat(start)
            periods[context_id] = (start or "", end)
    measures = {unit_id: (values[0] or "").strip().split(":")[-1]
                for unit_id, values, divide in units if len(values) == 1 and not divide}
    records: dict = {}
    conflicts = set()
    for tag, namespace, context_ref, unit_ref, text in nodes:
        if tag not in tracked or not any(f"/{part}/" in (namespace or "") for part in ["us-gaap", "dei"]):
            continue
        context = periods.get(context_ref)
        unit = measures.get(unit_ref)
        if not context or unit != ("shares" if tag in shares else "USD"):
            continue
        try:
            val = float(text or "")
        except ValueError:
            continue
        if not math.isfinite(val):
            continue
        key = (tag, unit, *context)
        if key in records and records[key]["val"] != val:
            conflicts.add(key)
        records[key] = dict(tag=tag, unit=unit, start_date=context[0], end_date=context[1], val=val,
                            form=form, fp=fp, fy=int(fy) if fy else None, filed_date=filed_date, accn=accn)
    return [row for key, row in records.items() if key not in conflicts]


COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def companyfacts_url(cik: str) -> str:
    return COMPANYFACTS_URL.format(cik=cik)
