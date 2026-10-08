"""Interpret rounded SEC SUB/NUM records without inventing exact contexts."""

import math
from datetime import datetime

import pandas as pd


def date8(value: str) -> str:
    return datetime.strptime(value, '%Y%m%d').date().isoformat()


def submissions(frame: pd.DataFrame, ciks: set[str], source_url: str) -> list[tuple]:
    frame = frame.copy()
    frame['cik'] = frame['cik'].str.zfill(10)
    selected = frame[frame.cik.isin(ciks) & frame.form.isin(['10-K', '10-Q', '10-K/A', '10-Q/A'])]
    return [(r.adsh, r.cik, r.name, r.sic, r.form, date8(r.filed), r.accepted,
             r.fy, r.fp, r.instance, source_url) for r in selected.itertuples(index=False)]


def facts(frame: pd.DataFrame, accessions: set[str], tracked: set[str], shares: set[str]) -> tuple[list[tuple], int, int]:
    selected = frame[frame.adsh.isin(accessions) & frame.tag.isin(tracked)
                     & frame.version.str.match(r'^(us-gaap|dei)/')]
    consolidated = (selected.coreg == '') & (selected.get('segments', '') == '')
    excluded = int((~consolidated).sum())
    records = []
    invalid = 0
    for r in selected[consolidated].itertuples(index=False):
        try:
            val, qtrs = float(r.value), int(r.qtrs)
            if not math.isfinite(val) or qtrs < 0 or r.uom != ('shares' if r.tag in shares else 'USD'):
                raise ValueError('invalid value or unit')
            records.append((r.adsh, r.tag, r.version, date8(r.ddate), qtrs, r.uom, val))
        except ValueError:
            invalid += 1
    return records, excluded, invalid
