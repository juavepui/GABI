"""The Streamlit «Actualizar datos» flow: explicit download job, failure summary and retry of the failed."""

import re
from collections.abc import Callable
from typing import Protocol

from gabi.application.errors import QueryError

SYMBOL = re.compile(r"[A-Z0-9^][A-Z0-9^-]{0,19}\Z")
MAX_RETRY_SYMBOLS = 1_000
MAX_FAILURES = 5_000
KEY_SOURCES = ("fred", "tiingo", "nasdaq", "fmp")


def normalize_data_update(options: dict | None) -> dict:
    options = dict(options or {})
    options.setdefault("universe_limit", None)
    options.setdefault("symbols", None)
    if set(options) != {"universe_limit", "force", "symbols"} or not isinstance(options["force"], bool):
        raise QueryError("invalid_job", "Parámetros de actualización no válidos.", 422)
    limit, symbols = options["universe_limit"], options["symbols"]
    if limit not in (None, 50, 150) or isinstance(limit, bool):
        raise QueryError("invalid_job", "El tamaño del universo debe ser 50, 150 o completo.", 422)
    if symbols is not None:
        if limit is not None or not isinstance(symbols, list) or not 1 <= len(symbols) <= MAX_RETRY_SYMBOLS:
            raise QueryError("invalid_job", "El reintento indica entre 1 y 1.000 símbolos, sin tamaño de universo.", 422)
        symbols = [str(symbol).strip().upper() for symbol in symbols]
        if not all(SYMBOL.fullmatch(symbol) for symbol in symbols) or len(set(symbols)) != len(symbols):
            raise QueryError("invalid_job", "Los símbolos del reintento no son válidos.", 422)
    return {"universe_limit": limit, "force": options["force"], "symbols": symbols}


def summarize_update(options: dict, symbols: list[str], result: dict) -> dict:
    """The success line and failures grouped by reason, most frequent first (as the old page)."""
    failures = [{"symbol": str(symbol), "stage": str(stage), "reason": str(reason)}
                for symbol, stages in sorted(result["failed"].items()) for stage, reason in stages.items()]
    if len(failures) > MAX_FAILURES:
        raise ValueError("La actualización supera el límite de fallos del resultado.")
    groups: dict[str, set[str]] = {}
    for failure in failures:
        groups.setdefault(failure["reason"], set()).add(failure["symbol"])
    return {"kind": "data_update", "universe_limit": options["universe_limit"], "force": options["force"],
            "retry": options["symbols"] is not None, "symbols": len(symbols),
            "price_refreshed": bool(result["price_refreshed"]),
            "fundamentals_refreshed": int(result["fundamentals_refreshed"]),
            "edgar_refreshed": int(result.get("edgar_refreshed", 0)),
            "failed_symbols": sorted(result["failed"]), "failures": failures,
            "failure_groups": [{"reason": reason, "symbols": sorted(names)} for reason, names in
                               sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))]}


class KeyWriter(Protocol):
    def save(self, source: str, key: str) -> None: ...


class KeyCommands:
    def __init__(self, writer: KeyWriter, configured: Callable[[], dict[str, bool]]):
        self.writer, self.configured = writer, configured

    def save(self, source: str, key: str) -> dict[str, bool]:
        """Store a local API key; the value is never returned or logged."""
        if source not in KEY_SOURCES:
            raise QueryError("invalid_key_source", "Fuente de clave desconocida.", 404)
        key = (key or "").strip()
        if not key or len(key) > 200 or any(character.isspace() for character in key):
            raise QueryError("invalid_key", "Pega una clave sin espacios de hasta 200 caracteres.", 422)
        self.writer.save(source, key)
        return self.configured()
