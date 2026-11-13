"""Operation-scoped, bounded SEC file evidence; reads never download or write."""

import hashlib
import json
from collections import OrderedDict
from pathlib import Path

from gabi.application.research.historical_issuer_evidence import listing_life
from gabi.domain.market.identity import normalize_cik
from gabi.domain.research import issuer_evidence as rules


class HistoricalIssuerFiles:
    def __init__(self, frames: Path, submissions: Path, *, frame_specs=None, periods=None,
                 annual_periods=None, max_file_bytes=8 * 1024 * 1024, max_file_rows=100000,
                 max_pages=100, max_facts=250000, facts_bytes=256 * 1024 * 1024,
                 cache_bytes=8 * 1024 * 1024, max_issuers=1000, max_files=2000):
        if min(max_file_bytes, max_file_rows, max_pages, max_facts, facts_bytes, max_issuers, max_files) <= 0 or cache_bytes < 0:
            raise ValueError('Issuer evidence limits must be positive and cache nonnegative')
        self.frames, self.directory = Path(frames), Path(submissions)
        self.specs = rules.FRAME_SPECS if frame_specs is None else frame_specs
        self.periods = rules.PERIODS if periods is None else periods
        self.annual = rules.ANNUAL_PERIODS if annual_periods is None else annual_periods
        self.max_file_bytes, self.max_file_rows, self.max_pages = max_file_bytes, max_file_rows, max_pages
        self.max_facts, self.facts_bytes, self.cache_bytes = max_facts, facts_bytes, cache_bytes
        self.max_issuers, self.max_files = max_issuers, max_files
        self.cache: OrderedDict[tuple[Path, tuple[int, int, int]], bytes] = OrderedDict()
        self.cached_bytes = 0
        self._signature: tuple | None = None
        self._facts: dict[tuple[str, int | None], dict[str, list[dict]]] = {}
        self._fact_count, self._fact_bytes = 0, 0

    @staticmethod
    def _stamp(path):
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        return stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size

    def _raw(self, path):
        stamp = self._stamp(path)
        if stamp is None:
            return None
        if stamp[2] > self.max_file_bytes:
            raise ValueError('Issuer evidence file exceeds the byte limit')
        key = (path, stamp)
        if key in self.cache:
            self.cache.move_to_end(key)
            raw = self.cache[key]
        else:
            with path.open('rb') as stream:
                raw = stream.read(self.max_file_bytes + 1)
            if len(raw) > self.max_file_bytes or self._stamp(path) != stamp:
                raise ValueError('Issuer evidence file exceeds limits or changed during reading')
            for previous in [k for k in self.cache if k[0] == path]:
                self.cached_bytes -= len(self.cache.pop(previous))
            if len(raw) <= self.cache_bytes:
                while self.cache and self.cached_bytes + len(raw) > self.cache_bytes:
                    _, removed = self.cache.popitem(last=False)
                    self.cached_bytes -= len(removed)
                self.cache[key] = raw
                self.cached_bytes += len(raw)
        return raw

    def _json(self, path):
        raw = self._raw(path)
        return None if raw is None else json.loads(raw)

    def catalog(self):
        count = 0
        for kind, (taxonomy, tag, unit, instant) in self.specs.items():
            for period in self.annual if kind == 'dividend_payments' else self.periods:
                count += 1
                if count > self.max_files:
                    raise ValueError('Issuer frame catalog exceeds the file limit')
                suffix = 'I' if instant else ''
                url = rules.FRAME_URL.format(taxonomy=taxonomy, tag=tag, unit=unit, period=period + suffix)
                yield kind, url, self.frames / f'{taxonomy}_{tag}_{unit}_{period}{suffix}.json'

    def prepare(self, ciks: set[str], frame_year_max: int | None = None):
        if len(ciks) > self.max_issuers:
            raise ValueError('Requested issuer batch exceeds the issuer limit')
        self._prepare({normalize_cik(cik) for cik in ciks}, frame_year_max)

    def _prepare(self, ciks, frame_year_max):
        catalog = list(self.catalog())
        signature = tuple((str(path), self._stamp(path)) for _, _, path in catalog)
        if signature != self._signature:
            self._facts.clear()
            self._fact_count, self._fact_bytes = 0, 0
            self._signature = signature
        if ciks is not None:
            ciks = {cik for cik in ciks if (cik, frame_year_max) not in self._facts}
            if not ciks:
                return
        pending: dict[str, dict[str, list[dict]]] = {cik: {} for cik in ciks} if ciks is not None else {}
        count, size = self._fact_count, self._fact_bytes
        for kind, url, path in catalog:
            payload = self._json(path)
            if payload is None:
                continue
            rows = payload.get('data', [])
            if len(rows) > self.max_file_rows:
                raise ValueError('Issuer frame exceeds the row limit')
            if rows and frame_year_max is not None and int(str(payload.get('ccp'))[2:6]) > frame_year_max:
                continue
            for row in rows:
                cik = normalize_cik(row['cik'])
                if ciks is not None and cik not in ciks:
                    continue
                record = {**{key: row.get(key) for key in ('accn', 'start', 'end', 'val')},
                          'frame': payload.get('ccp'), 'source_url': url}
                count += 1
                size += len(json.dumps(record).encode()) + 1024
                if count > self.max_facts or size > self.facts_bytes:
                    raise ValueError('Requested issuer facts exceed the operation budget')
                pending.setdefault(cik, {}).setdefault(kind, []).append(record)
        if tuple((str(path), self._stamp(path)) for _, _, path in catalog) != signature:
            raise ValueError('Issuer frames changed during preparation; retry the operation')
        self._facts.update({(cik, frame_year_max): facts for cik, facts in pending.items()})
        self._fact_count, self._fact_bytes = count, size

    def issuer_facts(self, cik: str, frame_year_max: int | None = None):
        cik = normalize_cik(cik)
        # prepare() defines the frame snapshot for a batch. Reuse its issuer keys
        # without rescanning every file's metadata once per member and check.
        if (cik, frame_year_max) not in self._facts:
            self.prepare({cik}, frame_year_max)
        facts = self._facts[(cik, frame_year_max)]
        return {kind: sorted((dict(row) for row in facts.get(kind, [])), key=lambda row: row['end'])
                for kind in self.specs}

    def all_facts(self):
        # Explicit compatibility aggregate; auditors use prepare(ciks), never this method.
        self._facts.clear()
        self._fact_count, self._fact_bytes = 0, 0
        self._prepare(None, None)
        return {cik: {kind: [dict(row) for row in rows] for kind, rows in facts.items()}
                for (cik, _), facts in self._facts.items()}

    def _child(self, name):
        if not isinstance(name, str) or Path(name).name != name or name in ('', '.', '..'):
            raise ValueError('SEC submissions page must remain inside its directory')
        path = self.directory / name
        if path.resolve().parent != self.directory.resolve():
            raise ValueError('SEC submissions page must remain inside its directory')
        return path

    def submissions(self, cik: str):
        cik = normalize_cik(cik)
        payload = self._json(self._child(f'CIK{cik}.json'))
        if payload is None:
            return None
        if normalize_cik(payload['cik']) != cik:
            raise ValueError('SEC submissions issuer CIK mismatch')
        files = payload['filings'].get('files', [])
        if len(files) > self.max_pages:
            raise ValueError('SEC submissions exceed the page limit')
        pages = [payload['filings']['recent']]
        for page in files:
            extra = self._json(self._child(page['name']))
            if extra is not None:
                pages.append(extra)
            elif page.get('filingFrom', '9999') <= rules.FILINGS_TO and page.get('filingTo', '0000') >= rules.FILINGS_FROM:
                return None
        if sum(len(page['form']) for page in pages) > self.max_file_rows:
            raise ValueError('SEC submissions exceed the filing row limit')
        return payload, pages

    def official_name_chain(self, cik: str):
        cik = normalize_cik(cik)
        path = self._child(f'CIK{cik}.json')
        raw = self._raw(path)
        if raw is None:
            return None
        payload = json.loads(raw)
        if normalize_cik(payload['cik']) != cik:
            raise ValueError(f'SEC name history CIK mismatch: {path.name}')
        return dict(names=[payload.get('name', '')] + [row['name'] for row in payload.get('formerNames', [])],
                    source_url=f'https://data.sec.gov/submissions/CIK{cik}.json',
                    sha256=hashlib.sha256(raw).hexdigest())

    def listing_life(self, cik: str, floatless_before: str = rules.FLOATLESS_BEFORE,
                     frame_year_max: int | None = None):
        return listing_life(self, cik, floatless_before, frame_year_max)
