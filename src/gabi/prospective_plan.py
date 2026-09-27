"""Plan preregistrado de análisis de la prueba ciega prospectiva (issue #42).

No lee resultados de la prueba ciega. Fija de antemano:

- la métrica y la prueba: exceso trimestral del Top-20 ciego frente al SPY
  (principal) y frente al S&P 500 equiponderado, RSP (secundaria), t
  unilateral;
- un diseño secuencial con revisiones fijas y umbrales O'Brien-Fleming
  (gasto de alfa de Lan-DeMets), que permite mirar en 2029 sin inflar el error
  de tipo I;
- la potencia esperable de cada revisión si el efecto futuro fuese el
  observado en 2011-2025 (#39), y la regla para combinarla con la evidencia
  retrospectiva que no es muestra de diseño (2011-07 → 2015-10).
"""

import argparse
import hashlib
import json

import numpy as np
from scipy.optimize import brentq
from scipy.stats import multivariate_normal, norm

from . import config
from . import factor_stability as fs

OUTPUT = config.BASE_DIR / "docs" / "prospective-plan"
ALPHA = 0.05  # unilateral
LOOKS = {"2029-09-21": 12, "2032-09-21": 24, "2036-09-21": 40}  # trimestres prospectivos acumulados
RETRO_NON_DESIGN_QUARTERS = 18  # 2011-07 → 2015-10: acreditados, fuera de la muestra de diseño 2016-2025
OBSERVED_QUARTERLY_SHARPE = 0.0106 / 0.0362  # exceso V1 Top-20 vs SPY 2011-2025 (#35, #39)


def obrien_fleming_spending(fraction: float, alpha: float = ALPHA) -> float:
    """Gasto acumulado de alfa de Lan-DeMets tipo O'Brien-Fleming (unilateral)."""
    return float(2 * (1 - norm.cdf(norm.ppf(1 - alpha / 2) / np.sqrt(fraction))))


def boundaries(fractions: list[float], alpha: float = ALPHA) -> list[float]:
    """Umbrales z de cada revisión con el gasto O'Brien-Fleming (integración multinormal exacta)."""
    result: list[float] = []
    spent = 0.0
    for k, fraction in enumerate(fractions):
        target = obrien_fleming_spending(fraction, alpha) - spent
        if k == 0:
            bound = float(norm.ppf(1 - target))
        else:
            cov = np.array([[np.sqrt(min(a, b) / max(a, b)) for b in fractions[:k + 1]] for a in fractions[:k + 1]])
            mvn = multivariate_normal(mean=np.zeros(k + 1), cov=cov)

            def excess(c, prior=tuple(result), mvn=mvn, target=target):
                # P(no cruzó antes y cruza ahora) - gasto objetivo
                below_all = mvn.cdf(np.array([*prior, c]))
                below_prior = multivariate_normal(mean=np.zeros(k), cov=cov[:k, :k]).cdf(np.array(prior)) \
                    if k > 1 else norm.cdf(prior[0])
                return (below_prior - below_all) - target
            bound = float(brentq(excess, 0.5, 6.0))
        result.append(bound)
        spent = obrien_fleming_spending(fraction, alpha)
    return result


def plan() -> dict:
    counts = list(LOOKS.values())
    fractions = [n / counts[-1] for n in counts]
    bounds = boundaries(fractions)
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
    return hashlib.sha256(json.dumps(fs._json_safe(record), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write() -> dict:
    record = plan()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = {"sha256": plan_hash(record), "plan": record}
    (OUTPUT / "plan.json").write_text(json.dumps(fs._json_safe(payload), ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(fs._json_safe(write() if args.write else {"plan": plan()}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
