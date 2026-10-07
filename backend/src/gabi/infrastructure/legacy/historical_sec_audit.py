"""Read-only SQLite, the old index membership and SEC tag lists for the 2010-2015 coverage audit."""
import json
from pathlib import Path

import pandas as pd

from gabi.domain.research import historical_sec_audit as audit_rules
from gabi.infrastructure.storage.readonly import connect_readonly

FACTS = """
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


def concept_tags() -> dict[str, list[str]]:
    from gabi import edgar

    return {"revenue": edgar.REVENUE_TAGS, "operating_income": edgar.OPERATING_INCOME_TAGS,
            "net_income": edgar.NET_INCOME_TAGS, "equity": edgar.EQUITY_TAGS, "cash": edgar.CASH_TAGS,
            "long_term_debt": edgar.LT_DEBT_TAGS, "operating_cash_flow": edgar.OCF_TAGS,
            "capex": edgar.CAPEX_TAGS, "shares": edgar.SHARES_TAGS, "depreciation": edgar.DEPRECIATION_TAGS}


def load_concept_dates(conn) -> dict[tuple[str, str], list[str]]:
    """Use exact attributed SEC facts, never rounded NUM dates or ticker cache."""
    return audit_rules.concept_dates(conn.execute(FACTS), concept_tags())


def audit(db: Path) -> tuple[pd.DataFrame, dict]:
    from gabi import historical_membership

    concepts = list(concept_tags())
    with connect_readonly(db) as conn:
        dates = load_concept_dates(conn)
        bulk = conn.execute("SELECT COUNT(*),COUNT(DISTINCT accn) FROM sec_bulk_facts").fetchone()
        exact = conn.execute("SELECT COUNT(*) FROM entity_observations WHERE dataset='edgar_facts' "
                             "AND json_extract(payload_json,'$.filed_date') BETWEEN '2010-01-01' AND '2015-12-31'").fetchone()[0]
        evidence = conn.execute("SELECT COUNT(*) FROM entity_observations WHERE dataset='filing_identity' "
                                "AND json_extract(payload_json,'$.filed_date') BETWEEN '2010-01-01' AND '2015-12-31'").fetchone()[0]
    rows = []
    for year in audit_rules.YEARS:
        members = historical_membership.constituents_as_of(
            f"{year}-12-31", source_id=historical_membership.REFERENCE_SOURCE, compare_reference=False)["members"]
        rows.extend(audit_rules.member_rows(year, members, dates, concepts))
    frame = pd.DataFrame(rows)
    counts = {"database": db.name, "source": "SEC XBRL exact facts by CIK, filed_date cutoff",
              "bulk_num_rows": bulk[0], "bulk_accessions": bulk[1],
              "exact_facts_filed_2010_2015": exact, "filing_identity_observations": evidence}
    return frame, audit_rules.summary(frame, dates, concepts, counts)


def run(db: Path, csv: Path, summary_path: Path) -> dict:
    frame, values = audit(db)
    csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv, index=False)
    summary_path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return values
