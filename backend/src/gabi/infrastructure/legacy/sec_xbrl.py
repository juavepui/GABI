"""Small compatibility bridge for the existing attributed observation schema."""

from gabi import identity


def ensure_schema(connection) -> None:
    identity.ensure_schema(connection)


def put_facts(connection, entity: str, symbol: str, rows: list[dict], source: str) -> None:
    identity.put_observations(connection, entity, "edgar_facts", symbol, rows, source)
