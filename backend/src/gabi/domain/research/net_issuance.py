"""Net share issuance, ``NSI-v1``: the data gate of the reserve candidate of #268 (#252).

Pontiff and Woodgate (2008) measure issuance as the log change of split-adjusted
shares outstanding. Here the split adjustment comes from the filing itself: a 10-K
reports the basic weighted-average shares of the fiscal year and of the previous
one, and ASC 260 requires the comparative figure to be restated retroactively for
splits and stock dividends. Both figures of the same accession are therefore on
one basis:

    issuance = ln(basic weighted shares, year t / same 10-K's figure for year t−1)

The premise is audited, not assumed: the comparative figure of filing t must
match the figure filing t−1 reported for its own year, or differ from it by a
simple split ratio (``SPLIT_RATIOS``). A mismatch means the restatement or the
share classes cannot be trusted for that issuer-date.

Only original 10-K filings (no 10-K/A) filed before the signal count, and the
anchor year must be at most 550 days old. Nothing here reads prices or returns.
"""

import math
from dataclasses import dataclass
from datetime import date

VERSION = "nsi-v1"
SHARE_TAGS = ("WeightedAverageNumberOfSharesOutstandingBasic",
              "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted")
MAX_ANCHOR_AGE_DAYS = 550
ANNUAL_DAYS = (340, 380)
YEAR_TOLERANCE_DAYS = 45
RECONCILE_TOLERANCE = 0.005
SPLIT_RATIOS = (1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 15.0, 20.0)
COVERAGE_THRESHOLD = 0.70  # Issuer-dates with both figures in one 10-K, over all members.
RECONCILED_THRESHOLD = 0.90  # Of the issuer-dates that have a previous 10-K to audit against.


@dataclass(frozen=True)
class Issuance:
    value: float | None
    state: str  # computed | absent | stale | not_meaningful
    reason: str | None
    anchor: str | None = None
    accession: str | None = None
    check: str = "no_previous_filing"  # reconciled | split_restated | mismatch | no_previous_filing


def _day(text: str) -> date:
    return date.fromisoformat(text)


def _annual(entries: list[dict], signal: date) -> dict[str, dict[str, float]]:
    """``{accession: {fiscal year end: value}}`` of the original 10-Ks filed before the signal."""
    by_filing: dict[str, dict[str, float]] = {}
    filed: dict[str, str] = {}
    for entry in entries:
        if entry.get("form") != "10-K" or not entry.get("filed") or str(entry["filed"]) >= signal.isoformat():
            continue
        if not entry.get("start") or not entry.get("end") or entry.get("val") is None:
            continue
        try:
            days = (_day(entry["end"]) - _day(entry["start"])).days
        except ValueError:
            continue
        if not ANNUAL_DAYS[0] <= days <= ANNUAL_DAYS[1]:
            continue
        values = by_filing.setdefault(entry["accn"], {})
        if entry["end"] in values and values[entry["end"]] != float(entry["val"]):
            values[entry["end"]] = math.nan  # Same filing, same year, two values: unusable.
        else:
            values[entry["end"]] = float(entry["val"])
        filed[entry["accn"]] = str(entry["filed"])
    return {accession: values for accession, values in sorted(by_filing.items(), key=lambda item: filed[item[0]])}


def _near(values: dict[str, float], target: date) -> float | None:
    close = sorted((abs((_day(end) - target).days), end) for end in values
                   if abs((_day(end) - target).days) <= YEAR_TOLERANCE_DAYS)
    return values[close[0][1]] if close else None


def _filings(facts: dict, signal: date) -> dict[str, dict[str, float]]:
    """Per accession, the values of the first share tag that filing reports, in filing order."""
    families = facts.get("facts", {}).get("us-gaap", {})
    merged: dict[str, dict[str, float]] = {}
    order: list[str] = []
    for tag in SHARE_TAGS:
        entries = (families.get(tag) or {}).get("units", {}).get("shares", [])
        for accession, values in _annual(entries, signal).items():
            if accession not in merged:
                merged[accession] = values
                order.append(accession)
    filed = {entry["accn"]: str(entry.get("filed")) for tag in SHARE_TAGS
             for entry in (families.get(tag) or {}).get("units", {}).get("shares", [])}
    return {accession: merged[accession] for accession in sorted(order, key=lambda accn: filed[accn])}


def reconcile(comparative: float, reported: float) -> str:
    ratio = comparative / reported
    if abs(ratio - 1) <= RECONCILE_TOLERANCE:
        return "reconciled"
    if any(abs(ratio / split - 1) <= RECONCILE_TOLERANCE or abs(ratio * split - 1) <= RECONCILE_TOLERANCE
           for split in SPLIT_RATIOS):
        return "split_restated"
    return "mismatch"


def issuance(facts: dict, signal: date) -> Issuance:
    filings = _filings(facts, signal)
    if not filings:
        return Issuance(None, "absent", "no_annual_report")
    accession, values = list(filings.items())[-1]
    anchor = max(values)
    if (signal - _day(anchor)).days > MAX_ANCHOR_AGE_DAYS:
        return Issuance(None, "stale", "annual_report_too_old", anchor, accession)
    current = values[anchor]
    prior_end = date(_day(anchor).year - 1, _day(anchor).month, min(_day(anchor).day, 28))
    prior = _near({end: value for end, value in values.items() if end != anchor}, prior_end)
    if math.isnan(current) or prior is None or math.isnan(prior):
        return Issuance(None, "absent", "no_comparative_year", anchor, accession)
    if current <= 0 or prior <= 0:
        return Issuance(None, "not_meaningful", "non_positive_shares", anchor, accession)
    check = "no_previous_filing"
    for older_values in reversed(list(filings.values())[:-1]):
        older_anchor = max(older_values)
        if abs((_day(older_anchor) - prior_end).days) <= YEAR_TOLERANCE_DAYS:
            own = older_values[older_anchor]
            check = "mismatch" if math.isnan(own) or own <= 0 else reconcile(prior, own)
            break
    return Issuance(math.log(current / prior), "computed", None, anchor, accession, check)


def coverage(rows: list[dict]) -> dict:
    """Coverage over all members and, where a previous 10-K exists, the share that reconciles."""
    computed = [row for row in rows if row["state"] == "computed"]
    audited = [row for row in computed if row["check"] != "no_previous_filing"]
    reconciled = sum(row["check"] in {"reconciled", "split_restated"} for row in audited)
    reasons: dict[str, int] = {}
    for row in rows:
        if row["state"] != "computed":
            reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    share = len(computed) / len(rows) if rows else None
    agreement = reconciled / len(audited) if audited else None
    return {"members": len(rows), "computed": len(computed), "coverage": share,
            "audited": len(audited), "reconciled": reconciled, "split_restated":
                sum(row["check"] == "split_restated" for row in audited), "reconciled_share": agreement,
            "passes": share is not None and share >= COVERAGE_THRESHOLD
            and agreement is not None and agreement >= RECONCILED_THRESHOLD,
            "missing_reasons": dict(sorted(reasons.items(), key=lambda item: -item[1]))}
