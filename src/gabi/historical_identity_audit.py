"""Offline identity coverage for the archived S&P 500 universe, per period.

2010-2015 (#27) and 2016-2025 (#34) use the same rules; each period writes
its own interval source (``historical_period``).

Community ticker/CIK rows are candidates. Direct SEC ticker evidence and
retrospective issuer corroboration have separate tiers; an issuer name alone
cannot certify a ticker or activate an operational alias.
"""

import argparse
import hashlib
import json
import re
import threading
import time
import unicodedata
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from lxml import etree

from . import config, historical_archive, historical_membership, identity, sec_history, storage
from . import historical_issuer_evidence as issuer_evidence
from .historical_period import P2010, Period
from .historical_period import get as get_period
from .historical_ticker_corrections import apply_nominations, correct_symbols, identity_nominations

QUARTERS = P2010.quarters
TICKER_RE = re.compile(r"[A-Z][A-Z0-9-]{0,11}\Z")
DEI_NAMESPACES = ("http://xbrl.sec.gov/dei/", "http://xbrl.us/dei/")
CANDIDATE_SOURCE = "lawcal:2e59b86998a119d68e377f9f98aa7a816cfc7d5b"
INTERVAL_SOURCE = historical_archive.IDENTITY_INTERVAL_SOURCE
# Quarterly filers report within ~100 days; allow one missed report.
MAX_FIRST_FILING_LAG_DAYS = 200


def _date(value: str | None) -> str | None:
    """lawcal marks inferred effective dates with an asterisk."""
    if not value:
        return None
    cleaned = value.strip().rstrip("*")
    return date.fromisoformat(cleaned).isoformat()


def _candidate_map(rows: list[tuple], as_of: str) -> dict[str, dict]:
    candidates: dict[str, dict[str, set[str]]] = {}
    for symbol, cik, name, added, removed, observed in rows:
        start, end = _date(added), _date(removed)
        if not cik or not start or as_of < start or (end and as_of >= end):
            continue
        symbol = identity.normalize_symbol(symbol)
        item = candidates.setdefault(symbol, {"ciks": set(), "names": set(), "observed_ciks": set()})
        item["ciks"].add(identity.normalize_cik(cik))
        if name:
            item["names"].add(name)
        if observed and (observed_date := _date(observed)) and observed_date <= as_of:
            item["observed_ciks"].add(identity.normalize_cik(cik))
    return {symbol: {"cik": next(iter(data["ciks"])) if len(data["ciks"]) == 1 else None,
                     "candidate_cik_count": len(data["ciks"]),
                     "historical_name_candidate": len(data["ciks"]) == 1 and len(data["names"]) == 1,
                     "row_created_by_date": len(data["observed_ciks"]) == 1 and data["observed_ciks"] == data["ciks"]}
            for symbol, data in candidates.items()}


COMMON_TITLE_RE = re.compile(r"common|capital stock|ordinary share|shares of beneficial interest", re.I)
NON_COMMON_RE = re.compile(r"preferred|preference|depositary|note|debenture|bond|warrant|right|unit|%", re.I)


def _common_stock_symbols(root, raw: list) -> set[str]:
    """Symbols of the common stock among the 12(b) securities of a 2019+ cover.

    Inline XBRL covers tag every listed security (notes, preferred) with its
    own ``TradingSymbol`` in a class-of-stock context; the common stock is the
    one without a dimension, in a common-stock member, or titled as common in
    ``Security12bTitle`` for the same context.
    """
    contexts = {node.get("id"): node for node in root.iter()
                if isinstance(node.tag, str) and node.tag.rsplit("}", 1)[-1] == "context"}
    titles = {node.get("contextRef"): str(node.text or "") for node in root.iter()
              if isinstance(node.tag, str) and node.tag.rsplit("}", 1)[-1] == "Security12bTitle"}
    result = set()
    for node in raw:
        context = contexts.get(node.get("contextRef"))
        members = [str(member.text or "") for member in context.iter()
                   if isinstance(member.tag, str) and member.tag.rsplit("}", 1)[-1] == "explicitMember"
                   ] if context is not None else []
        classes = [member for member in members if "Exchange" not in member and not member.startswith("exch:")]
        title = titles.get(node.get("contextRef"), "")
        if title:
            common = bool(COMMON_TITLE_RE.search(title)) and not NON_COMMON_RE.search(title)
        else:
            common = not classes or all(re.search(r"Common(Stock|Class)", member) for member in classes)
        if common and str(node.text or "").strip():
            result.add(identity.normalize_symbol(str(node.text).strip()))
    return result


def extract_sec_instance(path: Path, *, cik: str, common_stock_only: bool = False,
                         multi_class: frozenset[str] = frozenset()) -> dict:
    """Read ticker and historical issuer name from an original SEC XBRL filing.

    A filing proves its symbol only on its filing date. It cannot by itself
    establish the complete ticker validity interval or index membership.
    With ``common_stock_only`` (2016-2025, #34) a cover listing several 12(b)
    securities proves the common stock's symbol if exactly one is common; if
    several common classes are all in ``multi_class`` (a reviewed multi-class
    nomination of this CIK), each class is proved (``symbols``).
    """
    expected = identity.normalize_cik(cik)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.parse(str(path), parser)
    identifiers = {str(node.text or "").strip().zfill(10)
                   for node in root.xpath("//*[local-name()='identifier']")}
    if identifiers != {expected}:
        raise ValueError(f"XBRL issuer CIK mismatch: {path.name}")
    raw = [node for node in root.iter()
           if isinstance(node.tag, str) and node.tag.rsplit("}", 1)[-1] == "TradingSymbol"
           and node.tag.startswith(tuple("{" + ns for ns in DEI_NAMESPACES))]
    raw_symbols = {str(node.text or "").strip() for node in raw}
    symbols = {identity.normalize_symbol(value) for value in raw_symbols if value}
    if common_stock_only and len(symbols) > 1:
        symbols = _common_stock_symbols(root, raw)
    classes = sorted(symbols) if len(symbols) > 1 and symbols <= multi_class else None
    if classes:
        symbols = {classes[0]}
    if len(symbols) != 1 or not TICKER_RE.fullmatch(next(iter(symbols))):
        raise ValueError(f"Missing or ambiguous SEC trading symbol: {path.name}")
    names = {str(node.text or "").strip() for node in root.iter()
             if isinstance(node.tag, str) and node.tag.rsplit("}", 1)[-1] == "EntityRegistrantName"
             and node.tag.startswith(tuple("{" + ns for ns in DEI_NAMESPACES))
             if str(node.text or "").strip()}
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"symbol": next(iter(symbols)), "cik": expected,
            "historical_name": next(iter(names)) if len(names) == 1 else None,
            "sha256": digest, **({"symbols": classes} if classes else {})}


def scan_local_sec_instances(period: Period = P2010) -> tuple[list[dict], dict]:
    """Inspect already downloaded XBRL instances of the period; never fetch files."""
    directory = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / "instances"
    with storage.get_connection() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "sec_bulk_submissions" not in tables:
            raise ValueError("SEC bulk submissions have not been imported")
        filings = {row[0]: row[1:] for row in conn.execute(
            "SELECT accn,cik,filed_date,instance,name FROM sec_bulk_submissions "
            "WHERE filed_date>=? AND filed_date<? AND instance IS NOT NULL",
            (period.start, period.end_exclusive))}
        candidates = conn.execute("SELECT symbol,cik,name,date_added,date_removed,observed_from "
                                  "FROM historical_issuer_candidates WHERE source_id=?",
                                  (CANDIDATE_SOURCE,)).fetchall() if "historical_issuer_candidates" in tables else []
        snapshots = historical_membership._snapshots(pd.read_sql_query(
            "SELECT date,tickers FROM historical_membership WHERE source_id=? ORDER BY date",
            conn, params=(period.membership_source,))) if "historical_membership" in tables else []
    snapshot_dates = [row[0] for row in snapshots]
    multi_class_nominations = [row for row in identity_nominations() if row["reason"] == "multi_class_issuer"]
    records = []
    failures: dict[str, int] = {}
    for path in sorted(directory.glob("*.xml")):
        metadata = filings.get(path.stem)
        if metadata is None:
            continue
        cik, filed_date, instance, filing_name = metadata
        multi_class = frozenset(ticker for row in multi_class_nominations
                                if row["cik"] == identity.normalize_cik(cik)
                                and row["valid_from"] <= filed_date < row["valid_to"]
                                for ticker in row["sec_tickers"]) if period is not P2010 else frozenset()
        try:
            proof = extract_sec_instance(path, cik=cik, common_stock_only=period is not P2010,
                                         multi_class=multi_class)
        except (OSError, ValueError, etree.XMLSyntaxError) as exc:
            reason = str(exc).split(":", 1)[0]
            failures[reason] = failures.get(reason, 0) + 1
            continue
        proof["historical_name_source"] = "dei" if proof["historical_name"] else None
        if not proof["historical_name"] and filing_name:
            proof["historical_name"] = filing_name
            proof["historical_name_source"] = "sec_sub_index"
        proof.update(accession=path.stem, filed_date=filed_date,
                     source_url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                                f"{path.stem.replace('-', '')}/{instance}")
        candidate = _candidate_map(candidates, filed_date).get(proof["symbol"])
        if candidate is None:
            proof["candidate_status"] = "missing"
        elif candidate["candidate_cik_count"] != 1:
            proof["candidate_status"] = "ambiguous"
        else:
            proof["candidate_status"] = "agrees" if candidate["cik"] == proof["cik"] else "conflicts"
        index = bisect_right(snapshot_dates, filed_date) - 1
        members = correct_symbols(snapshots[index][1], filed_date)[0] if index >= 0 else set()
        for symbol in proof.pop("symbols", [proof["symbol"]]):
            records.append({**proof, "symbol": symbol, "member_in_fja": symbol in members})
    statuses = {status: sum(row["candidate_status"] == status for row in records)
                for status in ("agrees", "conflicts", "ambiguous", "missing")}
    return records, {"filings_with_local_instance": len(records) + sum(failures.values()),
                     "ticker_proofs": len(records), "distinct_ticker_cik_pairs": len({
                         (row["symbol"], row["cik"]) for row in records}),
                     "member_on_filing_date": sum(row["member_in_fja"] for row in records),
                     "historical_names": sum(row["historical_name"] is not None for row in records),
                     "candidate_crosscheck": statuses,
                     "conflict_examples": [{"symbol": row["symbol"], "cik": row["cik"],
                                            "filed_date": row["filed_date"]} for row in records
                                           if row["candidate_status"] in {"conflicts", "ambiguous"}][:20],
                     "rejections": failures}


def fetch_candidate_instances(limit: int, *, prioritize_unresolved: bool = False,
                              period: Period = P2010) -> dict:
    """Cache selected original SEC covers for historic CIK candidates.

    Three filings spread over each candidate's dated tenure give more useful
    checks than downloading every report. Candidate CIKs select *what to check*;
    only a ticker explicitly present in the SEC instance becomes proof.
    Reruns skip existing files and keep the archive's URL/SHA-256 provenance.
    """
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    with storage.get_connection() as conn:
        candidates = conn.execute(
            "SELECT DISTINCT symbol,cik,date_added,date_removed FROM historical_issuer_candidates "
            "WHERE source_id=? AND date_added<? "
            "AND (date_removed IS NULL OR date_removed='' OR date_removed>=?)",
            (CANDIDATE_SOURCE, period.end_exclusive, period.start)).fetchall()
        filings = conn.execute(
            "SELECT accn,cik,filed_date,instance FROM sec_bulk_submissions "
            "WHERE filed_date>=? AND filed_date<? "
            "AND form IN ('10-K','10-Q') AND instance IS NOT NULL ORDER BY filed_date,accn",
            (period.start, period.end_exclusive)).fetchall()
        candidates += [(row["label"], row["cik"],
                        (date.fromisoformat(row["valid_from"]) - timedelta(days=row["evidence_window_days"])).isoformat(),
                        (date.fromisoformat(row["valid_to"]) + timedelta(days=row["evidence_window_days"])).isoformat())
                       for row in identity_nominations()]
        unresolved = conn.execute(
            "SELECT cik,valid_from,valid_to FROM historical_identity_intervals "
            "WHERE source_id=? AND status='unresolved'",
            (period.identity_source,)).fetchall() if prioritize_unresolved else []
    by_cik: dict[str, list[tuple]] = {}
    for row in filings:
        by_cik.setdefault(identity.normalize_cik(row[1]), []).append(row)
    selected: dict[str, tuple] = {}
    missing_candidates = 0
    for _symbol, cik, added, removed in candidates:
        start = max(_date(added) or period.start, period.start)
        end = min(_date(removed) or period.end_exclusive, period.end_exclusive)
        eligible = [row for row in by_cik.get(identity.normalize_cik(cik), [])
                    if start <= row[2] < end]
        if len(eligible) < 2:
            missing_candidates += 1
            continue
        for index in {0, len(eligible) // 2, len(eligible) - 1}:
            row = eligible[index]
            selected[row[0]] = row
    # The ordinary three-per-candidate sample is already cached. For a second
    # pass, inspect remaining filings only inside still-unresolved intervals;
    # never broaden an ambiguous ticker/CIK association automatically.
    for cik, start, end in unresolved:
        for row in by_cik.get(identity.normalize_cik(cik), []):
            if start <= row[2] < end:
                selected[row[0]] = row
    directory = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / "instances"
    already_cached = 0
    pending: list[tuple[str, str, Path]] = []
    for accn, cik, _filed, instance in sorted(selected.values(), key=lambda row: (row[2], row[0])):
        path = directory / f"{accn}.xml"
        if path.exists():
            already_cached += 1
            continue
        if len(pending) >= limit:
            continue
        url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
               f"{accn.replace('-', '')}/{instance}")
        pending.append((accn, url, path))
    # Pace starts across workers: 4/s, including retries, below SEC's 10/s cap.
    pace_lock = threading.Lock()
    next_start = time.monotonic()

    def paced_download(url: str, path: Path) -> None:
        nonlocal next_start
        with pace_lock:
            now = time.monotonic()
            delay = max(0, next_start - now)
            next_start = max(now, next_start) + 0.25
        if delay:
            time.sleep(delay)
        sec_history.download(url, path)

    def fetch_one(accn: str, url: str, path: Path) -> tuple[str, str | None]:
        for attempt in range(3):
            try:
                paced_download(url, path)
                return accn, None
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return accn, str(exc)
            except (requests.RequestException, OSError, ValueError) as exc:
                return accn, str(exc)
        return accn, "retries exhausted"

    fetched = failures = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch_one, *item) for item in pending]
        for future in as_completed(futures):
            accn, error = future.result()
            if error:
                failures += 1
                print(f"SEC identity download failed {accn}: {error}", flush=True)
            else:
                fetched += 1
            if (fetched + failures) % 50 == 0:
                print(f"SEC identity covers attempted: {fetched + failures}", flush=True)
    return {"selected_filings": len(selected), "already_cached": already_cached,
            "fetched": fetched, "failed": failures,
            "candidates_with_fewer_than_two_filings": missing_candidates,
            "prioritize_unresolved": prioritize_unresolved}


def import_nominated_filings(period: Period = P2010) -> dict:
    """Index SEC bulk 10-K/10-Q rows for nominated CIKs from the cached archive.

    The quarterly Financial Statement Data Sets are already archived with
    their URL/SHA-256; this only adds rows for CIKs no candidate selected.
    """
    ciks = {row["cik"] for row in identity_nominations()}
    with storage.get_connection() as conn:
        sec_history.ensure_schema(conn)
        # Present means indexed for this period's quarters, not for another period.
        first_year = period.years.start - (1 if period is P2010 else 0)
        present = {row[0] for row in conn.execute(
            "SELECT DISTINCT cik FROM sec_bulk_submissions WHERE filed_date>=? AND filed_date<?",
            (f"{first_year}-01-01", period.end_exclusive))}
    missing = ciks - present
    report: dict[str, object] = {"nominated_ciks": len(ciks), "missing_before": len(missing)}
    if not missing:
        return report
    for year in range(period.years.start - (1 if period is P2010 else 0), period.years.stop):
        for quarter in range(1, 5):
            key = f"{year}q{quarter}"
            url = f"https://www.sec.gov/files/dera/data/financial-statement-data-sets/{key}.zip"
            path = sec_history.download(url, sec_history.DIRECTORY / f"{key}.zip")
            report[key] = sec_history.import_quarter(path, url, missing, facts=period is P2010)
            print(key, report[key], flush=True)
    return report


def import_period_filings(period: Period) -> dict:
    """Index SEC bulk 10-K/10-Q submissions of every candidate CIK of a period.

    For 2010-2015 this was done by ``sec_history.run_bulk`` (#27). Only the
    SUB table is read here (form, filing date, instance, issuer name); facts
    for 2016+ come from Company Facts. Quarters already indexed are skipped.
    """
    with storage.get_connection() as conn:
        sec_history.ensure_schema(conn)
        ciks = {identity.normalize_cik(row[0]) for row in conn.execute(
            "SELECT DISTINCT cik FROM historical_issuer_candidates WHERE source_id=? AND cik<>'' "
            "AND replace(date_added,'*','')<? "
            "AND (date_removed IS NULL OR date_removed='' OR replace(date_removed,'*','')>=?)",
            (CANDIDATE_SOURCE, period.end_exclusive, period.start))}
    ciks |= {row["cik"] for row in identity_nominations()
             if row["valid_from"] < period.end_exclusive and row["valid_to"] > period.start}
    report: dict[str, object] = {"ciks": len(ciks)}
    # Only quarters inside the period: adding rows filed before it would
    # change the evidence of the previous period's intervals.
    for year in period.years:
        for quarter in range(1, 5):
            key = f"{year}q{quarter}"
            url = f"https://www.sec.gov/files/dera/data/financial-statement-data-sets/{key}.zip"
            path = sec_history.download(url, sec_history.DIRECTORY / f"{key}.zip")
            report[key] = sec_history.import_quarter(path, url, ciks, facts=False)
            print(key, report[key], flush=True)
    return report


def annual_report_symbol_evidence(limit: int, period: Period = P2010) -> dict:
    """Ticker proofs from 10-K text for intervals the XBRL covers left open.

    Early XBRL covers often omit ``dei:TradingSymbol``. The annual report's
    market section states the symbol; a report naming exactly one symbol is
    stored like a cover proof (URL + SHA-256), otherwise it is ignored.
    """
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    with storage.get_connection() as conn:
        rows = conn.execute(
            "SELECT symbol,cik,valid_from,valid_to,status FROM historical_identity_intervals "
            "WHERE source_id=? AND status IN ('unresolved','corroborated_candidate')",
            (period.identity_source,)).fetchall()
    nominated = {(row["label"], row["cik"]) for row in identity_nominations()}
    # Unresolved intervals, plus nominations still resting on one SEC ticker
    # observation; community-name corroborations are left as they are.
    targets = [row for row in rows if row[4] == "unresolved" or (row[0], row[1]) in nominated]
    downloads = 0
    records = []
    for _symbol, cik, start, end, _status in targets:
        life = issuer_evidence.listing_life(cik)
        if life is None:
            continue
        reports = [row for row in life["annual_reports"] if start <= row["filed"] < end]
        for report in [reports[index] for index in sorted({0, len(reports) - 1})] if reports else []:
            if downloads >= limit:
                break
            url, path = issuer_evidence.fetch_annual_report(cik, report)
            downloads += 1
            extended = period is not P2010
            symbols = issuer_evidence.annual_report_symbols(path.read_text(encoding="utf-8", errors="ignore"),
                                                            extended=extended)
            if extended and len(symbols) > 1:
                # Other companies' symbols (investees, spin-offs) appear in the
                # text; keep the one reviewed ticker of this CIK, if unique.
                reviewed = {ticker for row in identity_nominations() if row["cik"] == cik
                            and row["valid_from"] <= report["filed"] < row["valid_to"] for ticker in row["sec_tickers"]}
                symbols &= reviewed
            if len(symbols) != 1:
                continue
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            records.append({"symbol": next(iter(symbols)), "cik": cik, "accession": report["accession"],
                            "filed_date": report["filed"], "historical_name": life["name"],
                            "historical_name_source": "sec_10k_text", "sha256": digest, "source_url": url})
    imported = historical_archive.import_filing_identity_evidence(records)
    return {"intervals": len(targets), "reports": downloads, "symbol_proofs": imported}


def _name_tokens(value: str) -> list[str]:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").upper()
    value = re.sub(r"\bINT'?L\b", "INTERNATIONAL", value)
    tokens = re.findall(r"[A-Z0-9]+", value)
    noise = {"THE", "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY",
             "LTD", "LIMITED", "PLC", "GROUP", "HOLDINGS", "HOLDING", "DE", "OF"}
    cleaned = ["INTERNATIONAL" if token in {"INTL", "INT"} else token
               for token in tokens if token not in noise]
    # Index constituent names sometimes append the share class to the issuer.
    if cleaned and cleaned[-1] in {"A", "B", "C"}:
        cleaned.pop()
    return cleaned


def _name_matches(candidate: str | None, filed: str | None) -> bool:
    if not candidate or not filed:
        return False
    left, right = _name_tokens(candidate), _name_tokens(filed)
    if not left or not right:
        return False
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    joined = ("".join(left), "".join(right))
    if joined[0] == joined[1] or sorted(left) == sorted(right):
        return True
    if min(map(len, joined)) >= 4 and (joined[0].startswith(joined[1]) or
                                      joined[1].startswith(joined[0])):
        return True
    # IBM/BNY-style abbreviated legal names; require every remaining token.
    if len(short) == 1 and len(short[0]) >= 3 and short[0] == "".join(t[0] for t in long):
        return True
    if len(short) > 1:
        for count in range(2, len(long)):
            if short[0] == "".join(token[0] for token in long[:count]) and short[1:] == long[count:]:
                return True
    generic = {"AMERICAN", "UNITED", "GENERAL", "NATIONAL", "BANK", "FIRST"}
    return bool(left[0] == right[0] and len(left[0]) >= 7 and left[0] not in generic)


def fetch_issuer_name_histories(limit: int, period: Period = P2010) -> dict:
    """Cache SEC's official name chain for still-unresolved historical CIKs."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    with storage.get_connection() as conn:
        ciks = [row[0] for row in conn.execute(
            "SELECT DISTINCT cik FROM historical_identity_intervals "
            "WHERE source_id=? AND status='unresolved' AND cik IN "
            "(SELECT cik FROM sec_bulk_submissions GROUP BY cik HAVING COUNT(*)>=2) ORDER BY cik",
            (period.identity_source,))]
    directory = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / "identity_submissions"
    cached = fetched = failed = 0
    for cik in ciks:
        path = directory / f"CIK{cik}.json"
        if path.exists():
            cached += 1
            continue
        if fetched + failed >= limit:
            break
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            sec_history.download(url, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            if identity.normalize_cik(payload["cik"]) != cik:
                raise ValueError("SEC submissions issuer CIK mismatch")
            fetched += 1
        except (requests.RequestException, OSError, ValueError, KeyError) as exc:
            failed += 1
            print(f"SEC issuer name history failed {cik}: {exc}", flush=True)
    return {"candidate_ciks": len(ciks), "cached": cached, "fetched": fetched, "failed": failed}


def _official_name_chain(cik: str) -> dict | None:
    path = (config.DATA_DIR / "history_refresh" / "validation_1996_2015" /
            "identity_submissions" / f"CIK{cik}.json")
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if identity.normalize_cik(payload["cik"]) != cik:
        raise ValueError(f"SEC name history CIK mismatch: {path.name}")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    names = [payload.get("name", "")] + [row["name"] for row in payload.get("formerNames", [])]
    return {"names": names, "source_url": f"https://data.sec.gov/submissions/CIK{cik}.json",
            "sha256": digest}


def build_evidence_intervals(period: Period = P2010) -> list[dict]:
    """Corroborate candidate/member intervals with dated SEC primary evidence.

    The resulting tier is retrospective research evidence. Membership and
    community candidate dates bound it, but are not themselves SEC-verified
    ticker-change dates. It is deliberately separate from entity_aliases.
    """
    with storage.get_connection() as conn:
        identity.ensure_schema(conn)
        history = pd.read_sql_query(
            "SELECT date,tickers FROM historical_membership WHERE source_id=? AND date<? ORDER BY date",
            conn, params=(period.membership_source, period.end_exclusive))
        candidates = conn.execute(
            "SELECT symbol,cik,name,date_added,date_removed,observed_from "
            "FROM historical_issuer_candidates WHERE source_id=?",
            (CANDIDATE_SOURCE,)).fetchall()
        proofs = conn.execute(
            "SELECT symbol,entity_id,payload_json FROM entity_observations WHERE dataset='filing_identity'").fetchall()
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        submissions = conn.execute(
            "SELECT s.cik,s.accn,s.filed_date,s.name,s.form,s.source_url,a.sha256 "
            "FROM sec_bulk_submissions s LEFT JOIN sec_archive_files a ON a.url=s.source_url "
            "WHERE s.filed_date>=? AND s.filed_date<? "
            "AND s.form IN ('10-K','10-Q')", (period.evidence_from, period.end_exclusive)
        ).fetchall() if {"sec_bulk_submissions", "sec_archive_files"} <= tables else []
    snapshots = historical_membership._snapshots(history)
    if not snapshots or snapshots[0][0] > period.start:
        raise ValueError("Historical membership snapshots missing")
    corrected = [(day, correct_symbols(symbols, day)[0]) for day, symbols in snapshots]
    # The source often keeps the later ANTM label retroactively; insert the
    # independently documented ticker-change date into the temporal series.
    from .historical_ticker_corrections import WLP_END
    prior = [(day, symbols) for day, symbols in snapshots if day < WLP_END]
    if prior and all(day != WLP_END for day, _symbols in snapshots):
        corrected.append((WLP_END, correct_symbols(prior[-1][1], WLP_END)[0]))
    corrected.sort(key=lambda row: row[0])
    frame = pd.DataFrame([(day, ",".join(sorted(symbols))) for day, symbols in corrected],
                         columns=["date", "tickers"])
    memberships = historical_membership.intervals(frame, period.end_exclusive)
    by_symbol: dict[str, list[dict]] = {}
    for symbol, cik, name, added, removed, _observed in candidates:
        if not cik or not (start := _date(added)):
            continue
        by_symbol.setdefault(identity.normalize_symbol(symbol), []).append({
            "cik": identity.normalize_cik(cik), "name": name,
            "start": start, "end": _date(removed) or "9999-12-31"})
    # Reviewed nominations only choose which CIK to test; the SEC ticker
    # evidence below still decides the tier.
    by_symbol = apply_nominations(by_symbol)
    evidence: dict[str, list[dict]] = {}
    evidence_by_cik: dict[str, list[dict]] = {}
    for symbol, entity_id, payload_json in proofs:
        payload = json.loads(payload_json)
        # Each period sees only proofs filed inside its own evidence window, so
        # rebuilding one period is unaffected by evidence gathered for another.
        if "filed_date" in payload and period.evidence_from <= payload["filed_date"] < period.end_exclusive:
            record = {**payload, "symbol": symbol, "cik": entity_id.removeprefix("cik:")}
            evidence.setdefault(symbol, []).append(record)
            evidence_by_cik.setdefault(record["cik"], []).append(record)
    filings_by_cik: dict[str, list[dict]] = {}
    for cik, accn, filed_date, name, form, source_url, sha256 in submissions:
        filings_by_cik.setdefault(identity.normalize_cik(cik), []).append({
            "cik": identity.normalize_cik(cik), "accession": accn,
            "filed_date": filed_date, "historical_name": name,
            "form": form, "source_url": source_url, "sha256": sha256,
            "evidence_kind": "sec_bulk_issuer_name_no_ticker"})
    official_names = {cik: _official_name_chain(cik) for cik in filings_by_cik}
    result = []
    for member in memberships:
        symbol = member["symbol"]
        start = max(member["valid_from"], period.start)
        end = min(member["valid_to"], period.end_exclusive)
        if start >= end:
            continue
        candidates_for_symbol = by_symbol.get(symbol, [])
        cuts = {start, end}
        for candidate in candidates_for_symbol:
            if start < candidate["start"] < end:
                cuts.add(candidate["start"])
            if start < candidate["end"] < end:
                cuts.add(candidate["end"])
        boundaries = sorted(cuts)
        for left, right in zip(boundaries, boundaries[1:]):
            active = [row for row in candidates_for_symbol if row["start"] <= left < row["end"]]
            if not active:
                continue
            ciks = {row["cik"] for row in active}
            nomination = next((row["nomination"] for row in active if row.get("nomination")), None)
            tickers = {symbol, *nomination["sec_tickers"]} if nomination else {symbol}
            pad = timedelta(days=nomination["evidence_window_days"]) if nomination else timedelta(0)
            low = (date.fromisoformat(left) - pad).isoformat()
            high = (date.fromisoformat(right) + pad).isoformat()
            relevant = [row for ticker in sorted(tickers) for row in evidence.get(ticker, [])
                        if low <= row["filed_date"] < high]
            # Another issuer reporting the label, or a nominated historical
            # ticker, inside the interval is recycling: never resolve it.
            contradictory = {row["cik"] for row in relevant if left <= row["filed_date"] < right} - ciks
            for cik in sorted(ciks):
                matching = sorted((row for row in relevant if row["cik"] == cik),
                                  key=lambda row: (row["filed_date"], row["accession"]))
                dates = {row["filed_date"] for row in matching}
                issuer_filings = [row for row in filings_by_cik.get(cik, [])
                                  if low <= row["filed_date"] < high]
                issuer_dates = {row["filed_date"] for row in issuer_filings}
                names = [row["name"] for row in active if row["cik"] == cik and row["name"]]
                name_match = any(_name_matches(name, row.get("historical_name"))
                                 for name in names for row in matching + issuer_filings)
                official = official_names.get(cik)
                chain_match = bool(official and
                                   any(_name_matches(name, official_name)
                                       for name in names for official_name in official["names"]) and
                                   any(_name_matches(row["historical_name"], official_name)
                                       for row in issuer_filings for official_name in official["names"]))
                other_tickers = {row["symbol"] for row in evidence_by_cik.get(cik, [])
                                 if row["symbol"] not in tickers and left <= row["filed_date"] < right}
                # A CIK whose first periodic report (full EDGAR history, not
                # the XBRL-only bulk sets) comes well after the interval opens
                # is a later successor, e.g. a holding company of the issuer.
                life = issuer_evidence.listing_life(cik)
                late_start = bool(life and life["first_periodic"] and
                                  date.fromisoformat(life["first_periodic"]) >
                                  date.fromisoformat(left) + timedelta(days=MAX_FIRST_FILING_LAG_DAYS))
                if len(ciks) > 1 or contradictory or other_tickers:
                    status = "ambiguous"
                elif late_start:
                    status = "unresolved"
                elif len(dates) >= 2 and {row["symbol"] for row in matching} == {symbol}:
                    # Two independent SEC covers explicitly report this
                    # ticker and CIK. A community display-name mismatch (GE,
                    # JCP) cannot outweigh the primary ticker evidence; the
                    # no-ticker corroboration tier still requires name match.
                    status = "confirmed_by_multiple_evidence"
                elif len(dates) >= 2:
                    # The label is a later symbol applied retroactively; SEC
                    # covers report the reviewed historical ticker of this CIK.
                    status = "confirmed_historical_ticker"
                elif len(issuer_dates) >= 2 and (name_match or chain_match) and not nomination:
                    status = "corroborated_candidate"
                elif nomination and len(issuer_dates) >= 2 and (
                        dates or set((life or {}).get("current_tickers", [])) & tickers):
                    # A reviewed nomination with repeated SEC reports of the CIK
                    # and one SEC ticker observation (cover or SEC's own ticker
                    # list): as strong as the community-name tier, not stronger.
                    status = "corroborated_candidate"
                else:
                    status = "unresolved"
                references = [{**{key: row.get(key) for key in
                                  ("accession", "filed_date", "source_url", "sha256", "cik")},
                               "evidence_kind": "sec_dei_ticker"}
                              for row in relevant]
                for row in (issuer_filings[:1] + issuer_filings[len(issuer_filings) // 2:len(issuer_filings) // 2 + 1]
                            + issuer_filings[-1:]):
                    if row["accession"] not in {ref["accession"] for ref in references}:
                        references.append({key: row.get(key) for key in
                                           ("accession", "filed_date", "source_url", "sha256", "cik",
                                            "historical_name", "evidence_kind")})
                if nomination and life and set(life.get("current_tickers", [])) & tickers:
                    references.append({"source_url": life["source_url"], "evidence_kind": "sec_submissions_tickers",
                                       "tickers": sorted(set(life["current_tickers"]) & tickers)})
                if chain_match and official:
                    references.append({"source_url": official["source_url"],
                                       "sha256": official["sha256"],
                                       "evidence_kind": "sec_official_name_chain_no_ticker"})
                result.append({"symbol": symbol, "cik": cik, "valid_from": left,
                               "valid_to": right, "status": status,
                               "evidence_count": len(dates) if status == "confirmed_by_multiple_evidence"
                               else len(issuer_dates),
                               "direct_ticker_proofs": len(dates),
                               "sec_issuer_filings": len(issuer_dates),
                               "first_filed": min(dates | issuer_dates) if dates or issuer_dates else None,
                               "last_filed": max(dates | issuer_dates) if dates or issuer_dates else None,
                               "name_match": name_match,
                               "official_name_chain_match": chain_match,
                               "other_sec_tickers_same_cik": sorted(other_tickers),
                               "source_refs": references})
    return result


def coverage_report(period: Period = P2010) -> dict:
    """Measure quarterly member observations, retaining candidate/verified tiers."""
    with storage.get_connection() as conn:
        required = {"historical_membership", "historical_issuer_candidates", "entity_aliases", "entities"}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = required - tables
        if missing:
            raise ValueError(f"Missing local identity tables: {sorted(missing)}")
        history = pd.read_sql_query("SELECT date,tickers FROM historical_membership WHERE source_id=? AND date<? "
                                    "ORDER BY date", conn, params=(period.membership_source, period.end_exclusive))
        candidates = conn.execute("SELECT symbol,cik,name,date_added,date_removed,observed_from "
                                  "FROM historical_issuer_candidates WHERE source_id=?",
                                  (CANDIDATE_SOURCE,)).fetchall()
        aliases = conn.execute("SELECT a.symbol,a.entity_id,e.cik,a.valid_from,a.valid_to,a.confidence "
                               "FROM entity_aliases a JOIN entities e USING(entity_id)").fetchall()
        intervals = conn.execute(
            "SELECT symbol,cik,valid_from,valid_to,status FROM historical_identity_intervals "
            "WHERE source_id=?", (period.identity_source,)).fetchall() if "historical_identity_intervals" in tables else []
        sec_names = conn.execute("SELECT cik,name,filed_date FROM sec_bulk_submissions "
                                 "WHERE name IS NOT NULL AND name<>'' AND filed_date<=?",
                                 (period.last_day,)).fetchall() if "sec_bulk_submissions" in tables else []
    snapshots = historical_membership._snapshots(history)
    quarters = period.quarters
    if not snapshots or snapshots[0][0] > quarters[0] or snapshots[-1][0] > period.last_day:
        raise ValueError("Archived fja05680 membership coverage is missing or invalid")
    snapshot_dates = [row[0] for row in snapshots]
    intervals_by_symbol: dict[str, list[tuple]] = {}
    for row in intervals:
        intervals_by_symbol.setdefault(row[0], []).append(row)
    by_year: dict[str, dict] = {}
    ambiguous_examples: set[str] = set()
    for day in quarters:
        index = bisect_right(snapshot_dates, day) - 1
        symbols, _ = correct_symbols(snapshots[index][1], day)
        candidates_by_symbol = _candidate_map(candidates, day)
        annual = by_year.setdefault(day[:4], {"quarter_dates": [], "member_observations": 0,
                                               "resolved_cik": 0, "resolved_entity_id": 0,
                                               "date_valid_alias": 0, "historical_name_sec": 0,
                                               "candidate_unique_cik": 0, "candidate_row_created_by_date": 0,
                                               "candidate_name": 0, "ambiguous_alias": 0,
                                               "ambiguous_candidate_cik": 0,
                                               "confirmed_by_multiple_evidence": 0,
                                               "confirmed_historical_ticker": 0,
                                               "corroborated_candidate": 0,
                                               "accredited_total": 0, "ambiguous_identity": 0})
        annual["quarter_dates"].append(day)
        annual["member_observations"] += len(symbols)
        for symbol in symbols:
            matching = [row for row in aliases if row[0] == symbol and row[3] <= day
                        and (row[4] is None or day < row[4])]
            owners = {row[1] for row in matching}
            valid = len(owners) == 1 and max((row[5] for row in matching), default=0) >= identity.MIN_CONFIDENCE
            if len(owners) > 1:
                annual["ambiguous_alias"] += 1
                ambiguous_examples.add(symbol)
            interval_matches = [row for row in intervals_by_symbol.get(symbol, [])
                                if row[2] <= day < row[3]]
            interval_confirmed = {row[1] for row in interval_matches
                                  if row[4] == "confirmed_by_multiple_evidence"}
            interval_historical = {row[1] for row in interval_matches
                                   if row[4] == "confirmed_historical_ticker"}
            interval_corroborated = {row[1] for row in interval_matches
                                    if row[4] == "corroborated_candidate"}
            interval_ambiguous = any(row[4] == "ambiguous" for row in interval_matches)
            alias_ciks = {row[2] for row in matching}
            supported = interval_confirmed | interval_historical | interval_corroborated
            conflict = (len(owners) > 1 or interval_ambiguous or len(supported) > 1 or
                        bool(supported and alias_ciks and supported != alias_ciks))
            if conflict:
                annual["ambiguous_identity"] += 1
                ambiguous_examples.add(symbol)
            elif interval_confirmed:
                annual["confirmed_by_multiple_evidence"] += 1
            elif interval_historical:
                annual["confirmed_historical_ticker"] += 1
            elif interval_corroborated:
                annual["corroborated_candidate"] += 1
            if not conflict and (valid or supported):
                annual["accredited_total"] += 1
            if valid:
                annual["date_valid_alias"] += 1
                annual["resolved_entity_id"] += 1
                cik = next((row[2] for row in matching if row[1] in owners), None)
                if cik:
                    annual["resolved_cik"] += 1
                    # A historical issuer name must come from a SEC filing
                    # available by that date, not today's entity name.
                    if any(row[0] == cik and row[2] <= day for row in sec_names):
                        annual["historical_name_sec"] += 1
            candidate = candidates_by_symbol.get(symbol)
            if candidate:
                if candidate["cik"]:
                    annual["candidate_unique_cik"] += 1
                    annual["candidate_row_created_by_date"] += candidate["row_created_by_date"]
                elif candidate["candidate_cik_count"] > 1:
                    annual["ambiguous_candidate_cik"] += 1
                    ambiguous_examples.add(symbol)
                annual["candidate_name"] += candidate["historical_name_candidate"]
    for annual in by_year.values():
        denominator = annual["member_observations"]
        annual["percent"] = {key: round(100 * annual[key] / denominator, 3) for key in (
            "resolved_cik", "resolved_entity_id", "date_valid_alias", "historical_name_sec",
            "candidate_unique_cik", "candidate_row_created_by_date", "candidate_name",
            "confirmed_by_multiple_evidence", "confirmed_historical_ticker", "corroborated_candidate",
            "accredited_total", "ambiguous_identity")}
    return {"membership_source_id": period.membership_source,
            "candidate_source_id": CANDIDATE_SOURCE,
            "window": [quarters[0], quarters[-1]], "unit": "quarter-end member observation",
            "candidate_warning": "lawcal CIK/name are reconstructed candidates, not verified ticker aliases; row creation date does not date the manually backfilled CIK",
            "by_year": by_year, "ambiguous_examples": sorted(ambiguous_examples)[:30]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=P2010.key, help="Historical period (2010-2015 or 2016-2025)")
    parser.add_argument("--output", type=Path, help="Write the offline report as JSON")
    parser.add_argument("--scan-instances", action="store_true", help="Check locally cached original SEC XBRL files")
    parser.add_argument("--fetch-candidate-instances", type=int,
                        help="Download up to N selected SEC XBRL covers of the period for candidate checks")
    parser.add_argument("--fetch-unresolved-instances", type=int,
                        help="Download up to N extra SEC covers only for unresolved dated identity intervals")
    parser.add_argument("--import-period-filings", action="store_true",
                        help="Index SEC bulk 10-K/10-Q submissions of the period's candidate CIKs")
    parser.add_argument("--import-nominated-filings", action="store_true",
                        help="Index cached SEC bulk filings for reviewed CIK nominations")
    parser.add_argument("--annual-report-symbols", type=int,
                        help="Download up to N 10-Ks for open intervals and store stated ticker symbols")
    parser.add_argument("--fetch-issuer-names", type=int,
                        help="Download up to N SEC issuer name histories for unresolved CIKs")
    parser.add_argument("--evidence-csv", type=Path, help="Save accepted SEC filing-day identity evidence")
    parser.add_argument("--import-evidence", action="store_true",
                        help="Idempotently archive SEC filing-day observations; does not create aliases")
    parser.add_argument("--build-intervals", action="store_true",
                        help="Build a separate, retrospective SEC-corroborated identity tier")
    parser.add_argument("--intervals-csv", type=Path,
                        help="Write interval status, dates and SEC provenance for review")
    args = parser.parse_args()
    period = get_period(args.period)
    fetch_summary = None
    if args.import_period_filings:
        print(json.dumps(import_period_filings(period)), flush=True)
    if args.import_nominated_filings:
        print(json.dumps(import_nominated_filings(period)), flush=True)
    if args.annual_report_symbols is not None:
        print(json.dumps(annual_report_symbol_evidence(args.annual_report_symbols, period)), flush=True)
    if args.fetch_candidate_instances is not None and args.fetch_unresolved_instances is not None:
        parser.error("Choose only one SEC instance download mode")
    if args.fetch_candidate_instances is not None or args.fetch_unresolved_instances is not None:
        fetch_summary = fetch_candidate_instances(
            args.fetch_candidate_instances if args.fetch_candidate_instances is not None else args.fetch_unresolved_instances,
            prioritize_unresolved=args.fetch_unresolved_instances is not None, period=period)
        print(json.dumps(fetch_summary), flush=True)
    if args.fetch_issuer_names is not None:
        name_fetch = fetch_issuer_name_histories(args.fetch_issuer_names, period)
        print(json.dumps(name_fetch), flush=True)
    if (args.evidence_csv or args.import_evidence) and not args.scan_instances:
        parser.error("--evidence-csv and --import-evidence require --scan-instances")
    if args.intervals_csv and not args.build_intervals:
        parser.error("--intervals-csv requires --build-intervals")
    evidence_summary = None
    if args.scan_instances:
        records, summary = scan_local_sec_instances(period)
        evidence_summary = summary
        if args.import_evidence:
            summary["imported_observations"] = historical_archive.import_filing_identity_evidence(records)
            with storage.get_connection() as conn:
                summary["stored_observations"] = conn.execute(
                    "SELECT COUNT(*) FROM entity_observations WHERE dataset='filing_identity'").fetchone()[0]
                summary["active_alias_rows"] = conn.execute("SELECT COUNT(*) FROM entity_aliases").fetchone()[0]
        if args.evidence_csv:
            args.evidence_csv.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(records).to_csv(args.evidence_csv, index=False)
    if args.build_intervals:
        intervals = build_evidence_intervals(period)
        historical_archive.replace_identity_intervals(period.identity_source, intervals)
        counts = {status: sum(row["status"] == status for row in intervals)
                  for status in ("confirmed_by_multiple_evidence", "confirmed_historical_ticker",
                                 "corroborated_candidate",
                                 "ambiguous", "unresolved")}
        if args.intervals_csv:
            args.intervals_csv.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([{**row, "source_refs": json.dumps(row["source_refs"], sort_keys=True)}
                          for row in intervals]).to_csv(args.intervals_csv, index=False)
    report = coverage_report(period)
    if fetch_summary:
        report["sec_candidate_download"] = fetch_summary
    if args.fetch_issuer_names is not None:
        report["sec_name_history_download"] = name_fetch
    if evidence_summary:
        report["sec_instance_evidence"] = evidence_summary
    if args.build_intervals:
        report["evidence_intervals"] = {"source_id": period.identity_source, "count": len(intervals),
                                        "statuses": counts,
                                        "note": "Retrospective corroboration, not a reviewed operational alias"}
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
