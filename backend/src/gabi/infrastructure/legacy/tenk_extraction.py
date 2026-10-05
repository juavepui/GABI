"""SEC downloads, the old issuer evidence and output files for the 10-K extraction pilot (#41).

Explicit command: it downloads pinned SEC documents and writes the pilot results.
"""
import io
import json
import re
from pathlib import Path

import pandas as pd
import requests

from gabi import edgar, identity, sec_history, storage
from gabi import factor_stability as fs
from gabi import historical_issuer_evidence as ie
from gabi.domain.research import tenk_extraction as pilot

TAGS = {
    "revenue": edgar.REVENUE_TAGS,
    "net_income": edgar.NET_INCOME_TAGS,
    "operating_income": edgar.OPERATING_INCOME_TAGS,
    "equity": edgar.EQUITY_TAGS,
    "long_term_debt": edgar.LT_DEBT_TAGS,
    "operating_cash_flow": edgar.OCF_TAGS,
    "capex": edgar.CAPEX_TAGS,
    "depreciation": edgar.DEPRECIATION_TAGS,
}


def parsed(html: str) -> tuple[list[pd.DataFrame], str] | None:
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        return None
    return tables, pilot.document_text(html)


def extract(documents: list[str]) -> dict:
    return pilot.extract([item for html in documents if (item := parsed(html)) is not None])


def _companyfacts(cik: str, directory: Path) -> dict:
    url = edgar.COMPANYFACTS_URL.format(cik=cik)
    try:
        path = sec_history.download(url, directory / "companyfacts" / f"CIK{cik}.json")
    except requests.HTTPError as exc:
        # Emisores que nunca presentaron XBRL (desaparecidos antes de 2009): sin comparativos.
        if exc.response is not None and exc.response.status_code == 404:
            return {}
        raise
    return json.loads(path.read_text())


def _xbrl_value(cik: str, item: str, directory: Path) -> tuple[float | None, str | None]:
    _kind, _pattern, period = pilot.PATTERNS[item]
    return pilot.first_xbrl_value(_companyfacts(cik, directory), [*TAGS[item], *pilot.EXTRA_TAGS[item]],
                                  period, "2008-12-31")


def sample(directory: Path) -> list[dict]:
    """30 miembros del S&P 500 a 2008-12-31 con 10-K del ejercicio 2008 presentado en 2009 y XBRL posterior."""
    from gabi import historical_membership as hm
    from gabi import historical_period as hp
    from gabi.historical_identity_audit import CANDIDATE_SOURCE, _candidate_map

    members = hm.constituents_as_of("2008-12-31", source_id=hp.REFERENCE_SOURCE_FULL, compare_reference=False)["symbols"]
    with storage.get_connection() as conn:
        cands = conn.execute("SELECT symbol,cik,name,date_added,date_removed,observed_from FROM "
                             "historical_issuer_candidates WHERE source_id=?", (CANDIDATE_SOURCE,)).fetchall()
    cmap = _candidate_map(cands, "2008-12-31")
    pool = []
    for symbol in sorted(members):
        cik = cmap.get(symbol, {}).get("cik")
        life = ie.listing_life(cik) if cik else None
        reports = [r for r in (life or {}).get("annual_reports", []) if "2009-01-15" <= r["filed"] <= "2009-04-15"]
        if cik and reports:
            revenue, _ = _xbrl_value(identity.normalize_cik(cik), "revenue", directory)
            if revenue is not None:
                pool.append({"symbol": symbol, "cik": identity.normalize_cik(cik), "report": reports[0]})
    step = max(1, len(pool) // pilot.SAMPLE_SIZE)
    return pool[::step][:pilot.SAMPLE_SIZE]


def _documents(cik: str, report: dict, work: Path) -> list[str]:
    accession = report["accession"]
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
    index = json.loads(sec_history.download(f"{base}/index.json", work / f"{accession}-index.json").read_text())
    names = [report["primary"]] + [item["name"] for item in index["directory"]["item"]
                                   if re.search(r"ex-?13|exv13|ex13", item["name"].lower())
                                   and item["name"].lower().endswith((".htm", ".html"))]
    return [sec_history.download(f"{base}/{name}", work / f"{accession}_{name}").read_text(encoding="latin-1")
            for name in dict.fromkeys(names)]


def run(root: Path, directory: Path, subset: str | None = None) -> dict:
    """``directory``: the 1996-2015 validation folder; results go to ``root/docs/tenk-extraction-pilot``."""
    rows = []
    chosen = sample(directory) if subset is None else pilot.split(sample(directory))[subset]
    for company in chosen:
        extracted = extract(_documents(company["cik"], company["report"], directory / "tenk_pilot"))
        for item in pilot.PATTERNS:
            xbrl, filed = _xbrl_value(company["cik"], item, directory)
            value = extracted.get(item)
            error = abs(value - xbrl) / abs(xbrl) if value is not None and xbrl not in (None, 0) else None
            rows.append({"symbol": company["symbol"], "cik": company["cik"], "item": item,
                         "extraido": value, "xbrl": xbrl, "xbrl_filed": filed, "error_relativo": error,
                         "coincide": bool(error is not None and error <= pilot.TOLERANCE)})
        print(company["symbol"], sum(r["coincide"] for r in rows if r["symbol"] == company["symbol"]), flush=True)
    frame = pd.DataFrame(rows)
    output = root / "docs" / "tenk-extraction-pilot"
    output.mkdir(parents=True, exist_ok=True)
    suffix = f"-{subset}" if subset else ""
    frame.to_csv(output / f"pilot{suffix}.csv", index=False)
    summary = fs._json_safe(pilot.summary(frame, len(chosen)))
    (output / f"pilot{suffix}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
    return summary
