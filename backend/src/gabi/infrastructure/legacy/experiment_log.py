"""Research Lab writes through the unchanged research_lab logger (commit, dependencies, environment)."""

from pathlib import Path

from gabi.application.errors import QueryError


class LegacyExperimentLog:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def _research_lab(self):
        # research_lab writes to the immutable project-root config, like the worker's legacy jobs.
        from gabi import config, research_lab

        if config.DATA_DIR.resolve() != self.data_dir.resolve():
            raise QueryError("experiments_unavailable",
                             "El registro de experimentos no usa el directorio de datos de la API.", 503)
        return research_lab

    def log(self, record: dict) -> int:
        record = dict(record)
        return self._research_lab().log_experiment(
            record.pop("model_id"), record.pop("stage"), record.pop("hypothesis_registered"), **record)

    def delete(self, experiment_id: int) -> bool:
        return self._research_lab().delete_experiment(experiment_id)
