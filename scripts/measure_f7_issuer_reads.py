"""Measure captured global frame indexing against bounded requested-issuer preparation."""

import json
import sys
import tempfile
from pathlib import Path

from measure_f7_historical_writers import measure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/src'))


def main():
    from gabi.domain.research.issuer_evidence import FRAME_SPECS
    from gabi.infrastructure.storage.historical_issuer_evidence import HistoricalIssuerFiles

    reference = json.loads((ROOT / 'backend/tests/fixtures/historical_runners_migration.json').read_text(encoding='utf-8'))
    old = dict(__name__='gabi._captured_issuer_reads', __package__='gabi')
    exec(reference['historical_issuer_evidence'], old)
    periods = [f'CY{year}Q{quarter}' for year in range(2010, 2015) for quarter in range(1, 5)]
    annual = [f'CY{year}' for year in range(2010, 2015)]
    requested = {str(cik) for cik in range(1, 21)}
    with tempfile.TemporaryDirectory(prefix='gabi-issuer-reads-') as directory:
        frames, submissions = Path(directory) / 'frames', Path(directory) / 'submissions'
        frames.mkdir()
        old.update(FRAMES_DIR=frames, SUBMISSIONS_DIR=submissions, PERIODS=periods, ANNUAL_PERIODS=annual)
        for kind, (taxonomy, tag, unit, instant) in FRAME_SPECS.items():
            for period in annual if kind == 'dividend_payments' else periods:
                suffix = 'I' if instant else ''
                path = frames / f'{taxonomy}_{tag}_{unit}_{period}{suffix}.json'
                path.write_text(json.dumps(dict(ccp=period + suffix, data=[dict(
                    cik=cik, accn=f'{cik}-{period}', end=f'{period[2:6]}-03-31', val=100. * cik)
                    for cik in range(1, 201)])), encoding='utf-8')
        current = HistoricalIssuerFiles(frames, submissions, periods=periods, annual_periods=annual)

        def new():
            current.prepare(requested, 2013)
            return {cik: current.issuer_facts(cik, 2013) for cik in requested}

        previous, before = measure(lambda: {cik: old['issuer_facts'](cik, 2013) for cik in requested})
        actual, after = measure(new)
        assert actual == previous
        print(json.dumps(dict(available_issuers=200, requested_issuers=len(requested),
            frame_files=sum(1 for _ in frames.iterdir()),
            indexed_before=sum(len(rows) for facts in old['load_frames']().values() for rows in facts.values()),
            indexed_after=current._fact_count, cached_source_bytes=current.cached_bytes,
            before=before, after=after), indent=2))


if __name__ == '__main__':
    main()
