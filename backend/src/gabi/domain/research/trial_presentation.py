"""Readable rows for a published trial: its configuration and its published result, never recomputed."""

import math

MAX_ROWS = 300
MAX_DEPTH = 5

LABELS = {
    "cagr_net": "CAGR neto", "cagr": "CAGR", "drawdown": "Caída máxima", "max_drawdown": "Caída máxima",
    "es_95": "Pérdida esperada 95 %", "es_99": "Pérdida esperada 99 %", "turnover": "Rotación",
    "commissions": "Comisiones", "spread_cost": "Coste de spread", "cost_total": "Coste total",
    "initial_value": "Valor inicial", "final_value": "Valor final", "n_periods": "Periodos", "n_obs": "Observaciones",
    "n": "Observaciones", "beta_spy": "Beta frente a SPY", "psr": "PSR (prob. Sharpe > 0)",
    "sharpe_anualizado": "Sharpe anualizado", "sharpe": "Sharpe", "skew": "Asimetría", "kurtosis": "Curtosis",
    "ic": "Coeficiente de información", "mean": "Media", "se_hac": "Error estándar HAC", "p": "p-valor",
    "p_holm": "p-valor (Holm)", "p_known_search_guard": "p-valor con búsqueda conocida", "status": "Estado",
    "mean_excess": "Exceso medio por periodo", "family_lower_bound": "Cota inferior de la familia",
    "known_search_lower_bound": "Cota inferior con búsqueda conocida", "windows": "Ventanas", "costs": "Costes",
    "base": "Base", "stress": "Estrés", "start": "Inicio", "end": "Fin", "months": "Meses entre rebalanceos",
    "top_n": "Posiciones", "buffer_multiplier": "Multiplicador de colchón", "cost_bps": "Coste (pb por lado)",
    "sma_filter": "Filtro SMA200", "role": "Papel", "evidence": "Evidencia", "max_symbols": "Empresas por fecha",
    "seed": "Semilla", "weights": "Pesos", "value": "Value", "quality": "Quality", "momentum": "Momentum",
    "risk": "Risk", "engine": "Motor", "trial": "Ensayo", "common_configuration": "Configuración común",
    "periods": "Periodos", "universe": "Universo", "trial_id": "Identificador",
}
FRACTIONS = {"cagr_net", "cagr", "drawdown", "max_drawdown", "es_95", "es_99", "mean_excess", "family_lower_bound",
             "known_search_lower_bound", "psr", "value", "quality", "momentum", "risk"}
USD = {"commissions", "spread_cost", "cost_total", "initial_value", "final_value"}
COUNTS = {"n", "n_obs", "n_periods", "periods", "top_n", "max_symbols", "seed", "months"}
HIDDEN = {"common_inputs_ref", "sha256", "configuration_sha256"}


def label(key: str) -> str:
    return LABELS.get(key, key.replace("_", " "))


def unit(key: str, value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "text"
    if key in FRACTIONS:
        return "fraction"
    if key in USD:
        return "USD"
    if key in COUNTS:
        return "count"
    return "number"


def rows(value: object, path: tuple[str, ...] = ()) -> list[dict]:
    """Depth-first rows of scalars with a readable path; lists of scalars are joined, long ones summarised."""
    out: list[dict] = []

    def walk(item: object, trail: tuple[str, ...]) -> None:
        if len(out) >= MAX_ROWS:
            return
        key = trail[-1] if trail else ""
        if isinstance(item, dict):
            if len(trail) >= MAX_DEPTH:
                return
            for child, nested in item.items():
                if str(child) not in HIDDEN and not str(child).endswith("_sha256"):
                    walk(nested, (*trail, str(child)))
            return
        if isinstance(item, list):
            scalars = [entry for entry in item if not isinstance(entry, dict | list)]
            if len(scalars) == len(item) and len(item) <= 12:
                out.append({"path": " › ".join(label(part) for part in trail), "key": key,
                            "value": ", ".join(str(entry) for entry in item) or "—", "unit": "text"})
            elif all(isinstance(entry, dict) for entry in item) and len(trail) < MAX_DEPTH:
                for index, entry in enumerate(item[:20]):
                    walk(entry, (*trail, str(index + 1)))
            return
        if isinstance(item, float) and not math.isfinite(item):
            item = None
        out.append({"path": " › ".join(label(part) for part in trail), "key": key, "value": item,
                    "unit": unit(key, item)})

    walk(value, path)
    return out
