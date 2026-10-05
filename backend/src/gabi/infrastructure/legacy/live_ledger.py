"""Prospective ledger writes and the LIVE_FORWARD report through the unchanged legacy modules."""

from pathlib import Path

from gabi.application.errors import QueryError
from gabi.domain.research import live_performance
from gabi.domain.research.live_ledger import safe


def live_report(*, model_version: str | None = None, as_of: str | None = None) -> dict:
    """The LIVE_FORWARD paper portfolio over the ledger's events and the cached, issuer-attributed prices."""
    import pandas as pd

    from gabi import config, identity, live_ledger, storage
    from gabi.history_refresh import last_completed_session

    def history(symbol: str, payload: dict) -> pd.DataFrame:
        owner = payload.get("sources", {}).get(symbol, {}).get("entity_id")
        if owner:
            return identity.price_history(symbol, payload["market_date"], entity_id=owner)
        if identity.has_aliases(symbol):
            return pd.DataFrame()  # never attribute a recycled/migrated ticker to an unknown old issuer
        return storage.get_prices(symbol)

    now = live_ledger._now()
    return live_performance.report(live_ledger.events(), now, last_completed_session(now),
                                   storage.get_prices(config.BENCHMARK_SYMBOL), history,
                                   benchmark_symbol=config.BENCHMARK_SYMBOL, model_version=model_version, as_of=as_of)


def run_live_report(model_version: str) -> dict:
    """Worker only (its LegacyExecutor checks the data directory)."""
    return safe(live_report(model_version=model_version))


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
