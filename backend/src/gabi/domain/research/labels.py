"""Readable names for research codes (classifications, families, gate failures); codes stay the identifiers."""

import re

# Same criteria as the frozen Factor Zoo specification (SPEC["classification"]), in plain words.
FACTOR_CLASSIFICATIONS = {
    "sin_evidencia": ("Sin evidencia", "IC medio ≤ 0 o señal no evaluable."),
    "indicio": ("Indicio no significativo",
                "IC medio > 0, pero no supera la corrección Holm (p Holm ≥ 0,05): no se distingue del azar."),
    "requiere_OOS": ("Requiere validación fuera de muestra",
                     "p Holm < 0,05, pero el IC no es positivo en al menos 2 de 3 ventanas o en 2 de 3 terciles "
                     "de tamaño."),
    "robusta_retrospectivamente": ("Robusta en retrospectiva",
                                   "p Holm < 0,05 e IC positivo en al menos 2 de 3 ventanas y 2 de 3 terciles de "
                                   "tamaño; aún requiere validación independiente fuera de muestra."),
}

FAMILIES = {
    "discovery_three_models": "Descubrimiento de estrategias · tres modelos",
    "r3_v2": "R3 E6 · variantes sobre V2",
    "r3_e6": "R3 E6 · variantes sobre V2",
    "repurchase_cash_v1": "Recompras y caja (v1)",
    "rotation_v2": "Rotación con umbral (v2)",
    "v1_reconstructed": "Reglas V1 reconstruidas",
    "value_forward": "Hipótesis de valor prospectiva",
    "r4_value": "R4 · hipótesis de valor",
    "stat_2": "STAT-2 · capacidad predictiva en sección cruzada",
    "stat_4": "STAT-4 · empresas fuera del S&P 500",
    "stat_5": "STAT-5 · mezcla de factores con 60 años",
}
_PREFIXES = (
    (re.compile(r"blind_validation_(\d+)"), lambda m: f"Validación ciega n.º {m[1]}"),
    (re.compile(r"retrospective_v1_([0-9a-f]{8})[0-9a-f]*"), lambda m: f"Auditoría retrospectiva V1 ({m[1]})"),
)

_FAILURES = {
    "ic_not_positive_after_holm": "IC no positivo tras la corrección Holm",
    "ic_not_positive_after_known_search_guard": "IC no positivo tras corregir por las búsquedas conocidas",
}
_SCENARIOS = {"base": "Escenario base", "stress": "Escenario de estrés"}
_WINDOW_FAILURE = re.compile(r"(base|stress)_(\d{4})-(\d{2})_insufficient_or_nonpositive")
_BOUND_FAILURE = re.compile(r"(base|stress)_insufficient_or_lower_bound_nonpositive")


def factor_classification(code: str) -> tuple[str, str]:
    """(label, meaning); an unknown code is shown as it comes rather than hidden."""
    return FACTOR_CLASSIFICATIONS.get(code, (code, ""))


def family(code: str | None) -> str | None:
    """Known families by name; a family typed by the user is already readable and stays as it is."""
    if code is None:
        return None
    if code in FAMILIES:
        return FAMILIES[code]
    for pattern, label in _PREFIXES:
        if match := pattern.fullmatch(code):
            return label(match)
    return code


def failure(code: str) -> str:
    if code in _FAILURES:
        return _FAILURES[code]
    if match := _WINDOW_FAILURE.fullmatch(code):
        return f"{_SCENARIOS[match[1]]} {match[2]}-{match[3]}: muestra insuficiente o resultado no positivo"
    if match := _BOUND_FAILURE.fullmatch(code):
        return f"{_SCENARIOS[match[1]]}: muestra insuficiente o cota inferior no positiva"
    return code
