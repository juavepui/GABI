"""The Streamlit «Calidad de los datos» page as one explicit job: the legacy readers create schema while reading."""

import math
import re
from datetime import date, datetime
from typing import Protocol

from gabi.application.errors import QueryError

SYMBOL = re.compile(r"[A-Z0-9^][A-Z0-9^.-]{0,19}\Z")
SCOPES = ("universe", "company", "identities", "archive", "archive_members", "archive_prices")
# The archive explorer only opens 2010-2015: before 2010 stays closed by the #43 reservation (owner, 2026-10-01).
ARCHIVE_START, ARCHIVE_END = "2010-01-01", "2015-12-31"
MAX_UNIVERSE = 1_000
MAX_ERRORS = 500
MAX_ARCHIVE_ROWS = 2_000


class HealthSource(Protocol):
    def universe(self) -> list[dict]: ...
    def summary(self, symbols: list[str]) -> dict: ...
    def recent_errors(self) -> list[dict]: ...
    def provenance(self, symbol: str, as_of: str) -> dict: ...
    def identity(self, symbol: str, as_of: str) -> dict: ...
    def identities(self, symbols: list[str], as_of: str) -> list[dict]: ...
    def archive_sources(self) -> list[dict]: ...
    def archive_quarterly(self) -> list[dict] | None: ...
    def archive_members(self, source: str, as_of: str) -> dict: ...
    def archive_prices(self, source: str, symbol: str, start: str, end: str) -> list[dict]: ...


def _invalid(message: str) -> QueryError:
    return QueryError("invalid_job", message, 422)


def _date(value, low: str = "1990-01-01", high: str | None = None) -> str:
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        raise _invalid("La fecha no es válida.") from None
    if not low <= parsed.isoformat() <= (high or "2100-01-01"):
        raise _invalid(f"La fecha debe estar entre {low} y {high or 'hoy'}.")
    return parsed.isoformat()


def _symbol(value) -> str:
    symbol = str(value or "").strip().upper()
    if not SYMBOL.fullmatch(symbol):
        raise _invalid("El símbolo no es válido.")
    return symbol


def normalize_data_health(options: dict | None) -> dict:
    options = dict(options or {})
    scope = options.get("scope")
    fields = {"universe": {"scope"}, "archive": {"scope"}, "company": {"scope", "symbol", "as_of"},
              "identities": {"scope", "as_of"}, "archive_members": {"scope", "source", "as_of"},
              "archive_prices": {"scope", "source", "symbol"}}
    if scope not in SCOPES or set(options) != fields[scope]:
        raise _invalid("Parámetros de calidad de datos no válidos.")
    if "symbol" in options:
        options["symbol"] = _symbol(options["symbol"])
    if "source" in options:
        source = str(options["source"] or "")
        if not 1 <= len(source) <= 200 or any(character.isspace() for character in source):
            raise _invalid("La fuente del archivo no es válida.")
        options["source"] = source
    if scope == "archive_members":
        options["as_of"] = _date(options["as_of"], ARCHIVE_START, ARCHIVE_END)
    elif "as_of" in options:
        options["as_of"] = _date(options["as_of"])
    return {key: options[key] for key in sorted(options)}


def _clean(value):
    """JSON values for the artifact: dates as ISO text, numpy scalars as Python numbers, NaN as absent."""
    if isinstance(value, date | datetime):
        return value.isoformat()
    if hasattr(value, "item") and not isinstance(value, list | tuple | dict):  # numpy scalar
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(item) for item in value]
    return value


def _universe(source: HealthSource) -> list[dict]:
    universe = source.universe()
    if not universe:
        raise QueryError("universe_missing", "Universo ausente en caché: actualiza los datos primero.", 409)
    if len(universe) > MAX_UNIVERSE:
        raise QueryError("universe_too_large", "El universo supera el límite del diagnóstico.", 503)
    return universe


def build_data_health(options: dict, source: HealthSource, today: date) -> dict:
    scope = options["scope"]
    result: dict = {"kind": "data_health", "scope": scope}
    if options.get("as_of", "") > today.isoformat():
        raise _invalid("La fecha no puede ser posterior a hoy.")
    if scope == "universe":
        universe = _universe(source)
        errors = source.recent_errors()
        result |= {"universe": universe, "summary": source.summary([row["symbol"] for row in universe]),
                   "recent_errors": errors[:MAX_ERRORS], "recent_errors_total": len(errors)}
    elif scope == "company":
        errors = [row for row in source.recent_errors() if row.get("symbol") == options["symbol"]]
        result |= {"symbol": options["symbol"], "as_of": options["as_of"],
                   "provenance": source.provenance(options["symbol"], options["as_of"]),
                   "identity": source.identity(options["symbol"], options["as_of"]),
                   "recent_errors": errors[:MAX_ERRORS]}
    elif scope == "identities":
        rows = source.identities([row["symbol"] for row in _universe(source)], options["as_of"])
        result |= {"as_of": options["as_of"], "rows": rows,
                   "without_cik": sum(1 for row in rows if not row.get("cik"))}
    elif scope == "archive":
        quarterly = source.archive_quarterly()
        result |= {"sources": source.archive_sources(), "window": [ARCHIVE_START, ARCHIVE_END],
                   "quarterly": None if quarterly is None else
                   [row for row in quarterly if ARCHIVE_START <= str(row["date"]) <= ARCHIVE_END]}
    elif scope == "archive_members":
        members = source.archive_members(options["source"], options["as_of"])
        result |= {"source": options["source"], "as_of": options["as_of"], "source_date": members["source_date"],
                   "symbols": members["symbols"][:MAX_ARCHIVE_ROWS], "total": len(members["symbols"])}
    else:
        rows = source.archive_prices(options["source"], options["symbol"], ARCHIVE_START, "2016-01-01")
        result |= {"source": options["source"], "symbol": options["symbol"], "window": [ARCHIVE_START, ARCHIVE_END],
                   "rows": rows[:MAX_ARCHIVE_ROWS], "total": len(rows)}
    return _clean(result)
