"""Prospective ledger writes and the LIVE_FORWARD report through the unchanged legacy modules."""

from pathlib import Path

from gabi.application.errors import QueryError
from gabi.domain.research.live_ledger import safe


def run_live_report(model_version: str) -> dict:
    """Worker only (its LegacyExecutor checks the data directory): live_performance.report as Streamlit."""
    from gabi import live_performance

    return safe(live_performance.report(model_version=model_version))


class LegacyLiveLedger:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def save_evaluation(self, report: dict) -> dict:
        from gabi import config, live_ledger

        if config.DATA_DIR.resolve() != self.data_dir.resolve():
            raise QueryError("live_ledger_unavailable",
                             "El registro prospectivo no usa el directorio de datos de la API.", 503)
        try:
            return live_ledger.save_evaluation(report)
        except (OSError, ValueError) as exc:  # Busy writer lock or a ledger that is no longer intact.
            raise QueryError("live_ledger_busy", f"No se pudo guardar la evaluación: {exc}", 409) from exc
