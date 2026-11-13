"""Explicit CSV/JSON audit publication with replacement of each complete artifact."""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd


def _replace(path: str | Path, write) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
            write(stream)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class HistoricalAuditFiles:
    def price_audit(self, frame: pd.DataFrame, summary: dict, csv: str | Path, report: str | Path) -> None:
        _replace(csv, lambda stream: frame.drop(columns=['evidence_refs'], errors='ignore').to_csv(stream, index=False))
        self.report(summary, report)

    def evidence(self, records: list[dict], csv: str | Path) -> None:
        _replace(csv, lambda stream: pd.DataFrame(records).to_csv(stream, index=False))

    def intervals(self, records: list[dict], csv: str | Path) -> None:
        frame = pd.DataFrame([{**row, 'source_refs': json.dumps(row['source_refs'], sort_keys=True)} for row in records])
        _replace(csv, lambda stream: frame.to_csv(stream, index=False))

    def report(self, report: dict, path: str | Path) -> None:
        payload = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        # Match Path.write_text's newline translation on the host platform.
        _replace(path, lambda stream: stream.write(payload.replace('\n', os.linesep)))
