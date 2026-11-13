"""Read-only SEC cover metadata and bounded XML files with exact byte hashes."""

import hashlib
from pathlib import Path

import pandas as pd
from lxml import etree

from gabi.application.research.identity_instances import InstanceResult
from gabi.domain.market.identity import normalize_cik
from gabi.domain.research import identity_instances as rules
from gabi.domain.research.historical_identity_audit import CANDIDATE_SOURCE
from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only


class InstanceBudgetExceeded(ValueError):
    """Abort a scan instead of treating budget exhaustion as rejected evidence."""


def decode_cover(root) -> rules.Cover:
    nodes = [node for node in root.iter() if isinstance(node.tag, str)]
    prefixes = tuple('{' + ns for ns in rules.DEI_NAMESPACES)
    contexts = {node.get('id'): node for node in nodes if node.tag.rsplit('}', 1)[-1] == 'context'}
    return rules.Cover(
        identifiers=frozenset(str(node.text or '').strip().zfill(10) for node in nodes
                              if node.tag.rsplit('}', 1)[-1] == 'identifier'),
        symbols=tuple((str(node.text or ''), node.get('contextRef')) for node in nodes
                      if node.tag.rsplit('}', 1)[-1] == 'TradingSymbol' and node.tag.startswith(prefixes)),
        members={key: [str(member.text or '') for member in node.iter()
                       if isinstance(member.tag, str) and member.tag.rsplit('}', 1)[-1] == 'explicitMember']
                 for key, node in contexts.items()},
        titles={node.get('contextRef'): str(node.text or '') for node in nodes
                if node.tag.rsplit('}', 1)[-1] == 'Security12bTitle'},
        names=frozenset(str(node.text or '').strip() for node in nodes
                        if node.tag.rsplit('}', 1)[-1] == 'EntityRegistrantName'
                        and node.tag.startswith(prefixes) and str(node.text or '').strip()))


class LocalIdentityInstances:
    def __init__(self, directory: Path, *, max_file_bytes: int = 32 * 1024**2,
                 max_scan_bytes: int = 16 * 1024**3, max_files: int = 50000, max_nodes: int = 250000):
        if min(max_file_bytes, max_scan_bytes, max_files, max_nodes) <= 0:
            raise ValueError('Invalid instance read budgets')
        self.directory = directory
        self.max_file_bytes, self.max_scan_bytes = max_file_bytes, max_scan_bytes
        self.max_files, self.max_nodes, self.read_bytes = max_files, max_nodes, 0

    def accessions(self, allowed: set[str]) -> list[str]:
        paths = []
        for accession in allowed:
            if not accession or Path(accession).name != accession or accession in {'.', '..'}:
                raise ValueError('Unsafe SEC accession path')
            path = self.directory / f'{accession}.xml'
            if path.exists():
                paths.append(path)
            if len(paths) > self.max_files:
                raise InstanceBudgetExceeded('Instance file budget exceeded')
        return [path.stem for path in sorted(paths)]

    def extract(self, path: Path, *, cik: str, common_stock_only: bool = False,
                multi_class: frozenset[str] = frozenset()) -> dict:
        cik = normalize_cik(cik)
        before = path.stat()
        if before.st_size > self.max_file_bytes or self.read_bytes + before.st_size > self.max_scan_bytes:
            raise InstanceBudgetExceeded('Instance byte budget exceeded')
        with path.open('rb') as source:
            content = source.read(before.st_size + 1)
        self.read_bytes += len(content)
        if len(content) > self.max_file_bytes or self.read_bytes > self.max_scan_bytes:
            raise InstanceBudgetExceeded('Instance byte budget exceeded')
        after = path.stat()
        if len(content) != before.st_size or (before.st_mtime_ns, before.st_ctime_ns, before.st_size) != (
                after.st_mtime_ns, after.st_ctime_ns, after.st_size):
            raise ValueError(f'Instance changed during read: {path.name}')
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        # libxml labels path-based parses with a file:/ URI on Windows. Keep
        # that label so legacy rejection grouping (split at ':') stays exact.
        base_url = 'file:/' + path.as_posix() if path.drive else str(path)
        root = etree.fromstring(content, parser, base_url=base_url)
        if sum(1 for _ in root.iter()) > self.max_nodes:
            raise InstanceBudgetExceeded('Instance node budget exceeded')
        return {**rules.ticker_proof(decode_cover(root), cik=cik, name=path.name,
                                   common_stock_only=common_stock_only, multi_class=multi_class),
                'sha256': hashlib.sha256(content).hexdigest()}

    def proof(self, accession: str, *, cik: str, common_stock_only: bool, multi_class: frozenset[str]) -> InstanceResult:
        path = self.directory / f'{accession}.xml'
        try:
            if path.resolve().parent != self.directory.resolve():
                raise ValueError('Unsafe SEC accession path')
            return InstanceResult(proof=self.extract(path, cik=cik, common_stock_only=common_stock_only,
                                                     multi_class=multi_class))
        except InstanceBudgetExceeded:
            raise
        except (OSError, ValueError, etree.XMLSyntaxError) as exc:
            return InstanceResult(rejection=str(exc).split(':', 1)[0])


class SqliteIdentityInstances:
    def __init__(self, path: Path, *, max_rows: int = 100000, max_bytes: int = 64 * 1024**2,
                 max_field_bytes: int = 1024**2):
        if min(max_rows, max_bytes, max_field_bytes) <= 0:
            raise ValueError('Invalid instance metadata budgets')
        self.path = path
        self.limits = dict(max_rows=max_rows, max_bytes=max_bytes, max_field_bytes=max_field_bytes)

    def scan_inputs(self, period):
        with read_only(self.path, self.limits['max_field_bytes']) as (db, tables):
            if 'sec_bulk_submissions' not in tables:
                raise ValueError('SEC bulk submissions have not been imported')
            filings = bounded_rows(db, 'SELECT accn,cik,filed_date,instance,name FROM sec_bulk_submissions '
                'WHERE filed_date>=? AND filed_date<? AND instance IS NOT NULL',
                (period.start, period.end_exclusive), **self.limits)
            candidates = bounded_rows(db, 'SELECT symbol,cik,name,date_added,date_removed,observed_from '
                'FROM historical_issuer_candidates WHERE source_id=?', (CANDIDATE_SOURCE,),
                **self.limits) if 'historical_issuer_candidates' in tables else []
            history = bounded_rows(db, 'SELECT date,tickers FROM historical_membership WHERE source_id=? ORDER BY date',
                (period.membership_source,), **self.limits) if 'historical_membership' in tables else []
            return {row[0]: row[1:] for row in filings}, candidates, pd.DataFrame(history, columns=['date', 'tickers'])
