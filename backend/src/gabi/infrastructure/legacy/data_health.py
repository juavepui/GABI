"""The old Calidad de los datos through the unchanged data_quality, identity and historical_archive modules."""

from pathlib import Path

import pandas as pd

from gabi.application.errors import QueryError


def _records(frame: pd.DataFrame) -> list[dict]:
    return [{str(key): (None if pd.isna(value) else value) if not isinstance(value, list) else value
             for key, value in row.items()} for row in frame.to_dict("records")]


class LegacyDataHealth:
    """Worker only: its LegacyExecutor checks that config.DATA_DIR is the API data directory."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def universe(self) -> list[dict]:
        from gabi import config

        if not config.SP500_CACHE.is_file():
            return []
        frame = pd.read_csv(config.SP500_CACHE, nrows=1001)
        names = frame["name"] if "name" in frame else pd.Series([None] * len(frame))
        return [{"symbol": str(symbol), "name": None if pd.isna(name) else str(name)}
                for symbol, name in zip(frame["symbol"], names, strict=True) if pd.notna(symbol)]

    def summary(self, symbols: list[str]) -> dict:
        from gabi import data_quality

        return data_quality.universe_summary(symbols)

    def recent_errors(self) -> list[dict]:
        from gabi import data_quality

        return _records(data_quality.recent_errors_summary())

    def provenance(self, symbol: str, as_of: str) -> dict:
        from gabi import data_quality

        return data_quality.symbol_provenance(symbol, as_of=as_of)

    def identity(self, symbol: str, as_of: str) -> dict:
        from gabi import identity, storage

        resolution = identity.resolve(symbol, as_of)
        with storage.get_connection() as conn:
            identity.ensure_schema(conn)
            candidates = pd.read_sql_query("SELECT * FROM entity_candidates WHERE symbol=? LIMIT 200", conn,
                                           params=(identity.normalize_symbol(symbol),))
        return {"resolution": resolution, "name_candidates": _records(candidates)}

    def identities(self, symbols: list[str], as_of: str) -> list[dict]:
        from gabi import identity

        return _records(identity.diagnostics(symbols, as_of))

    def archive_sources(self) -> list[dict]:
        from gabi import historical_archive

        return [{"source": row["Fuente"], "data": row["Datos"], "rows": int(row["Filas"]),
                 "first": row["Desde"], "last": row["Hasta"]} for row in historical_archive.source_summary()]

    def archive_quarterly(self) -> list[dict] | None:
        from gabi import config

        path = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / "coverage" / "quarterly.csv"
        if not path.is_file() or path.stat().st_size > 1_000_000:
            return None
        return _records(pd.read_csv(path))

    def archive_members(self, source: str, as_of: str) -> dict:
        from gabi import historical_archive

        try:
            return historical_archive.get_membership(source, as_of)
        except ValueError as error:
            raise QueryError("archive_unavailable", f"El archivo no tiene esa composición: {error}.", 404) from None

    def archive_prices(self, source: str, symbol: str, start: str, end: str) -> list[dict]:
        from gabi import historical_archive

        frame = historical_archive.get_prices(source, symbol, start, end)
        frame = frame.reset_index()[["date", "close", "adj_close", "volume"]]
        frame["date"] = frame["date"].dt.date.astype(str)
        return _records(frame)
