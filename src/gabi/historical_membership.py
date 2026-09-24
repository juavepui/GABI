"""Offline, source-attributed S&P 500 membership and dated ticker intervals.

These are reconstructed community snapshots, not certified index records or
issuer identities. A snapshot persists only inside its declared source horizon.
"""

import hashlib
import json
from bisect import bisect_right
from datetime import date, timedelta

import pandas as pd

from . import historical_archive, identity, storage, universe
from .historical_ticker_corrections import WLP_END, correct_symbols
from .membership_extension import apply_reviewed_extension

OPERATIONAL_SOURCE = "hanshof:local+reviewed-extension"
REFERENCE_SOURCE = "fja05680:a2430f2af0c79ddf0748e91de11bdeb1616ab5a7"


def _members(value: str) -> set[str]:
    result = {identity.normalize_symbol(symbol) for symbol in value.split(",") if symbol.strip()}
    if not result:
        raise ValueError("Empty historical membership snapshot")
    return result


def _snapshots(frame: pd.DataFrame) -> list[tuple[str, set[str]]]:
    rows = [(date.fromisoformat(str(row.date)).isoformat(), _members(str(row.tickers)))
            for row in frame.itertuples(index=False)]
    rows.sort(key=lambda row: row[0])
    by_date: dict[str, set[str]] = {}
    for day, symbols in rows:
        if day in by_date and by_date[day] != symbols:
            raise ValueError(f"Conflicting historical membership snapshots on {day}")
        by_date[day] = symbols
    return list(by_date.items())


def _segment(frame: pd.DataFrame, as_of: str, end_exclusive: str) -> tuple[pd.DataFrame, str, str]:
    """Conflicting same-day snapshots make coverage unknown until the next clean row."""
    grouped = frame.groupby("date", sort=True)["tickers"].apply(lambda values: {
        frozenset(_members(value)) for value in values})
    conflicts = sorted(day for day, variants in grouped.items() if len(variants) > 1)
    if as_of in conflicts:
        raise ValueError(f"Conflicting historical membership snapshots on {as_of}")
    before = [day for day in conflicts if day < as_of]
    after = [day for day in conflicts if day > as_of]
    last = before[-1] if before else None
    upcoming = after[0] if after else None
    selected = frame[frame["date"] > last] if last else frame
    if upcoming:
        selected = selected[selected["date"] < upcoming]
    boundary = min(end_exclusive, upcoming) if upcoming else end_exclusive
    return selected, boundary, "source_gap" if upcoming else "source_boundary"


def intervals(frame: pd.DataFrame, end_exclusive: str, *, boundary_reason: str = "source_boundary") -> list[dict]:
    """Turn snapshots into half-open intervals, retaining exits and reentries.

    A terminal interval ends at the source boundary, *not* an inferred exit.
    """
    boundary = date.fromisoformat(end_exclusive).isoformat()
    rows = _snapshots(frame)
    if not rows or rows[-1][0] >= boundary:
        raise ValueError("Snapshots must precede the source coverage boundary")
    active: dict[str, str] = {}
    result = []
    for day, members in rows:
        for symbol in sorted(active.keys() - members):
            result.append({"symbol": symbol, "valid_from": active.pop(symbol),
                           "valid_to": day, "end_reason": "exit"})
        for symbol in members - active.keys():
            active[symbol] = day
    result.extend({"symbol": symbol, "valid_from": start, "valid_to": boundary,
                   "end_reason": boundary_reason} for symbol, start in active.items())
    return sorted(result, key=lambda row: (row["symbol"], row["valid_from"]))


def _operational() -> tuple[pd.DataFrame, str]:
    # Read the cache directly so this query never triggers a download.
    if not universe.HISTORICAL_MEMBERSHIP_CACHE.exists():
        raise ValueError("Historical membership cache is not available locally")
    frame = apply_reviewed_extension(pd.read_csv(universe.HISTORICAL_MEMBERSHIP_CACHE, dtype={"date": str}))
    if frame.empty:
        raise ValueError("Historical membership cache is empty")
    end = (date.fromisoformat(str(frame["date"].max())) + timedelta(days=1)).isoformat()
    return frame, end


def _archive() -> tuple[pd.DataFrame, str]:
    with storage.get_connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='historical_sources'").fetchone():
            raise ValueError("The fja05680 reference archive has not been imported")
        source = conn.execute("SELECT metadata_json FROM historical_sources WHERE source_id=?",
                              (REFERENCE_SOURCE,)).fetchone()
        if source is None:
            raise ValueError("The fja05680 reference archive has not been imported")
        end = json.loads(source[0])["end_exclusive"]
        frame = pd.read_sql_query("SELECT date,tickers FROM historical_membership "
                                  "WHERE source_id=? ORDER BY date", conn, params=(REFERENCE_SOURCE,))
    return frame, end


def _identities(symbols: set[str], as_of: str) -> dict[str, dict]:
    """Keep reviewed aliases, SEC filing-day proof and research tiers distinct."""
    with storage.get_connection() as conn:
        identity.ensure_schema(conn)
        rows = conn.execute(
            "SELECT a.symbol,a.entity_id,e.cik,a.confidence FROM entity_aliases a "
            "JOIN entities e USING(entity_id) WHERE a.valid_from<=? "
            "AND (a.valid_to IS NULL OR a.valid_to>?)", (as_of, as_of)).fetchall()
        evidence = conn.execute("SELECT symbol,entity_id,payload_json,source FROM entity_observations "
                                "WHERE dataset='filing_identity'").fetchall()
        has_intervals = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                     "AND name='historical_identity_intervals'").fetchone()
        intervals = conn.execute("SELECT symbol,cik,status,source_id FROM historical_identity_intervals "
                                 "WHERE source_id=? AND valid_from<=? AND valid_to>?",
                                 (historical_archive.IDENTITY_INTERVAL_SOURCE, as_of, as_of)
                                 ).fetchall() if has_intervals else []
    candidates: dict[str, dict[str, float]] = {}
    ciks: dict[str, str | None] = {}
    for symbol, entity_id, cik, confidence in rows:
        if symbol in symbols:
            candidates.setdefault(symbol, {})[entity_id] = max(
                confidence, candidates.get(symbol, {}).get(entity_id, 0))
            ciks[entity_id] = cik
    proofs: dict[str, dict[str, tuple[dict, str]]] = {}
    for symbol, entity_id, payload_json, source in evidence:
        payload = json.loads(payload_json)
        if symbol in symbols and payload.get("filed_date") == as_of:
            proofs.setdefault(symbol, {})[entity_id] = (payload, source)
    corroborated: dict[str, dict[str, tuple[str, str]]] = {}
    blocked: set[str] = set()
    for symbol, cik, status, source in intervals:
        if symbol not in symbols:
            continue
        if status == "ambiguous":
            blocked.add(symbol)
        elif status in {"confirmed_by_multiple_evidence", "corroborated_candidate"}:
            corroborated.setdefault(symbol, {})[f"cik:{cik}"] = (status, source)
    result = {}
    for symbol in symbols:
        found = candidates.get(symbol, {})
        status = "ambiguous" if len(found) > 1 else "unresolved"
        entity_id = next(iter(found)) if len(found) == 1 and next(iter(found.values())) >= identity.MIN_CONFIDENCE else None
        if entity_id:
            status = "resolved"
        tier = "reviewed_alias" if entity_id else None
        interval = corroborated.get(symbol, {})
        if symbol in blocked or len(interval) > 1 or (interval and found and set(interval) != set(found)):
            entity_id, status, tier = None, "ambiguous", None
        elif len(interval) == 1 and status != "ambiguous":
            entity_id, status = next(iter(interval)), "resolved"
            tier = tier or interval[entity_id][0]
        proof = proofs.get(symbol, {})
        if proof and (len(proof) > 1 or status == "ambiguous" or
                      (found and set(found) != set(proof)) or
                      (interval and set(interval) != set(proof))):
            entity_id, status, tier = None, "ambiguous", None
        elif len(proof) == 1:
            entity_id, status = next(iter(proof)), "resolved"
            tier = "filing_day"
        filing = proof.get(entity_id) if entity_id else None
        result[symbol] = {"entity_id": entity_id,
                          "cik": (ciks.get(entity_id) or entity_id.removeprefix("cik:")) if entity_id else None,
                          "identity_status": status,
                          "identity_tier": tier,
                          "identity_confidence": (1.0 if filing else found.get(entity_id)
                                                  if tier == "reviewed_alias" else None),
                          "identity_source": (filing[1] if filing else interval[entity_id][1]
                                              if tier in {"confirmed_by_multiple_evidence",
                                                         "corroborated_candidate"} else None),
                          "historical_name": filing[0].get("historical_name") if filing else None}
    return result


def constituents_as_of(as_of: str, *, source_id: str = OPERATIONAL_SOURCE,
                       compare_reference: bool = True) -> dict:
    """Return dated membership without a current-universe fallback.

    Secondary-source disagreement is disclosed and never silently merged into
    the selected source. Membership confidence remains community_unverified.
    """
    day = date.fromisoformat(as_of).isoformat()
    if source_id == OPERATIONAL_SOURCE:
        frame, end = _operational()
    elif source_id == REFERENCE_SOURCE:
        frame, end = _archive()
    else:
        raise ValueError(f"Unknown membership source: {source_id}")
    source_end = end
    frame, end, boundary_reason = _segment(frame, day, end)
    rows = _snapshots(frame)
    dates = [item[0] for item in rows]
    index = bisect_right(dates, day) - 1
    if index < 0 or day >= end:
        first = dates[0] if dates else "none"
        raise ValueError(f"Date {day} outside {source_id} coverage [{first}, {end})")
    source_date, reported_symbols = rows[index]
    symbols, corrections = correct_symbols(reported_symbols, day)
    active_intervals = {row["symbol"]: row for row in intervals(frame, end, boundary_reason=boundary_reason)
                        if row["valid_from"] <= day < row["valid_to"]}
    corrected_intervals = {}
    for symbol in symbols:
        raw_symbol = "ANTM" if corrections and symbol == "WLP" else symbol
        interval = {**active_intervals[raw_symbol], "symbol": symbol}
        if corrections and symbol == "WLP":
            change = corrections[0]
            interval["valid_from"] = max(interval["valid_from"], change["valid_from"])
            if change["valid_to"] <= interval["valid_to"]:
                interval["valid_to"] = change["valid_to"]
                interval["end_reason"] = "ticker_change"
        elif symbol == "ANTM" and day >= WLP_END:
            interval["valid_from"] = max(interval["valid_from"], WLP_END)
        corrected_intervals[symbol] = interval
    identities = _identities(symbols, day)
    members = [{**corrected_intervals[symbol], **identities[symbol], "source_id": source_id,
                "membership_status": "community_unverified"} for symbol in sorted(symbols)]
    accredited_symbols = sorted(row["symbol"] for row in members if row["identity_status"] == "resolved")
    excluded_identity_symbols = sorted(row["symbol"] for row in members if row["identity_status"] != "resolved")
    comparison: dict[str, object] = {"status": "not_requested", "reference_source_id": REFERENCE_SOURCE}
    if compare_reference and source_id == OPERATIONAL_SOURCE:
        try:
            reference = historical_archive.get_membership(REFERENCE_SOURCE, day)
        except ValueError:
            comparison["status"] = "outside_reference_coverage_or_not_imported"
        else:
            other, _ = correct_symbols(set(reference["symbols"]), day)
            comparison.update(status="agree" if symbols == other else "conflict",
                              primary_only=sorted(symbols - other), reference_only=sorted(other - symbols),
                              reference_date=reference["source_date"])
    return {"as_of": day, "source_id": source_id, "source_date": source_date,
            "coverage_start": dates[0], "coverage_end_exclusive": end,
            "source_end_exclusive": source_end,
            "symbols": sorted(symbols), "members": members, "comparison": comparison,
            "accredited_symbols": accredited_symbols,
            "excluded_identity_symbols": excluded_identity_symbols,
            "label_corrections": corrections,
            "quality": "community_unverified"}


def overlap_report(start: str = "2010-01-01", end_exclusive: str = "2016-01-01") -> dict:
    """Compare both local sources at every recorded change date in the overlap."""
    date.fromisoformat(start)
    date.fromisoformat(end_exclusive)
    primary, primary_end = _operational()
    reference, reference_end = _archive()
    primary_conflicts = sorted(day for day, values in primary.groupby("date")["tickers"]
                               if len({frozenset(_members(value)) for value in values}) > 1)
    equivalent_duplicates = sorted(day for day, values in primary.groupby("date")["tickers"]
                                   if len(values) > 1 and len({frozenset(_members(value)) for value in values}) == 1)
    primary = primary[(primary["date"] < end_exclusive) & (primary["date"] < reference_end)]
    reference = reference[(reference["date"] < end_exclusive) & (reference["date"] < primary_end)]
    left, right = _snapshots(primary), _snapshots(reference)
    left_dates, right_dates = [row[0] for row in left], [row[0] for row in right]
    dates = sorted({day for day in left_dates + right_dates
                    if start <= day < min(end_exclusive, primary_end, reference_end)})
    by_year: dict[str, dict] = {}
    for day in dates:
        li, ri = bisect_right(left_dates, day) - 1, bisect_right(right_dates, day) - 1
        if li < 0 or ri < 0:
            continue
        diff = len(left[li][1] ^ right[ri][1])
        item = by_year.setdefault(day[:4], {"checkpoints": 0, "disagree_checkpoints": 0,
                                             "difference_sum": 0, "max_difference": 0})
        item["checkpoints"] += 1
        item["disagree_checkpoints"] += diff > 0
        item["difference_sum"] += diff
        item["max_difference"] = max(item["max_difference"], diff)
    for item in by_year.values():
        item["mean_difference"] = round(item.pop("difference_sum") / item["checkpoints"], 2)
    with universe.HISTORICAL_MEMBERSHIP_CACHE.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"primary_source_id": OPERATIONAL_SOURCE, "primary_cache_sha256": digest,
            "primary_coverage": [left_dates[0], primary_end],
            "primary_conflict_dates": primary_conflicts,
            "primary_equivalent_duplicate_dates": equivalent_duplicates,
            "reference_source_id": REFERENCE_SOURCE,
            "reference_coverage": [right_dates[0], reference_end],
            "comparison_window": [start, end_exclusive], "by_year": by_year}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Compare local historical S&P 500 membership sources; no network")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end-exclusive", default="2016-01-01")
    parser.add_argument("--date", help="Inspect one membership date instead of the annual overlap report")
    args = parser.parse_args()
    if args.date:
        result = constituents_as_of(args.date)
        output = {key: result[key] for key in ("as_of", "source_id", "source_date", "coverage_start",
                                                 "coverage_end_exclusive", "source_end_exclusive",
                                                 "comparison", "quality")}
        output["member_count"] = len(result["symbols"])
        output["resolved_identity_count"] = sum(row["identity_status"] == "resolved" for row in result["members"])
    else:
        output = overlap_report(args.start, args.end_exclusive)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
