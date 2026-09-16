"""Obtiene el universo de empresas a analizar (constituyentes del S&P 500)."""
import pandas as pd

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
