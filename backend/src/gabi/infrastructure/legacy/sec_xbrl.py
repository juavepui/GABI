"""Small compatibility bridge for the existing attributed observation schema."""

from gabi import identity


def refresh_selected(data_dir, operation, symbols, **options):
    """Legacy universe selection remains pending; only synchronization is injected."""
    from gabi import config, edgar

    if config.DATA_DIR.resolve() != data_dir.resolve():
        raise ValueError("La selección SEC y el worker no usan el mismo directorio de datos.")
    return edgar.ensure_edgar_data(symbols, synchronize_one=operation, **options)


def ensure_schema(connection) -> None:
    identity.ensure_schema(connection)


def put_facts(connection, entity: str, symbol: str, rows: list[dict], source: str) -> None:
    identity.put_observations(connection, entity, "edgar_facts", symbol, rows, source)
