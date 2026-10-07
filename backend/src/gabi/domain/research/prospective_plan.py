"""Preregistered prospective power, spending and boundaries over an explicit integration port."""

import hashlib
import json
from collections.abc import Callable
from types import MappingProxyType

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

ALPHA = 0.05  # unilateral
LOOKS = MappingProxyType({"2029-09-21": 12, "2032-09-21": 24, "2036-09-21": 40})  # trimestres prospectivos acumulados
RETRO_NON_DESIGN_QUARTERS = 18  # 2011-07 → 2015-10: acreditados, fuera de la muestra de diseño 2016-2025
OBSERVED_QUARTERLY_SHARPE = 0.0106 / 0.0362  # exceso V1 Top-20 vs SPY 2011-2025 (#35, #39)


def obrien_fleming_spending(fraction: float, alpha: float = ALPHA) -> float:
    """Gasto acumulado de alfa de Lan-DeMets tipo O'Brien-Fleming (unilateral)."""
    return float(2 * (1 - norm.cdf(norm.ppf(1 - alpha / 2) / np.sqrt(fraction))))


def boundaries(fractions: list[float], alpha: float = ALPHA, *, cdf: Callable[[np.ndarray, np.ndarray], float]) -> list[float]:
    """Umbrales z de cada revisión con el gasto O'Brien-Fleming (integración multinormal exacta)."""
    result: list[float] = []
    spent = 0.0
    for k, fraction in enumerate(fractions):
        target = obrien_fleming_spending(fraction, alpha) - spent
        if k == 0:
            bound = float(norm.ppf(1 - target))
        else:
            cov = np.array([[np.sqrt(min(a, b) / max(a, b)) for b in fractions[:k + 1]] for a in fractions[:k + 1]])

            def excess(c, prior=tuple(result), target=target):
                # P(no cruzó antes y cruza ahora) - gasto objetivo
                below_all = cdf(np.array([*prior, c]), cov)
                below_prior = cdf(np.array(prior), cov[:k, :k]) \
                    if k > 1 else norm.cdf(prior[0])
                return (below_prior - below_all) - target
            bound = float(brentq(excess, 0.5, 6.0))
        result.append(bound)
        spent = obrien_fleming_spending(fraction, alpha)
    return result


def plan(*, cdf: Callable[[np.ndarray, np.ndarray], float]) -> dict:
    counts = list(LOOKS.values())
    fractions = [n / counts[-1] for n in counts]
    bounds = boundaries(fractions, cdf=cdf)
    drift = OBSERVED_QUARTERLY_SHARPE
    power = {date: float(norm.cdf(drift * np.sqrt(n) - b)) for (date, n), b in zip(LOOKS.items(), bounds, strict=True)}
    combined = {date: float(norm.cdf(drift * np.sqrt(n + RETRO_NON_DESIGN_QUARTERS) - b))
                for (date, n), b in zip(LOOKS.items(), bounds, strict=True)}
    return {
        "issue": 42, "blind_validation_id": 1, "alpha_unilateral": ALPHA,
        "primary": "exceso trimestral equiponderado del Top-20 ciego (entrada a entrada) frente al SPY; "
                   "t de la media con z = media / (desv. típica / raíz(n))",
        "secondary": "el mismo exceso frente al S&P 500 equiponderado (ETF RSP), como aproximación del universo",
        "combination": {"rule": "Stouffer ponderado por raíz del número de trimestres: retrospectivo acreditado "
                                "fuera de la muestra de diseño (2011-07 → 2015-10, 18 trimestres, V1 Top-20 vs SPY) "
                                "+ prospectivo; se juzga con los mismos umbrales secuenciales",
                        "excluded": "2016-2025 (muestra de diseño de GABI) nunca entra en la combinación",
                        "note": "El z retrospectivo ya se conoce; la regla de pesos queda fijada aquí, antes de "
                                "ver ningún dato prospectivo."},
        "looks": [{"fecha": date, "trimestres_prospectivos": n, "fraccion_informacion": f, "umbral_z": b,
                   "alfa_acumulado": obrien_fleming_spending(f), "potencia_si_efecto_observado_solo": power[date],
                   "potencia_si_efecto_observado_combinada": combined[date]}
                  for (date, n), f, b in zip(LOOKS.items(), fractions, bounds, strict=True)],
        "requirements": ["El modelo (GABI-MF-v1, 30/35/25/10, Top-20, trimestral) no cambia hasta la última revisión; "
                         "si cambia, el registro prospectivo termina en esa fecha.",
                         "Cada rebalanceo se registra a tiempo con blind_validation.record_rebalance; la cadena de "
                         "hashes debe estar íntegra en cada revisión.",
                         "Solo se miran los resultados en las fechas de revisión; parar antes por éxito solo si se "
                         "cruza el umbral; nunca se para por pérdidas para 'probar otra cosa' sin documentarlo."],
        "decision_at_each_look": {"cruza_umbral": "ventaja estadísticamente significativa (fin del estudio)",
                                  "no_cruza": "continuar hasta la siguiente revisión",
                                  "ultima_revision_sin_cruzar": "sin evidencia de ventaja frente al SPY"},
        "assumption_warning": "La potencia supone un efecto futuro igual al observado 2011-2025; si hubo "
                              "sobreajuste en el diseño será menor.",
    }


def plan_hash(record: dict) -> str:
    return hashlib.sha256(json.dumps(json_value(record), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def json_value(value):
    """The original plan fingerprint's JSON normalization, including its key types."""
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def gabi_blind_plan() -> dict:
    """Plan fijo para la prueba ciega de GABI (id 1): una única revisión en su desbloqueo (#42).

    El propietario decidió no prolongarla (2026-09-27). Se deja escrita la
    potencia esperable para que el resultado de 2029 se lea con esa cautela.
    """
    quarters = 12
    drift = OBSERVED_QUARTERLY_SHARPE
    bound = float(norm.ppf(1 - ALPHA))
    return {
        "issue": 42, "blind_validation_id": 1, "look": "2029-09-21", "trimestres": quarters,
        "alpha_unilateral": ALPHA, "umbral_z": bound,
        "primary": "exceso trimestral equiponderado del Top-20 ciego frente al SPY; z = media / (desv. / raíz(n))",
        "secondary": "exceso frente a RSP (S&P 500 equiponderado); Holm sobre ambas",
        "combination": {"rule": "Stouffer ponderado por raíz del número de trimestres con el retrospectivo "
                                "acreditado fuera de la muestra de diseño (2011-07 → 2015-10, 18 trimestres)",
                        "excluded": "2016-2025 (muestra de diseño)"},
        "potencia_si_efecto_observado": {"sola": float(norm.cdf(drift * np.sqrt(quarters) - bound)),
                                         "combinada": float(norm.cdf(drift * np.sqrt(quarters + RETRO_NON_DESIGN_QUARTERS)
                                                                     - bound))},
        "lectura": "Con 12 trimestres, no cruzar el umbral NO demuestra que GABI no funcione: la prueba tiene poca "
                   "potencia. Cruzarlo sería evidencia a favor.",
    }


