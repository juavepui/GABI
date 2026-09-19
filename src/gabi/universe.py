"""Obtiene el universo de empresas a analizar (constituyentes del S&P 500),
tanto el actual como (aproximado) el de una fecha pasada."""
import pandas as pd
import requests

from . import config

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
        "symbol": raw["Symbol"].astype(str).str.strip(),
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
        return pd.read_csv(HISTORICAL_MEMBERSHIP_CACHE, dtype={"date": str})
    resp = requests.get(HISTORICAL_MEMBERSHIP_URL, timeout=60)
    resp.raise_for_status()
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORICAL_MEMBERSHIP_CACHE.write_bytes(resp.content)
    return pd.read_csv(HISTORICAL_MEMBERSHIP_CACHE, dtype={"date": str})


def get_sp500_constituents_asof(target_date: str) -> dict:
    """Reconstruye qué símbolos formaban el S&P 500 en target_date (YYYY-MM-DD).

    Devuelve {"symbols": [...], "source_date": fecha real usada o None,
    "is_exact": bool, "note": texto explicativo}. is_exact=False cuando
    target_date cae fuera del rango cubierto por la fuente histórica y se ha
    usado el universo ACTUAL como mejor aproximación disponible — con el
    riesgo de sesgo de supervivencia que eso reintroduce si el índice cambió
    entre esa fecha y hoy.
    """
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
        current = get_sp500_constituents()
        return {
            "symbols": current["symbol"].tolist(),
            "source_date": None,
            "is_exact": False,
            "note": (
                f"El histórico gratuito de composición del índice solo llega hasta {last_date}. "
                f"Para {target_date} se ha usado el universo ACTUAL como mejor aproximación "
                "disponible — puede tener sesgo de supervivencia si hubo cambios en el índice "
                "desde entonces."
            ),
        }

    row = history[history["date"] <= target_date].iloc[-1]
    symbols = [s.strip() for s in str(row["tickers"]).split(",") if s.strip()]
    return {
        "symbols": symbols,
        "source_date": row["date"],
        "is_exact": True,
        "note": f"Composición registrada el {row['date']} (el cambio más reciente antes de {target_date}).",
    }
