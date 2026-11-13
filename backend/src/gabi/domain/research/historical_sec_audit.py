"""Offline 2010-2015 SEC concept coverage for historical index members.

Run ``python -m gabi_cli research historical-sec-audit``. This is a coverage
inventory, not a ranking or a substitute for a dated issuer/security identity check.
"""
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta

import pandas as pd

YEARS = range(2010, 2016)


def filing_status(filing_dates: list[str], as_of: str) -> tuple[bool, bool]:
    """Any prior filing and one in the last 460 days, without period-end lookahead."""
    index = bisect_right(filing_dates, as_of)
    if index == 0:
        return False, False
    fresh_since = (date.fromisoformat(as_of) - timedelta(days=460)).isoformat()
    return True, filing_dates[index - 1] >= fresh_since


def concept_dates(facts: Iterable[tuple], concept_tags: Mapping[str, Sequence[str]]) -> dict[tuple[str, str], list[str]]:
    """Filing dates per (CIK, concept) from exact (cik, tag, unit, filed) facts; shares need a share unit."""
    tag_concepts = defaultdict(list)
    for concept, tags in concept_tags.items():
        for tag in tags:
            tag_concepts[tag].append(concept)
    dates: dict[tuple[str, str], set[str]] = defaultdict(set)
    for cik, tag, unit, filed in facts:
        if not filed:
            continue
        for concept in tag_concepts.get(tag, []):
            if unit == ("shares" if concept == "shares" else "USD"):
                dates[(cik, concept)].add(filed)
    return {key: sorted(value) for key, value in dates.items()}


def member_rows(year: int, members: list[dict], dates: dict, concepts: Sequence[str]) -> list[dict]:
    day = f"{year}-12-31"
    rows = []
    for member in members:
        cik = member.get("cik") if member["identity_status"] == "resolved" else None
        row = {"year": year, "as_of": day, "symbol": member["symbol"], "cik": cik,
               "identity_tier": member.get("identity_tier"),
               "identity_status": member["identity_status"]}
        for concept in concepts:
            available, fresh = filing_status(dates.get((cik, concept), []), day) if cik else (False, False)
            row[concept] = available
            row[f"{concept}_fresh"] = fresh
        row["roic_inputs"] = all(row[key] for key in ("net_income", "equity", "long_term_debt"))
        row["fcf_inputs"] = row["operating_cash_flow"] and row["capex"]
        row["missing_concepts"] = ";".join(key for key in concepts if not row[key])
        rows.append(row)
    return rows


def summary(frame: pd.DataFrame, dates: dict, concepts: Sequence[str], counts: dict) -> dict:
    """``counts`` carries the database name and the bulk/exact/identity row counts, in published key order."""
    result = {**counts,
              "first_filed_by_concept": {concept: min((days[0] for (cik, item), days in dates.items()
                                                     if item == concept), default=None)
                                         for concept in concepts},
              "years": []}
    for year, group in frame.groupby("year"):
        accredited = group[group.identity_status == "resolved"]
        result["years"].append({"year": int(year), "members": len(group),
                                "identity_accredited": len(accredited),
                                "concepts_available": {key: int(accredited[key].sum()) for key in concepts},
                                "concepts_fresh_460d": {key: int(accredited[f"{key}_fresh"].sum())
                                                        for key in concepts},
                                "roic_inputs": int(accredited.roic_inputs.sum()),
                                "fcf_inputs": int(accredited.fcf_inputs.sum())})
    return result
