"""Explicit publication ports for historical audit artifacts."""

from typing import Protocol

import pandas as pd


class HistoricalAuditExporter(Protocol):
    def price_audit(self, frame: pd.DataFrame, summary: dict, csv: str, report: str) -> None: ...
    def evidence(self, records: list[dict], csv: str) -> None: ...
    def intervals(self, records: list[dict], csv: str) -> None: ...
    def report(self, report: dict, path: str) -> None: ...


def export_evidence(exporter: HistoricalAuditExporter, records: list[dict], path: str) -> None:
    exporter.evidence(records, path)


def export_intervals(exporter: HistoricalAuditExporter, records: list[dict], path: str) -> None:
    exporter.intervals(records, path)


def export_report(exporter: HistoricalAuditExporter, report: dict, path: str) -> None:
    exporter.report(report, path)
