"""Offline 2010-2015 SEC concept coverage for historical index members.

Run ``python -m gabi.historical_sec_audit``. This is a coverage inventory,
not a ranking or a substitute for a dated issuer/security identity check.
"""
import argparse
import json
from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import config, edgar, historical_membership
from .historical_data_audit import connect_readonly

CONCEPT_TAGS = {
    "revenue": edgar.REVENUE_TAGS,
    "operating_income": edgar.OPERATING_INCOME_TAGS,
    "net_income": edgar.NET_INCOME_TAGS,
    "equity": edgar.EQUITY_TAGS,
    "cash": edgar.CASH_TAGS,
    "long_term_debt": edgar.LT_DEBT_TAGS,
    "operating_cash_flow": edgar.OCF_TAGS,
    "capex": edgar.CAPEX_TAGS,
    "shares": edgar.SHARES_TAGS,
    "depreciation": edgar.DEPRECIATION_TAGS,
}
TAG_CONCEPTS = defaultdict(list)
for concept, tags in CONCEPT_TAGS.items():
    for tag in tags:
        TAG_CONCEPTS[tag].append(concept)

OUTPUT = config.BASE_DIR / "docs" / "historical-sec-2010-2015.csv"
SUMMARY = config.BASE_DIR / "docs" / "historical-sec-2010-2015.json"


def filing_status(filing_dates: list[str], as_of: str) -> tuple[bool, bool]:
    """Any prior filing and one in the last 460 days, without period-end lookahead."""
    index = bisect_right(filing_dates, as_of)
    if index == 0:
        return False, False
    fresh_since = (date.fromisoformat(as_of) - timedelta(days=460)).isoformat()
    return True, filing_dates[index - 1] >= fresh_since


def load_concept_dates(conn) -> dict[tuple[str, str], list[str]]:
    """Use exact attributed SEC facts, never rounded NUM dates or ticker cache."""
    query = """
      SELECT e.cik,
             json_extract(o.payload_json,'$.tag') AS tag,
             json_extract(o.payload_json,'$.unit') AS unit,
             json_extract(o.payload_json,'$.filed_date') AS filed
      FROM entity_observations o JOIN entities e USING(entity_id)
      WHERE o.dataset='edgar_facts' AND e.cik IS NOT NULL
        AND json_extract(o.payload_json,'$.filed_date')<='2015-12-31'
        AND json_extract(o.payload_json,'$.filed_date')>=json_extract(o.payload_json,'$.end_date')
        AND json_extract(o.payload_json,'$.form') IN ('10-K','10-Q','10-K/A','10-Q/A')
      GROUP BY e.cik,tag,unit,filed
    """
    dates: dict[tuple[str, str], set[str]] = defaultdict(set)
    for cik, tag, unit, filed in conn.execute(query):
        if not filed:
            continue
        for concept in TAG_CONCEPTS.get(tag, []):
            if unit == ("shares" if concept == "shares" else "USD"):
                dates[(cik, concept)].add(filed)
    return {key: sorted(value) for key, value in dates.items()}


def audit(db: Path = config.DB_PATH) -> tuple[pd.DataFrame, dict]:
    with connect_readonly(db) as conn:
        dates = load_concept_dates(conn)
        bulk = conn.execute("SELECT COUNT(*),COUNT(DISTINCT accn) FROM sec_bulk_facts").fetchone()
        exact = conn.execute("SELECT COUNT(*) FROM entity_observations WHERE dataset='edgar_facts' "
                             "AND json_extract(payload_json,'$.filed_date') BETWEEN '2010-01-01' AND '2015-12-31'").fetchone()[0]
        evidence = conn.execute("SELECT COUNT(*) FROM entity_observations WHERE dataset='filing_identity' "
                                "AND json_extract(payload_json,'$.filed_date') BETWEEN '2010-01-01' AND '2015-12-31'").fetchone()[0]
    rows = []
    for year in range(2010, 2016):
        day = f"{year}-12-31"
        members = historical_membership.constituents_as_of(
            day, source_id=historical_membership.REFERENCE_SOURCE, compare_reference=False)["members"]
        for member in members:
            cik = member.get("cik") if member["identity_status"] == "resolved" else None
            row = {"year": year, "as_of": day, "symbol": member["symbol"], "cik": cik,
                   "identity_tier": member.get("identity_tier"),
                   "identity_status": member["identity_status"]}
            for concept in CONCEPT_TAGS:
                available, fresh = filing_status(dates.get((cik, concept), []), day) if cik else (False, False)
                row[concept] = available
                row[f"{concept}_fresh"] = fresh
            row["roic_inputs"] = all(row[key] for key in ("net_income", "equity", "long_term_debt"))
            row["fcf_inputs"] = row["operating_cash_flow"] and row["capex"]
            row["missing_concepts"] = ";".join(key for key in CONCEPT_TAGS if not row[key])
            rows.append(row)
    frame = pd.DataFrame(rows)
    summary = {"database": db.name, "source": "SEC XBRL exact facts by CIK, filed_date cutoff",
               "bulk_num_rows": bulk[0], "bulk_accessions": bulk[1],
               "exact_facts_filed_2010_2015": exact, "filing_identity_observations": evidence,
               "first_filed_by_concept": {concept: min((days[0] for (cik, item), days in dates.items()
                                                      if item == concept), default=None)
                                          for concept in CONCEPT_TAGS},
               "years": []}
    for year, group in frame.groupby("year"):
        accredited = group[group.identity_status == "resolved"]
        summary["years"].append({"year": int(year), "members": len(group),
                                 "identity_accredited": len(accredited),
                                 "concepts_available": {key: int(accredited[key].sum()) for key in CONCEPT_TAGS},
                                 "concepts_fresh_460d": {key: int(accredited[f"{key}_fresh"].sum())
                                                         for key in CONCEPT_TAGS},
                                 "roic_inputs": int(accredited.roic_inputs.sum()),
                                 "fcf_inputs": int(accredited.fcf_inputs.sum())})
    return frame, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=OUTPUT)
    parser.add_argument("--json", type=Path, default=SUMMARY)
    args = parser.parse_args()
    frame, summary = audit()
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.csv, index=False)
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
