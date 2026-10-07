"""Blind validation writes through the unchanged blind_validation module."""

from pathlib import Path

from gabi.application.errors import QueryError


class LegacyBlindWriter:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def _module(self):
        # blind_validation writes to the immutable project-root config, like the worker's legacy jobs.
        from gabi import blind_validation, config

        if config.DATA_DIR.resolve() != self.data_dir.resolve():
            raise QueryError("blind_unavailable", "Las validaciones ciegas no usan el directorio de datos de la API.", 503)
        return blind_validation

    def create(self, record: dict) -> int:
        return self._module().create_validation(record["name"], record["weights"], record["n_positions"],
                                                 record["rebalance_months"], record["start_date"],
                                                 record["unlock_date"])

    def break_seal(self, validation_id: int, reason: str) -> None:
        self._module().break_seal_early(validation_id, reason)


def run_blind_job(kind: str, data_dir: Path, plans_root: Path, options: dict) -> dict:
    """Worker only (its LegacyExecutor checks the data directory): rebalance, performance or export."""
    from datetime import date

    from gabi import blind_validation
    from gabi.application.research import blind
    from gabi.infrastructure.legacy.periodic import build_periodic_tasks
    from gabi.infrastructure.storage.blind import SqliteBlindStore
    from gabi.infrastructure.storage.blind_plans import FileBlindPlans

    queries = blind.BlindValidationQueries(SqliteBlindStore(data_dir), date.today, FileBlindPlans(plans_root))
    validation_id = options["validation_id"]
    if kind == "blind_rebalance":
        return blind.run_rebalance(queries, validation_id, build_periodic_tasks(data_dir).prices_fresh,
                                   blind_validation.record_rebalance)
    if kind == "blind_performance":
        return blind.run_performance(queries, validation_id, lambda vid, through: blind_validation.get_status(
            vid, reveal=True, as_of=through))
    return blind.run_export(queries, validation_id, blind_validation.export_to_research_lab)
