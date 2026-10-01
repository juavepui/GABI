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
