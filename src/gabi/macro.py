"""Contexto macroeconómico vía la API de FRED (Federal Reserve Economic Data).

A diferencia de yfinance y SEC EDGAR, FRED requiere una API key gratuita
(sin tarjeta, alta inmediata en https://fred.stlouisfed.org/docs/api/api_key.html).
Sin clave configurada, todo esto se degrada con elegancia: ensure_macro_data
devuelve ok=False y la página explica cómo conseguirla, en vez de fallar.

El objetivo no es meter macro en el score (eso ya es terreno de "qué factor
funciona bajo qué régimen", que requiere el backtesting que se decidió NO
construir todavía) sino tener a mano, al escribir una tesis en el Diario de
inversión, las relaciones causales típicas: tipos, inflación, curva, crédito..."""
from datetime import UTC, date, datetime

import pandas as pd
import requests

from . import config, storage
from .data_fetch import _classify_error

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# id FRED -> metadatos. units_param sigue la convención de la API de FRED
# ("lin" = sin transformar, "pc1" = variación % interanual).
SERIES = {
    "DGS10": {
        "label": "Treasury 10 años", "unit": "%", "units_param": "lin",
        "help": "Tipo de interés de la deuda pública de EE.UU. a 10 años. Referencia clave: cuando sube, "
                "penaliza especialmente a las empresas cuyo beneficio esperado está muy lejos en el futuro "
                "(crecimiento/tecnológicas), porque sus flujos de caja futuros valen menos al descontarlos.",
    },
    "DFII10": {
        "label": "Tipo real 10 años (TIPS)", "unit": "%", "units_param": "lin",
        "help": "Tipo de interés real (ya descontada la inflación esperada) a 10 años. Es, en muchos "
                "sentidos, más determinante para la valoración de acciones que el tipo nominal.",
    },
    "FEDFUNDS": {
        "label": "Tipo de interés oficial (Fed Funds)", "unit": "%", "units_param": "lin",
        "help": "Tipo de interés oficial de la Reserva Federal. Su subida encarece el crédito para "
                "empresas y consumidores; sus recortes suelen ser un catalizador alcista para renta variable.",
    },
    "T10Y2Y": {
        "label": "Curva de tipos (10A-2A)", "unit": "puntos", "units_param": "lin",
        "help": "Diferencia entre el tipo a 10 años y a 2 años. Cuando es negativa (curva invertida), "
                "ha anticipado históricamente recesiones en EE.UU. con antelación.",
    },
    "CPIAUCSL": {
        "label": "Inflación interanual (CPI)", "unit": "% interanual", "units_param": "pc1",
        "help": "Variación interanual del Índice de Precios al Consumo. Determina en gran medida la "
                "política de tipos de la Fed.",
    },
    "DTWEXBGS": {
        "label": "Índice del dólar (trade-weighted)", "unit": "índice", "units_param": "lin",
        "help": "Fortaleza del dólar frente a la cesta de divisas de sus principales socios comerciales. "
                "Un dólar fuerte suele perjudicar a las multinacionales con muchas ventas fuera de EE.UU.",
    },
    "BAMLH0A0HYM2": {
        "label": "Spread de crédito high yield", "unit": "puntos %", "units_param": "lin",
        "help": "Sobreprima que exige el mercado a la deuda corporativa de peor calidad frente a deuda "
                "pública. Se dispara cuando el mercado teme una recesión o impagos — termómetro de estrés "
                "de crédito.",
    },
    "WALCL": {
        "label": "Balance de la Fed (liquidez)", "unit": "millones $", "units_param": "lin",
        "help": "Tamaño del balance de la Reserva Federal. Un balance que crece inyecta liquidez al "
                "sistema; que se reduce (quantitative tightening) la retira.",
    },
    "SAHMREALTIME": {
        "label": "Regla de Sahm (indicador de recesión)", "unit": "puntos", "units_param": "lin",
        "help": "Indicador basado en el desempleo que históricamente señala el inicio de una recesión en "
                "EE.UU. cuando supera 0,5.",
    },
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS macro_series (
    series_id TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (series_id, date)
);
CREATE TABLE IF NOT EXISTS macro_meta (
    series_id TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL
);
"""


def fetch_series(series_id: str, api_key: str, units: str = "lin", limit: int = 260) -> list:
    """[(fecha, valor), ...] más reciente primero. Descarta observaciones sin
    dato ('.' es como FRED marca los huecos)."""
    params = {
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "sort_order": "desc", "limit": limit, "units": units,
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=20)
    if resp.status_code in (400, 401, 403):
        raise ValueError("FRED ha rechazado la petición (revisa que la API key sea correcta)")
    resp.raise_for_status()
    data = resp.json()
    observations = data.get("observations", [])
    return [(o["date"], float(o["value"])) for o in observations if o.get("value") not in (None, ".")]


def upsert_series(series_id: str, observations: list):
    fetched_at = datetime.now(UTC).isoformat()
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO macro_series (series_id, date, value) VALUES (?,?,?)",
            [(series_id, date, value) for date, value in observations],
        )
        conn.execute(
            "INSERT OR REPLACE INTO macro_meta (series_id, fetched_at) VALUES (?,?)",
            (series_id, fetched_at),
        )
        conn.commit()


def get_series_history(series_id: str) -> pd.DataFrame:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        df = pd.read_sql_query(
            "SELECT date, value FROM macro_series WHERE series_id = ? ORDER BY date ASC",
            conn, params=(series_id,),
        )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def get_all_fetched_at() -> dict:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute("SELECT series_id, fetched_at FROM macro_meta").fetchall()
    result = {}
    for series_id, fetched_at in rows:
        try:
            result[series_id] = datetime.fromisoformat(fetched_at)
        except Exception:
            result[series_id] = None
    return result


def ensure_macro_data(force: bool = False, max_age_hours: int = 24, progress_cb=None) -> dict:
    api_key = config.load_fred_key()
    if not api_key:
        return {"ok": False, "reason": "no_api_key", "refreshed": 0, "failed": {}}

    fetched_at = get_all_fetched_at()
    now = datetime.now(UTC)
    stale = [
        sid for sid in SERIES
        if force or fetched_at.get(sid) is None
        or (now - fetched_at[sid]).total_seconds() > max_age_hours * 3600
    ]
    failed = {}
    for i, sid in enumerate(stale):
        try:
            obs = fetch_series(sid, api_key, units=SERIES[sid]["units_param"])
            upsert_series(sid, obs)
        except Exception as exc:
            _, reason = _classify_error(exc, service="FRED")
            failed[sid] = reason
        if progress_cb:
            progress_cb(i + 1, len(stale), sid)
    storage.record_update_errors("fred_macro", failed)
    return {"ok": True, "refreshed": len(stale) - len(failed), "failed": failed}


# release_id de FRED (no de series) -- solo para series que representan una
# publicación programada y discreta (una vez al mes, en fecha conocida de
# antemano), no una serie que se actualiza a diario como DGS10 o FEDFUNDS:
# ahí "próxima actualización" no es un evento, es continuo.
RELEASE_IDS = {"CPIAUCSL": 10}
RELEASE_DATES_URL = "https://api.stlouisfed.org/fred/release/dates"


def _parse_next_release_date(payload: dict, today: date) -> date | None:
    """Pura: de la respuesta ya parseada (JSON) de /fred/release/dates, la
    primera fecha >= today -- FRED las devuelve ordenadas ascendente al
    pedir sort_order=asc, pero se ordena aquí también por si acaso."""
    dates = sorted(d["date"] for d in payload.get("release_dates", []))
    for d in dates:
        parsed = date.fromisoformat(d)
        if parsed >= today:
            return parsed
    return None


def fetch_next_release_date(series_id: str, api_key: str) -> date | None:
    """Próxima fecha de publicación programada (confirmada por la fuente
    oficial que FRED indexa, ej. BLS para CPI) -- None si `series_id` no
    tiene un release_id mapeado en RELEASE_IDS o si FRED no devuelve ninguna
    fecha futura."""
    release_id = RELEASE_IDS.get(series_id)
    if release_id is None:
        return None
    today = date.today()
    params = {
        "release_id": release_id, "api_key": api_key, "file_type": "json",
        "realtime_start": today.isoformat(), "sort_order": "asc",
        "include_release_dates_with_no_data": "true",
    }
    resp = requests.get(RELEASE_DATES_URL, params=params, timeout=20)
    resp.raise_for_status()
    return _parse_next_release_date(resp.json(), today)


def get_snapshot() -> pd.DataFrame:
    """Una fila por serie: último valor, fecha, variación frente a ~3 meses
    antes (aprox. 63 sesiones para series diarias, o últimas observaciones
    disponibles para series menos frecuentes)."""
    rows = []
    for series_id, meta in SERIES.items():
        history = get_series_history(series_id)
        if history.empty:
            rows.append({
                "series_id": series_id, "label": meta["label"], "unit": meta["unit"],
                "help": meta["help"], "latest_value": None, "latest_date": None, "change_3m": None,
            })
            continue
        latest_date = history.index[-1]
        latest_value = history["value"].iloc[-1]
        change_3m = None
        past = history[history.index <= latest_date - pd.Timedelta(days=90)]
        if not past.empty:
            past_value = past["value"].iloc[-1]
            change_3m = latest_value - past_value
        rows.append({
            "series_id": series_id, "label": meta["label"], "unit": meta["unit"],
            "help": meta["help"], "latest_value": latest_value,
            "latest_date": latest_date.date().isoformat(), "change_3m": change_3m,
        })
    return pd.DataFrame(rows)
