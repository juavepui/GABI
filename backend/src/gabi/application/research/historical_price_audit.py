"""Historical price audit with explicit membership, local data, calendar and issuer evidence."""
import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date, timedelta
from typing import Protocol

import pandas as pd

from gabi.application.research import historical_accreditation as accreditation
from gabi.application.research.historical_accreditation import HistoricalAuditWriter
from gabi.application.research.historical_audit_exports import HistoricalAuditExporter
from gabi.domain.market.sec_identity import ACCREDITED_IDENTITY_TIERS
from gabi.domain.research import issuer_evidence
from gabi.domain.research.historical_price_audit import (
    ACCEPTED_ADJUSTMENTS,
    ADJUSTED,
    _as_traded_yahoo,
    _level_checks,
    _next_rebalance,
    _nominated_price_symbol,
    _proof,
    _short_history,
    _split_ratios,
    archive_adjustment,
    assess_series,
    choose_source,
    continued_price_symbols,
    forward_coverage,
    same_traded_prices,
    series_identity,
    summarize,
)
from gabi.domain.research.periods import P2010, Period
from gabi.domain.research.price_accreditation import overlap_status


class PriceAuditSnapshot(Protocol):
    def series(self, symbol: str, start: str, end: str, *, archive: bool, source_id: str) -> pd.DataFrame: ...
    def splits(self, symbol: str) -> pd.DataFrame: ...
    def conflicts(self, source: str, symbol: str, start: str, end: str) -> int: ...
    def provenance(self, entity, symbol, source, start, end, producer) -> list[tuple]: ...
    def events(self, entity, start, end) -> list[tuple]: ...
    def boundaries(self, source, label, symbol, cik, day) -> tuple: ...
    def sic(self, cik, day) -> tuple | None: ...
    def identity_rows(self, source: str) -> list[tuple]: ...
    def price_values(self, symbol, start, end, *, archive, source_id) -> list[tuple]: ...

class PriceAuditReader(Protocol):
    def snapshot(self) -> AbstractContextManager[PriceAuditSnapshot]: ...

class IssuerEvidence(Protocol):
    def listing_life(self, cik: str, floatless_before: str, frame_year_max: int | None) -> dict | None: ...
    def issuer_facts(self, cik: str, frame_year_max: int | None) -> dict: ...

def audit(reader: PriceAuditReader, membership: Callable[[str], dict], evidence: IssuerEvidence, *,
          calendar, source_ids: dict[str, str], nominations: tuple[dict, ...], database_name: str,
          dates: list[str] | None = None, period: Period = P2010,
          prepare_evidence: Callable[[set[str], int | None], None] | None = None) -> tuple[pd.DataFrame, dict]:
    EXTRA_SOURCES = {name: source for name, source in source_ids.items() if name not in {"yahoo", "finsaber"}}
    rows = []
    dates = dates or [f"{year}-12-31" for year in period.years]
    quarters = period.quarters
    identity_source = period.identity_source
    series_cache: dict[tuple[str, bool | str], pd.DataFrame] = {}
    with reader.snapshot() as data:
        def load(name: str, symbol: str) -> pd.DataFrame:
            key: tuple[str, bool | str] = (symbol, name if name in EXTRA_SOURCES else name == "finsaber")
            if key not in series_cache:
                series_cache[key] = data.series(symbol, period.series_start,
                                            period.series_end if name == "yahoo" else period.archive_until(name),
                                            archive=name != "yahoo",
                                            source_id=source_ids[name])
            return series_cache[key]
        for as_of in dates:
            year = int(as_of[:4])
            constituents = membership(as_of)
            if prepare_evidence is not None:
                prepare_evidence({row['cik'] for row in constituents['members'] if row.get('cik')},
                                 period.frame_year_max)
            sessions = calendar.sessions[calendar.sessions <= pd.Timestamp(as_of)][-253:]
            start, end = sessions[0].date().isoformat(), sessions[-1].date().isoformat()
            horizon = _next_rebalance(as_of, quarters)
            for member in [*constituents["members"], {"symbol": "SPY", "identity_tier": "benchmark",
                                                      "cik": None}]:
                series_cache.clear()
                label = member["symbol"]
                cik = member.get("cik")
                symbols = {"yahoo": _nominated_price_symbol(label, cik, as_of, "yahoo", nominations),
                           "finsaber": _nominated_price_symbol(label, cik, as_of, "finsaber", nominations),
                           **{name: _nominated_price_symbol(label, cik, as_of, name, nominations) for name in EXTRA_SOURCES}}
                if period.price_symbol_fallback and cik:
                    symbols = continued_price_symbols(
                        label, symbols, evidence.listing_life(cik, *period.life_horizon),
                        lambda name, symbol: assess_series(load(name, symbol).loc[start:end], sessions)["complete"])
                for name, symbol in list(symbols.items())[:2]:
                    load(name, symbol)
                yahoo = series_cache[(symbols["yahoo"], False)].loc[start:end]
                archive = series_cache[(symbols["finsaber"], True)].loc[start:end] if label != "SPY" else \
                    pd.DataFrame(columns=["close", "adj_close"])
                yc, ac = assess_series(yahoo, sessions), assess_series(archive, sessions)
                if label == "SPY":
                    rows.append({"year": year, "as_of": as_of, "symbol": label, "expected_sessions": len(sessions),
                                 "yahoo_sessions": yc["sessions"], "selected_source": "yahoo" if yc["complete"] else None,
                                 "coverage_status": "complete" if yc["complete"] else "incomplete_prices",
                                 "price_attribution": "benchmark", "price_source_status": "benchmark"})
                    continue
                overlap, count, p99 = overlap_status(yahoo, archive, sessions)
                conflicts = data.conflicts(identity_source, label, start, end)
                issuer = None
                life = evidence.listing_life(cik, *period.life_horizon) if cik else None
                facts = evidence.issuer_facts(cik, period.frame_year_max) if cik else {}
                listing_refs: list[dict] = []
                yahoo_checks: list[dict] = []
                archive_checks: list[dict] = []
                adjustment_refs: list[dict] = []
                yahoo_adjustment_refs: list[dict] = []
                if cik:
                    reason, listing_refs = issuer_evidence.listing_checks(life, start, end)
                    until = issuer_evidence.level_horizon(life, end)
                    full_yahoo = series_cache[(symbols["yahoo"], False)].loc[start:until]
                    full_archive = series_cache[(symbols["finsaber"], True)].loc[start:until]
                    splits = data.splits(symbols["yahoo"])
                    yahoo_close = _as_traded_yahoo(full_yahoo, splits)
                    if overlap == "consistent_overlap":
                        # Same security on both sources: the archive close is as traded.
                        yahoo_close = full_archive["close"].astype(float).reindex(full_yahoo.index).fillna(yahoo_close)
                    archive_splits = _split_ratios(full_archive)
                    yahoo_splits = archive_splits if overlap == "consistent_overlap" else                         pd.Series(splits.ratio.astype(float).to_numpy(), index=pd.to_datetime(splits.date))
                    yahoo_checks = _level_checks(
                        facts, yahoo_close, start, end, until=until, splits=yahoo_splits) if yc["complete"] else []
                    archive_checks = _level_checks(
                        facts, full_archive["close"].astype(float), start, end, until=until,
                        splits=archive_splits) if ac["complete"] else []
                    adjustment = yahoo_adjustment = "not_assessed"
                    if ac["complete"] and (not yc["complete"] or overlap != "consistent_overlap"):
                        adjustment, adjustment_refs = archive_adjustment(archive, facts, start, end, yahoo, sessions)
                    if yc["complete"] and (overlap != "consistent_overlap" or
                                           issuer_evidence.level_status(yahoo_checks) == "missing"):
                        empty = pd.DataFrame(columns=["close", "adj_close"])
                        yahoo_adjustment, yahoo_adjustment_refs = archive_adjustment(
                            yahoo, facts, start, end, empty, sessions)
                    issuer = {"listing": reason,
                              "yahoo_level": series_identity(yahoo_checks, yahoo_adjustment, yahoo_adjustment_refs),
                              "archive_level": series_identity(archive_checks, adjustment, adjustment_refs),
                              "archive_adjustment": adjustment, "yahoo_adjustment": yahoo_adjustment,
                              "same_traded_prices": same_traded_prices(yahoo, archive, sessions)}
                proof = _proof(listing_refs, adjustment_refs, start, end) if listing_refs and \
                    issuer and not issuer["listing"] else None
                source, status = choose_source(member.get("identity_tier"), conflicts > 1, yc, ac, overlap,
                                               issuer=issuer, fallback_proof=proof)
                detail: dict = {}
                if source is None and status in {"incomplete_prices", "listing_starts_after_window"} and \
                        cik and member.get("identity_tier") and conflicts <= 1 and \
                        overlap not in {"divergent_overlap", "divergent_event"}:
                    splits = data.splits(symbols["yahoo"])
                    short_source, short_status, detail = _short_history(
                        member, sessions, yahoo, archive, yc, ac, life, facts, splits)
                    if short_source:
                        source, status = short_source, short_status
                    elif status == "incomplete_prices":
                        status = short_status
                extra_row: dict = {}
                extra_stats: dict[str, dict] = {}
                for name, extra_source in EXTRA_SOURCES.items():
                    extra_key = (symbols[name], name)
                    extra = load(name, symbols[name]).loc[start:end]
                    stats = assess_series(extra, sessions)
                    extra_stats[name] = stats
                    extra_row.update({f"{name}_sessions": stats["sessions"], f"{name}_first": stats["first"],
                                      f"{name}_last": stats["last"], f"{name}_level": None,
                                      f"{name}_adjustment": None})
                    if source is not None or not stats["complete"] or not cik or not issuer or \
                            issuer["listing"] or not member.get("identity_tier") or conflicts > 1:
                        continue
                    # Extra archived source, same controls as FINSABER. An overlap
                    # only counts against it when that other series is identified.
                    identified = {"passed", "fingerprint"}
                    e_overlap = overlap_status(yahoo, extra, sessions)[0] \
                        if issuer["yahoo_level"] in identified else "insufficient_overlap"
                    if e_overlap == "insufficient_overlap" and issuer["archive_level"] in identified and \
                            issuer["archive_adjustment"] in ACCEPTED_ADJUSTMENTS:
                        e_overlap = overlap_status(archive, extra, sessions)[0]
                    until = issuer_evidence.level_horizon(life, end)
                    full_extra = series_cache[extra_key].loc[start:until]
                    e_checks = _level_checks(
                        facts, full_extra["close"].astype(float), start, end, until=until,
                        splits=_split_ratios(full_extra))
                    e_adjustment, e_refs = archive_adjustment(extra, facts, start, end, yahoo, sessions)
                    e_issuer = {**issuer, "archive_level": series_identity(e_checks, e_adjustment, e_refs),
                                "archive_adjustment": e_adjustment}
                    e_source, e_status = choose_source(
                        member.get("identity_tier"), False, {"complete": False}, stats, e_overlap, issuer=e_issuer,
                        fallback_proof=_proof(listing_refs, e_refs, start, end), archive_name=name)
                    extra_row.update({f"{name}_level": e_issuer["archive_level"], f"{name}_adjustment": e_adjustment})
                    if e_source:
                        source, status = e_source, f"{name}_{e_status}"
                        archive_checks, adjustment_refs = e_checks, e_refs
                        detail = {}
                source_id = source_ids.get(source or "")
                source_symbol = symbols[source] if source else None
                source_stats = {"yahoo": yc, "finsaber": ac, **extra_stats}.get(source or "", ac)
                provenance = data.provenance(member.get("entity_id"), source_symbol, source_id,
                    source_stats["first"] or start, (date.fromisoformat(end) + timedelta(days=1)).isoformat(),
                    period.price_producer) if source_id else []
                accredited = len(provenance) == 1 and provenance[0][1] == ADJUSTED
                delisting = (life or {}).get("delisting")
                forward_exit = bool(delisting and as_of < delisting["filed"] <= horizon)
                events = data.events(member.get("entity_id"), as_of, horizon) if cik else []
                if not forward_exit:
                    forward = "continues_to_next_rebalance" if cik and life else "unknown"
                else:
                    forward = events[0][0] if len(events) == 1 else "terminal_event_missing"
                forward_until, forward_coverage_status = None, None
                if source and source_symbol:
                    source_frame = series_cache[(source_symbol, source if source in EXTRA_SOURCES
                                                 else source == "finsaber")]
                    identity_end, other_owner = data.boundaries(identity_source, label, source_symbol, cik, as_of)
                    boundary = min([day for day in (identity_end, other_owner) if day], default=None)
                    forward_until, forward_coverage_status = forward_coverage(
                        source_frame, calendar, source_stats["last"] or end, horizon, life,
                        archive=source != "yahoo",
                        identity_end=boundary if boundary and boundary < period.end_exclusive else None)
                sic_row = data.sic(cik, as_of) if cik else None
                floats = [row for row in facts.get("public_float", []) if row["end"] <= as_of and row["val"]]
                next_exit = bool(member.get("end_reason") == "exit" and
                                 member.get("valid_to", "9999-12-31") <=
                                 (date.fromisoformat(as_of) + timedelta(days=365)).isoformat())
                level_checks = detail.get("level_checks", yahoo_checks if source == "yahoo" else archive_checks)
                rows.append({"year": year, "as_of": as_of, "symbol": label, "cik": cik,
                             "entity_id": member.get("entity_id"),
                             "identity_tier": member.get("identity_tier"), "expected_sessions": len(sessions),
                             "yahoo_symbol": symbols["yahoo"], "finsaber_symbol": symbols["finsaber"],
                             "yahoo_sessions": yc["sessions"], "yahoo_first": yc["first"], "yahoo_last": yc["last"],
                             "finsaber_sessions": ac["sessions"], "finsaber_first": ac["first"],
                             "finsaber_last": ac["last"], "overlap_returns": count,
                             "overlap_status": overlap, "overlap_p99": p99,
                             "known_cik_conflict": conflicts > 1,
                             "sec_first_periodic": (life or {}).get("first_periodic"),
                             "sec_delisting": delisting["filed"] if delisting else None,
                             "listing_check": issuer["listing"] if issuer else None,
                             "yahoo_level": issuer["yahoo_level"] if issuer else None,
                             "finsaber_level": issuer["archive_level"] if issuer else None,
                             "finsaber_adjustment": issuer["archive_adjustment"] if issuer else None,
                             "yahoo_adjustment": issuer["yahoo_adjustment"] if issuer else None,
                             **extra_row,
                             "level_ratio": json.dumps([round(check["ratio"], 4) for check in level_checks]),
                             "selected_source": source, "source_symbol": source_symbol,
                             "coverage_status": status,
                             "history": "short_history" if status == "short_history" else
                             "full_window" if source else None,
                             "price_attribution": "accredited_entity_interval" if accredited
                             else "legacy_symbol_unattributed",
                             "price_source_status": provenance[0][2] if accredited else
                             "candidate_only" if source else "excluded",
                             "forward_status": forward,
                             "holding_covered_until": forward_until,
                             "holding_coverage": forward_coverage_status,
                             "identity_valid_from": member.get("valid_from"),
                             "identity_valid_to": member.get("valid_to"),
                             "membership_end_reason": member.get("end_reason"),
                             "sic": sic_row[0] if sic_row else None,
                             "public_float_usd": floats[-1]["val"] if floats else None,
                             "membership_exit_next_365d": next_exit,
                             "evidence_refs": {"listing": detail.get("listing_refs", listing_refs),
                                           "level": level_checks,
                                           "adjustment": detail.get("adjustment_refs", yahoo_adjustment_refs
                                                                    if source == "yahoo" else adjustment_refs)}})
    result = pd.DataFrame(rows)
    return result, summarize(result, database_name, source_ids["finsaber"], EXTRA_SOURCES)


def promote(reader, writer: HistoricalAuditWriter, frame: pd.DataFrame, *, period: Period,
            source_ids: dict[str, str], audit_url: str) -> dict:
    producer = period.price_producer
    candidates = frame[(frame.symbol != "SPY") & frame.selected_source.notna() & frame.cik.notna()]
    intervals: list[dict] = []
    ordered = candidates.assign(first=candidates.apply(lambda row: row[f"{row.selected_source}_first"], axis=1),
                                last=candidates.apply(lambda row: row[f"{row.selected_source}_last"], axis=1))
    for (symbol, cik, source), group in ordered.groupby(["source_symbol", "cik", "selected_source"]):
        for row in group.sort_values("first").itertuples(index=False):
            last = max(row.last, row.holding_covered_until) \
                if isinstance(row.holding_covered_until, str) else row.last
            end = (date.fromisoformat(last) + timedelta(days=1)).isoformat()
            current = intervals[-1] if intervals else None
            if current and (current["symbol"], current["cik"], current["source"]) == (symbol, cik, source) \
                    and row.first <= current["end"]:
                current["end"] = max(end, current["end"])
                current["rows"].append(row)
            else:
                intervals.append({"symbol": symbol, "cik": cik, "source": source, "start": row.first,
                                  "end": end, "rows": [row]})
    with reader.snapshot() as data:
        identity_rows = data.identity_rows(period.identity_source)
    removed = accreditation.remove_producer(writer, producer)
    accepted = {"tier_a": 0, "tier_b": 0}
    skipped: dict[str, int] = {}
    examples: dict[str, list[dict]] = {}
    for item in intervals:
        symbol, cik, label_rows = item["symbol"], item["cik"], item["rows"]
        refs: list[dict] = []
        for row in label_rows:
            for label, icik, valid_from, valid_to, status, source_refs in identity_rows:
                if label == row.symbol and icik == cik and valid_from <= row.as_of < valid_to and \
                        status in ACCREDITED_IDENTITY_TIERS:
                    refs.extend({**ref, "kind": "identity", "identity_tier": status, "index_label": label}
                                for ref in json.loads(source_refs)[:3] if ref.get("source_url"))
            # Findings computed by this audit itself (an unreconciled Yahoo
            # adjustment noted on an accepted Tier A window) cite the audit row.
            refs.extend(ref if ref.get("source_url") else {**ref, "source_url": audit_url, "window": row.as_of,
                                                           "derived_from": "historical_price_audit"}
                        for ref in row.evidence_refs["listing"] + row.evidence_refs["adjustment"])
            refs.extend({**check, "kind": "price_level"} for check in row.evidence_refs["level"])
        if not any(ref["kind"] == "identity" for ref in refs):
            skipped["missing_sec_identity_reference"] = skipped.get("missing_sec_identity_reference", 0) + 1
            continue
        source_id = source_ids[item["source"]]
        with reader.snapshot() as data:
            values = data.price_values(symbol, item['start'], item['end'],
                                       archive=item['source'] != 'yahoo', source_id=source_id)
        digest = hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()
        refs.append({"kind": "source", "producer": producer, "local_rows_sha256": digest, "rows": len(values),
                     "source_url": {"yahoo": f"https://finance.yahoo.com/quote/{symbol}/history/",
                                    "finsaber": "https://huggingface.co/datasets/finsaber-team/FINSABER-reproduce",
                                    "tiingo": f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices",
                                    "wiki": "https://data.nasdaq.com/databases/WIKIP"
                                    }[item["source"]],
                     "index_labels": sorted({row.symbol for row in label_rows}),
                     "note": {"yahoo": "legacy Yahoo cache", "finsaber": "FINSABER archived snapshot",
                              "tiingo": "Tiingo free-plan snapshot",
                              "wiki": "Nasdaq Data Link WIKI Prices, frozen 2018"}[item["source"]]})
        # Which audited windows this interval accredits and how far each one's
        # verified holding period reaches: a ranking on an audited date may
        # only use a series whose own window was accredited (#32).
        refs.append({"kind": "accredited_windows", "source_url": audit_url,
                     "windows": [{"as_of": row.as_of, "window_last": row.last,
                                  "holding_until": row.holding_covered_until
                                  if isinstance(row.holding_covered_until, str) else row.last}
                                 for row in label_rows]})
        if item["source"] != "yahoo":
            refs.append({"kind": "corporate_actions", "valid_from": item["start"], "valid_to": item["end"],
                         "source_url": next(ref["source_url"] for ref in refs if ref["kind"] == "last_trade"),
                         "basis": "SEC listing life, successions and split/dividend reconciliation per window"})
            first_dates = [ref["date"] for ref in refs if ref["kind"] == "first_trade" and ref.get("date")]
            last_dates = [ref["date"] for ref in refs if ref["kind"] == "last_trade" and ref.get("date")]
            refs = [ref for ref in refs if ref["kind"] not in {"first_trade", "last_trade"}] + [
                {**next(ref for ref in refs if ref["kind"] == "first_trade"), "date": min(first_dates)},
                {**next(ref for ref in refs if ref["kind"] == "last_trade"), "date": min(last_dates)}]
        tier = "tier_a" if item["source"] == "yahoo" else "tier_b"
        try:
            accreditation.record_series(writer, cik=cik, symbol=symbol, valid_from=item["start"], valid_to=item["end"],
                          source_id=source_id, adjustment_basis=ADJUSTED, status=tier, evidence=refs)
        except ValueError as exc:
            skipped[str(exc)] = skipped.get(str(exc), 0) + 1
            examples.setdefault(str(exc), []).append(
                {"symbol": symbol, "cik": cik, "source": item["source"], "valid_from": item["start"],
                 "missing_url_kinds": sorted({ref.get("kind") for ref in refs if not ref.get("source_url")})})
        else:
            accepted[tier] += 1
    return {"removed_previous": removed, "intervals_promoted": accepted, "skipped": skipped,
            "skipped_examples": {reason: rows[:10] for reason, rows in examples.items()}}

def record_terminal_events(writer: HistoricalAuditWriter, evidence: IssuerEvidence, document,
                           frame: pd.DataFrame, period: Period = P2010) -> dict:
    members = frame[(frame.symbol != "SPY") & frame.cik.notna() & frame.sec_delisting.notna()]
    quarters = period.quarters
    exits = members[members.apply(lambda row: row.as_of < row.sec_delisting <= _next_rebalance(row.as_of, quarters),
                                  axis=1)]
    counts: dict[str, int] = {}
    for (label, cik), _group in exits.groupby(["symbol", "cik"]):
        life = evidence.listing_life(cik, *period.life_horizon)
        if life is None or life["delisting"] is None:
            continue
        delisting = life["delisting"]
        references = [{"kind": "delisting", "source_url": life["source_url"], **delisting}]
        terms = {"cash": [], "stock": [], "election": False, "bankruptcy": False, "quotes": []}
        items: set[str] = set()
        event_date = delisting["filed"]
        for report in issuer_evidence.completion_reports(life, delisting["filed"])[:3]:
            url, text = document(cik, report)
            found = issuer_evidence.extract_terms(text)
            report_items = set(report["items"].split(","))
            if found["cash"] or found["stock"] or "1.03" in report_items:
                terms, items, event_date = found, report_items, report["filed"]
                references.append({"kind": "completion_8k", "source_url": url, "filed": report["filed"],
                                 "items": report["items"], "quotes": found["quotes"]})
                break
        event_type, status, economics = issuer_evidence.classify_terminal(items, terms)
        accreditation.record_terminal(writer, cik=cik, symbol=label, event_date=event_date, event_type=event_type,
                        status=status, evidence=references, **economics)
        counts[f"{event_type}:{status}"] = counts.get(f"{event_type}:{status}", 0) + 1
    return counts

def record_succession_events(reader, writer: HistoricalAuditWriter, evidence: IssuerEvidence, document,
                             frame: pd.DataFrame, *, period: Period, audit_url: str) -> dict:
    rows = frame[(frame.symbol != "SPY") & frame.cik.notna() &
                 frame.holding_coverage.isin(["succession", "identity_boundary", "terminal"])]
    counts: dict[str, int] = {}
    with reader.snapshot() as data:
        intervals = [row[:3] for row in data.identity_rows(period.identity_source)
                     if row[4] in ACCREDITED_IDENTITY_TIERS]
    for (label, cik), group in rows.groupby(["symbol", "cik"]):
        boundary = group.holding_covered_until.max()
        successors = [(start, other) for symbol, other, start in intervals
                      if symbol == label and other != cik and
                      0 <= (date.fromisoformat(start) - date.fromisoformat(boundary)).days <= 30]
        if not successors:
            continue
        start, successor = min(successors)
        life = evidence.listing_life(successor, *period.life_horizon)
        filings = [row for row in (life or {}).get("successions", []) if row.get("primary") and
                   abs((date.fromisoformat(row["filed"]) - date.fromisoformat(start)).days) <= 30]
        quote, url = None, None
        for filing in filings:
            url, text = document(successor, filing)
            quote = issuer_evidence.one_for_one_quote(text)
            if quote:
                break
        status = "terminal_return_confirmed" if quote else "terminal_return_unknown"
        references = [{"kind": "succession", "source_url": url or (life or {}).get("source_url", audit_url),
                     "successor_cik": successor, "successor_from": start, "quote": quote}]
        accreditation.replace_unknown_terminal(
            writer,
            after=group.as_of.min(), through=(date.fromisoformat(start) + timedelta(days=30)).isoformat(),
            cik=cik, symbol=label, event_date=start, event_type="succession", status=status,
            evidence=references, exchange_ratio=1.0 if quote else None,
            successor_symbol=label if quote else None)
        counts[status] = counts.get(status, 0) + 1
    return counts

def run(reader: PriceAuditReader, membership: Callable[[str], dict], evidence: IssuerEvidence, *,
        calendar, source_ids: dict[str, str], nominations: tuple[dict, ...], database_name: str,
        writer: HistoricalAuditWriter, document, exporter: HistoricalAuditExporter, csv, report,
        audit_url: str, period: Period = P2010, dates: list[str] | None = None,
        promote_prices: bool = False, terminal_events: bool = False,
        prepare_evidence: Callable[[set[str], int | None], None] | None = None) -> dict:
    parameters = dict(calendar=calendar, source_ids=source_ids, nominations=nominations,
                      database_name=database_name, dates=dates, period=period, prepare_evidence=prepare_evidence)
    frame, summary = audit(reader, membership, evidence, **parameters)
    terminal = record_terminal_events(writer, evidence, document, frame, period) if terminal_events else None
    if terminal is not None:
        terminal.update({f'succession:{key}': value for key, value in
                         record_succession_events(reader, writer, evidence, document, frame,
                                                   period=period, audit_url=audit_url).items()})
    promotion = promote(reader, writer, frame, period=period, source_ids=source_ids,
                        audit_url=audit_url) if promote_prices else None
    if terminal is not None or promotion is not None:
        frame, summary = audit(reader, membership, evidence, **parameters)
    if promotion is not None:
        summary['promotion'] = promotion
    if terminal is not None:
        summary['terminal_events'] = terminal
    exporter.price_audit(frame, summary, csv, report)
    return summary
