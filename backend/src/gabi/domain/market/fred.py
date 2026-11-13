"""Published FRED metadata and pure observation/revision policies."""

from datetime import date, datetime
from types import MappingProxyType

import pandas as pd

_SERIES = {
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

SERIES = MappingProxyType({key: MappingProxyType(value) for key, value in _SERIES.items()})
del _SERIES
RELEASE_IDS = MappingProxyType({"CPIAUCSL": 10})


def series_metadata() -> dict[str, dict]:
    return {key: {field: value[field] for field in ("label", "unit", "help")}
            for key, value in SERIES.items()}


def observations(payload: dict, *, include_missing: bool = False) -> list:
    return [(o["date"], None if o.get("value") in (None, ".") else float(o["value"]))
            for o in payload.get("observations", [])
            if include_missing or o.get("value") not in (None, ".")]


def refresh_window(old: pd.DataFrame, checkpoint: dict, now: datetime, full_refresh: bool) -> tuple[bool, str | None]:
    audit_due = not checkpoint.get("full_audited_at") or (
        now - datetime.fromisoformat(checkpoint["full_audited_at"])).total_seconds() >= 30 * 86400
    audit = full_refresh or audit_due
    start = "1776-07-04" if audit else (old.index.max() - pd.Timedelta(days=400)).date().isoformat() if not old.empty else None
    return audit, start


def parse_next_release_date(payload: dict, today: date) -> date | None:
    """Pura: de la respuesta ya parseada (JSON) de /fred/release/dates, la
    primera fecha >= today -- FRED las devuelve ordenadas ascendente al
    pedir sort_order=asc, pero se ordena aquí también por si acaso."""
    dates = sorted(d["date"] for d in payload.get("release_dates", []))
    for d in dates:
        parsed = date.fromisoformat(d)
        if parsed >= today:
            return parsed
    return None


def snapshot(series, histories) -> pd.DataFrame:
    """Una fila por serie: último valor, fecha, variación frente a ~3 meses
    antes (aprox. 63 sesiones para series diarias, o últimas observaciones
    disponibles para series menos frecuentes)."""
    rows = []
    for series_id, meta in series.items():
        history = histories[series_id]
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
