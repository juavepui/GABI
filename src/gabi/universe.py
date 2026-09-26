"""Obtiene el universo de empresas a analizar (constituyentes del S&P 500),
tanto el actual como (aproximado) el de una fecha pasada."""
from io import BytesIO

import pandas as pd
import requests

from . import config
from .historical_ticker_corrections import correct_symbols
from .membership_extension import apply_reviewed_extension

# Fuente principal: CSV plano mantenido en sincronía con la Wikipedia oficial.
# Se prefiere sobre el scraping directo de Wikipedia porque es más ligero
# (no requiere parsear HTML) y algunas redes bloquean/filtran wikipedia.org
# específicamente mientras dejan pasar github.com sin problema.
GITHUB_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/"
    "data/constituents.csv"
)
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Composición histórica día a día desde 1996 (una fila por fecha en la que
# cambió el índice, con la lista completa de tickers de ese momento —
# incluye tickers de empresas ya deslistadas/quebradas). Fuente comunitaria
# (MIT, sin garantías, mantenimiento discontinuado desde 2025-08-23): es la
# pieza que evita el sesgo de supervivencia al reconstruir un ranking
# histórico, pero no está tan verificada como Wikipedia/GitHub para el
# universo ACTUAL — por eso se usa solo para fechas pasadas, nunca para "hoy".
HISTORICAL_MEMBERSHIP_URL = (
    "https://raw.githubusercontent.com/hanshof/sp500_constituents/main/"
    "sp_500_historical_components.csv"
)
HISTORICAL_MEMBERSHIP_CACHE = config.DATA_DIR / "sp500_historical_membership.csv"


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": raw["Symbol"].astype(str).str.strip().str.replace(".", "-", regex=False),
        "name": raw["Security"].astype(str).str.strip(),
        "sector": raw["GICS Sector"].astype(str).str.strip(),
        "industry": raw["GICS Sub-Industry"].astype(str).str.strip(),
    })


def get_sp500_constituents(force_refresh: bool = False) -> pd.DataFrame:
    """Devuelve DataFrame[symbol, name, sector, industry].

    Se cachea en disco (data/sp500_constituents.csv) porque la lista cambia
    muy poco y así evitamos depender de la red en cada arranque.
    """
    cache_path = config.SP500_CACHE
    if not force_refresh and cache_path.exists():
        return pd.read_csv(cache_path)

    errors = []
    for fetch in (_fetch_from_github_csv, _fetch_from_wikipedia):
        try:
            df = fetch()
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache_path, index=False)
            return df
        except Exception as exc:  # noqa: BLE001 - probamos la siguiente fuente
            errors.append(f"{fetch.__name__}: {exc}")

    if cache_path.exists():
        return pd.read_csv(cache_path)
    raise RuntimeError(
        "No se pudo obtener la lista de constituyentes del S&P 500 de ninguna "
        "fuente y no hay caché local. Errores: " + " | ".join(errors)
    )


def _fetch_from_github_csv() -> pd.DataFrame:
    return _normalize(pd.read_csv(GITHUB_CSV_URL))


def _fetch_from_wikipedia() -> pd.DataFrame:
    tables = pd.read_html(WIKI_URL)
    return _normalize(tables[0])


def get_historical_membership(force_refresh: bool = False) -> pd.DataFrame:
    """DataFrame[date, tickers] — 'tickers' es un string con los símbolos de
    ese momento separados por comas. Se cachea en disco porque el archivo
    pesa varios MB y cambia poco; solo hace falta refrescarlo de vez en cuando."""
    if not force_refresh and HISTORICAL_MEMBERSHIP_CACHE.exists():
        history = pd.read_csv(HISTORICAL_MEMBERSHIP_CACHE, dtype={"date": str})
        return apply_reviewed_extension(history)
    resp = requests.get(HISTORICAL_MEMBERSHIP_URL, timeout=60)
    resp.raise_for_status()
    history = pd.read_csv(BytesIO(resp.content), dtype={"date": str})
    if HISTORICAL_MEMBERSHIP_CACHE.exists():
        cached = pd.read_csv(HISTORICAL_MEMBERSHIP_CACHE, dtype={"date": str})
        # A stale upstream download must not erase a newer local extension.
        history = pd.concat([history, cached[cached["date"] > history["date"].max()]], ignore_index=True)
    history = apply_reviewed_extension(history)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = HISTORICAL_MEMBERSHIP_CACHE.with_suffix(".csv.tmp")
    history.to_csv(temporary, index=False)
    temporary.replace(HISTORICAL_MEMBERSHIP_CACHE)
    return history


def get_sp500_constituents_asof(target_date: str) -> dict:
    """Reconstruye qué símbolos formaban el S&P 500 en target_date (YYYY-MM-DD).

    Devuelve los símbolos de una fecha cubierta por la fuente comunitaria.
    Fuera del horizonte conocido se rechaza la consulta: la composición actual
    introduciría sesgo de supervivencia. ``is_exact`` indica cobertura temporal,
    no certificación de la calidad de la fuente.
    """
    from . import historical_pit
    if historical_pit.covers(target_date):
        # 2010-2015: la composición sobre la que se acreditaron identidad y
        # precios (#26-#28); mezclar fuentes cambiaría las etiquetas.
        return historical_pit.universe(target_date)
    history = get_historical_membership()
    if history.empty:
        raise RuntimeError("No se pudo obtener el histórico de composición del S&P 500.")

    dates = sorted(history["date"].tolist())
    first_date, last_date = dates[0], dates[-1]

    if target_date < first_date:
        raise ValueError(
            f"No hay datos de composición del S&P 500 anteriores a {first_date} "
            f"(pediste {target_date})."
        )

    if target_date > last_date:
        raise ValueError(f"No hay composición histórica después de {last_date} "
                         f"(pediste {target_date}).")

    # A duplicated effective date with different lists leaves membership
    # unknown until the next unambiguous snapshot. Do not pick the last row.
    dated = history[history["date"] <= target_date]
    row = dated.iloc[-1]
    on_day = dated[dated["date"] == row["date"]]
    if len({frozenset(s.strip().replace(".", "-") for s in str(value).split(",") if s.strip())
            for value in on_day["tickers"]}) > 1:
        raise ValueError(f"Composición histórica contradictoria el {row['date']}; "
                         "se necesita otro snapshot sin conflicto.")
    reported = [s.strip() for s in str(row["tickers"]).split(",") if s.strip()]
    _, corrections = correct_symbols({s.replace(".", "-") for s in reported}, target_date)
    symbols = ["WLP" if corrections and symbol == "ANTM" else symbol for symbol in reported]
    return {
        "symbols": symbols,
        "source_date": row["date"],
        "is_exact": True,
        "label_corrections": corrections,
        "note": (f"Última composición registrada el {row['date']}, aplicable a {target_date}."
                 + (" ANTM se ha corregido a WLP según evidencia SEC/MIAX fechada." if corrections else "")),
    }
