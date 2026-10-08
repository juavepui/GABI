"""Ticker proofs and dated crosschecks over decoded SEC cover data; no I/O."""

import re
from bisect import bisect_right
from dataclasses import dataclass

from gabi.domain.market.identity import normalize_cik, normalize_symbol
from gabi.domain.research.historical_identity_audit import _candidate_map
from gabi.domain.research.ticker_corrections import correct_symbols

TICKER_RE = re.compile(r'[A-Z][A-Z0-9-]{0,11}\Z')
DEI_NAMESPACES = ('http://xbrl.sec.gov/dei/', 'http://xbrl.us/dei/')
COMMON_TITLE_RE = re.compile(r'common|capital stock|ordinary share|shares of beneficial interest', re.I)
NON_COMMON_RE = re.compile(r'preferred|preference|depositary|note|debenture|bond|warrant|right|unit|%', re.I)


@dataclass(frozen=True)
class Cover:
    identifiers: frozenset[str]
    symbols: tuple[tuple[str, str | None], ...]
    members: dict[str | None, list[str]]
    titles: dict[str | None, str]
    names: frozenset[str]


def common_stock_symbols(cover: Cover) -> set[str]:
    result = set()
    for text, context in cover.symbols:
        classes = [member for member in cover.members.get(context, [])
                   if 'Exchange' not in member and not member.startswith('exch:')]
        title = cover.titles.get(context, '')
        if title:
            common = bool(COMMON_TITLE_RE.search(title)) and not NON_COMMON_RE.search(title)
        else:
            common = not classes or all(re.search(r'Common(Stock|Class)', member) for member in classes)
        if common and text.strip():
            result.add(normalize_symbol(text.strip()))
    return result


def ticker_proof(cover: Cover, *, cik: str, name: str, common_stock_only: bool = False,
                 multi_class: frozenset[str] = frozenset()) -> dict:
    expected = normalize_cik(cik)
    if cover.identifiers != {expected}:
        raise ValueError(f'XBRL issuer CIK mismatch: {name}')
    symbols = {normalize_symbol(text.strip()) for text, _ in cover.symbols if text.strip()}
    if common_stock_only and len(symbols) > 1:
        symbols = common_stock_symbols(cover)
    classes = sorted(symbols) if len(symbols) > 1 and symbols <= multi_class else None
    if classes:
        symbols = {classes[0]}
    if len(symbols) != 1 or not TICKER_RE.fullmatch(next(iter(symbols))):
        raise ValueError(f'Missing or ambiguous SEC trading symbol: {name}')
    return dict(symbol=next(iter(symbols)), cik=expected,
                historical_name=next(iter(cover.names)) if len(cover.names) == 1 else None,
                **({'symbols': classes} if classes else {}))


def dated_proofs(proof: dict, accession: str, metadata: tuple, candidates: list,
                 snapshots: list, snapshot_dates: list[str]) -> list[dict]:
    cik, filed_date, instance, filing_name = metadata
    proof = dict(proof)
    proof['historical_name_source'] = 'dei' if proof['historical_name'] else None
    if not proof['historical_name'] and filing_name:
        proof['historical_name'] = filing_name
        proof['historical_name_source'] = 'sec_sub_index'
    proof.update(accession=accession, filed_date=filed_date,
                 source_url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/'
                            f"{accession.replace('-', '')}/{instance}")
    candidate = _candidate_map(candidates, filed_date).get(proof['symbol'])
    if candidate is None:
        proof['candidate_status'] = 'missing'
    elif candidate['candidate_cik_count'] != 1:
        proof['candidate_status'] = 'ambiguous'
    else:
        proof['candidate_status'] = 'agrees' if candidate['cik'] == proof['cik'] else 'conflicts'
    index = bisect_right(snapshot_dates, filed_date) - 1
    members = correct_symbols(snapshots[index][1], filed_date)[0] if index >= 0 else set()
    return [{**proof, 'symbol': symbol, 'member_in_fja': symbol in members}
            for symbol in proof.pop('symbols', [proof['symbol']])]


def summary(records: list[dict], failures: dict[str, int]) -> dict:
    statuses = {status: sum(row['candidate_status'] == status for row in records)
                for status in ('agrees', 'conflicts', 'ambiguous', 'missing')}
    return dict(filings_with_local_instance=len(records) + sum(failures.values()),
        ticker_proofs=len(records), distinct_ticker_cik_pairs=len({(row['symbol'], row['cik']) for row in records}),
        member_on_filing_date=sum(row['member_in_fja'] for row in records),
        historical_names=sum(row['historical_name'] is not None for row in records), candidate_crosscheck=statuses,
        conflict_examples=[{key: row[key] for key in ('symbol', 'cik', 'filed_date')} for row in records
                           if row['candidate_status'] in {'conflicts', 'ambiguous'}][:20], rejections=failures)
