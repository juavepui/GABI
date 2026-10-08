"""Retrospective identity tiers over explicit local evidence; no I/O."""
import json
import re
import unicodedata
from bisect import bisect_right
from datetime import date, timedelta

import pandas as pd

from gabi.domain.market import identity
from gabi.domain.research import historical_membership
from gabi.domain.research.periods import P2010, Period
from gabi.domain.research.ticker_corrections import WLP_END, apply_nominations, correct_symbols

CANDIDATE_SOURCE = "lawcal:2e59b86998a119d68e377f9f98aa7a816cfc7d5b"
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


def build_evidence_intervals(history, candidates, proofs, submissions, official_names, lives, nominations, period: Period = P2010) -> list[dict]:
    """Corroborate candidate/member intervals with dated SEC primary evidence.

    The resulting tier is retrospective research evidence. Membership and
    community candidate dates bound it, but are not themselves SEC-verified
    ticker-change dates. It is deliberately separate from entity_aliases.
    """
    memberships, by_symbol = member_candidates(history, candidates, nominations, period)
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
                life = lives.get(cik)
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


def coverage_report(history, candidates, aliases, intervals, sec_names, period: Period = P2010) -> dict:
    """Measure quarterly member observations, retaining candidate/verified tiers."""
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



def member_candidates(history, candidates, nominations, period: Period):
    snapshots = historical_membership._snapshots(history)
    if not snapshots or snapshots[0][0] > period.start:
        raise ValueError("Historical membership snapshots missing")
    corrected = [(day, correct_symbols(symbols, day)[0]) for day, symbols in snapshots]
    # The source often keeps the later ANTM label retroactively; insert the
    # independently documented ticker-change date into the temporal series.
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
    by_symbol = apply_nominations(by_symbol, nominations)
    return memberships, by_symbol
