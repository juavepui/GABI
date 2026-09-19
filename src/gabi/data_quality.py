"""Salud y procedencia de los datos cacheados.

Cada fuente (precios, fundamentales Yahoo, SEC EDGAR, insider Form 4, FRED
macro) ya llevaba su propio `fetched_at`/`max_age_hours` por separado,
repartido en `storage.py`, `data_fetch.py`, `edgar.py`, `insider.py` y
`macro.py` -- no había un sitio único donde ver "qué calidad tienen mis
datos" (agregado, por universo) ni "de dónde procede este resultado"
(desglosado, por empresa). Este módulo solo agrega lo que ya existe: no
añade ninguna fuente, umbral ni llamada de red nueva -- todo se lee de la
caché local (SQLite/CSV), nunca dispara un fetch."""
from datetime import UTC, datetime

import pandas as pd

from . import config, edgar, insider, macro, storage

PRICE_STALE_DAYS = 5  # una acción sin nueva sesión guardada en 5 días naturales va con retraso


def _age_hours(fetched_at) -> float | None:
    """`fetched_at`: None, str ISO o datetime -- todas las fuentes de este
    proyecto guardan `datetime.now(UTC).isoformat()`, así que siempre trae
    su propio offset y nunca hace falta (ni sería correcto) asumir una
    zona horaria por nuestra cuenta."""
    if fetched_at is None:
        return None
    if isinstance(fetched_at, str):
        try:
            fetched_at = datetime.fromisoformat(fetched_at)
        except ValueError:
            return None
    return (datetime.now(UTC) - fetched_at).total_seconds() / 3600


def _fetched_at_summary(label: str, symbols: list, fetched_map: dict, threshold_hours: float) -> dict:
    n = len(symbols)
    raw_ages = [_age_hours(fetched_map.get(s)) for s in symbols]
    ages: list[float] = [a for a in raw_ages if a is not None]
    have = len(ages)
    fresh = sum(1 for a in ages if a <= threshold_hours)
    return {
        "label": label,
        "coverage": have / n if n else 0.0,
        "fresh": fresh / n if n else 0.0,
        "threshold_hours": threshold_hours,
        "oldest_hours": max(ages) if ages else None,
        "have": have, "fresh_n": fresh, "total": n,
    }


def universe_summary(symbols: list) -> dict:
    """Cobertura y frescura agregadas de todo el universo dado, fuente por
    fuente -- el "qué calidad tienen mis datos" de un vistazo. No dispara
    ningún fetch: si algo no está en caché, cuenta como cobertura 0, no
    como error."""
    n = len(symbols)
    if n == 0:
        return {"n_symbols": 0, "sources": {}, "cik": None, "macro": None}

    price_coverage = storage.get_price_coverage(symbols)
    has_price = 0
    fresh_price = 0
    oldest_price_date = None
    today = pd.Timestamp.now(tz="UTC").normalize()
    for s in symbols:
        row = price_coverage.get(s, {})
        if not row.get("adjusted_count"):
            continue
        has_price += 1
        latest = row.get("latest_adjusted_date")
        if not latest:
            continue
        age_days = (today - pd.Timestamp(latest, tz="UTC")).days
        if age_days <= PRICE_STALE_DAYS:
            fresh_price += 1
        if oldest_price_date is None or latest < oldest_price_date:
            oldest_price_date = latest

    sources = {
        "prices": {
            "label": "Precios (Yahoo)", "coverage": has_price / n, "fresh": fresh_price / n,
            "threshold_hours": PRICE_STALE_DAYS * 24, "oldest_hours": None, "oldest_date": oldest_price_date,
            "have": has_price, "fresh_n": fresh_price, "total": n,
        },
        "fundamentals": _fetched_at_summary(
            "Fundamentales (Yahoo)", symbols, storage.get_fundamentals_fetched_at(symbols),
            config.CACHE_MAX_AGE_HOURS),
        "edgar": _fetched_at_summary(
            "SEC EDGAR", symbols, edgar.get_edgar_fetched_at(symbols), config.EDGAR_CACHE_MAX_AGE_HOURS),
        "insider": _fetched_at_summary(
            "Insider (Form 4)", symbols, insider.get_insider_fetched_at(symbols), 24),
    }
    edgar_with_facts = edgar.get_symbols_with_facts(symbols)
    sources["edgar"]["with_facts_pct"] = len(edgar_with_facts & set(symbols)) / n

    cik_status = None
    if edgar.CIK_CACHE.exists():
        cik_map = edgar.get_cik_map()
        resolved = sum(1 for s in symbols if edgar.get_cik_for_symbol(s, cik_map=cik_map)[0])
        cik_status = {"resolved": resolved, "total": n, "pct": resolved / n}

    macro_fetched = macro.get_all_fetched_at()
    macro_status = None
    if macro_fetched:
        ages: list[float] = [a for dt in macro_fetched.values() if (a := _age_hours(dt)) is not None]
        macro_status = {
            "n_series": len(macro_fetched),
            "oldest_hours": max(ages) if ages else None,
            "threshold_hours": 24,
        }

    return {"n_symbols": n, "sources": sources, "cik": cik_status, "macro": macro_status}


def symbol_provenance(symbol: str) -> dict:
    """Para una empresa concreta: qué fuente y qué fecha respalda cada pieza
    de dato detrás de su score actual -- el "de dónde procede este
    resultado". Distingue `fetched_at` (cuándo lo descargó GABI) de la fecha
    real del propio informe (`latest_10k_date`/`latest_10q_date`) -- una
    descarga de ayer puede seguir respaldada por un 10-K de hace más de un
    año, si la empresa no ha presentado nada nuevo desde entonces."""
    price_row = storage.get_price_coverage([symbol]).get(symbol, {})
    price_age_hours = None
    latest_price_date = price_row.get("latest_adjusted_date")
    if latest_price_date:
        today = pd.Timestamp.now(tz="UTC").normalize()
        price_age_hours = (today - pd.Timestamp(latest_price_date, tz="UTC")).days * 24
    fundamentals = storage.get_fundamentals([symbol]).get(symbol)
    fundamentals_fetched_at = fundamentals["fetched_at"] if fundamentals else None
    edgar_fetched_at = edgar.get_edgar_fetched_at([symbol]).get(symbol)
    edgar_metrics = edgar.get_edgar_metrics([symbol]).get(symbol, {})
    edgar_has_facts = symbol in edgar.get_symbols_with_facts([symbol])
    insider_fetched_at = insider.get_insider_fetched_at([symbol]).get(symbol)

    return {
        "symbol": symbol,
        "prices": {
            "latest_date": latest_price_date,
            "adjusted_sessions": price_row.get("adjusted_count", 0),
            "age_hours": price_age_hours,
            "threshold_hours": PRICE_STALE_DAYS * 24,
        },
        "fundamentals": {
            "fetched_at": fundamentals_fetched_at,
            "age_hours": _age_hours(fundamentals_fetched_at),
            "threshold_hours": config.CACHE_MAX_AGE_HOURS,
        },
        "edgar": {
            "fetched_at": edgar_fetched_at,
            "age_hours": _age_hours(edgar_fetched_at),
            "threshold_hours": config.EDGAR_CACHE_MAX_AGE_HOURS,
            "has_facts": edgar_has_facts,
            "latest_10k_date": edgar_metrics.get("latest_10k_date"),
            "latest_10q_date": edgar_metrics.get("latest_10q_date"),
        },
        "insider": {
            "fetched_at": insider_fetched_at,
            "age_hours": _age_hours(insider_fetched_at),
            "threshold_hours": 24,
        },
    }
