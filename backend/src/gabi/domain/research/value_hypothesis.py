"""Hipótesis de valor preregistrada con validación solo prospectiva (issue #43).

La elección de «valor» se hizo después de ver el IC por bloques de 2011-2025
(#40), así que ese periodo no puede validarla. La hipótesis se congela con hash
y se evalúa solo con una prueba ciega nueva que guarda además la puntuación
completa del universo. La prueba ciega de GABI (id 1) no se toca.

La especificación y su huella deben coincidir byte a byte con
``docs/value-hypothesis/preregistro.json``.
"""

import hashlib
import json

MODEL_ID = "GABI-VALUE-v1"
WEIGHTS = {"value": 1.0, "quality": 0.0, "momentum": 0.0, "risk": 0.0}
START = "2026-12-21"  # mismo calendario que la prueba ciega de GABI; datos frescos en cada registro
FIRST_LOOK = "2029-12-21"  # 12 trimestres; se continúa sin cambios hasta 40
LOOKS = {"2029-12-21": 12, "2032-12-21": 24, "2036-12-21": 40}


def specification(value_metrics: list[str]) -> dict:
    """La especificación preregistrada; ``value_metrics`` son las métricas del bloque de valor de GABI."""
    return {
        "issue": 43, "model_id": MODEL_ID, "stage": "LIVE_FORWARD",
        "hypothesis": "Entre los miembros del S&P 500 con datos suficientes, un composite de valor (E/P, B/P y "
                      "EBITDA/EV, percentiles dentro del sector) predice la rentabilidad relativa del trimestre "
                      "siguiente, y su Top-20 equiponderado supera al SPY y al S&P 500 equiponderado.",
        "rationale": "Composite de valor clásico (Fama-French 1992; Lakonishok-Shleifer-Vishny 1994; Loughran-Wellman "
                     "2011, EBITDA/EV; Asness-Moskowitz-Pedersen 2013). Se reutiliza el bloque de valor existente de "
                     "GABI para no añadir grados de libertad. Elegido tras ver el IC por bloques de 2011-2025 (#40): "
                     "ese periodo NO cuenta como evidencia.",
        "score": {"weights": WEIGHTS, "value_metrics": value_metrics,
                  "percentiles": "dentro del sector (scoring.build_scores, sin cambios)"},
        "universe": "S&P 500 vigente en cada fecha (camino operativo), mismo filtro de datos que GABI: composite no "
                    "vacío y cobertura >= 70 % de las 13 métricas",
        "portfolio": {"n_positions": 20, "weighting": "equiponderada", "rebalance_months": 3,
                      "start": START, "entry": "último cierre ajustado disponible al registrar (blind_validation)"},
        "tests": {
            "primary": "IC de Spearman trimestral entre la puntuación registrada y el retorno del trimestre siguiente, "
                       "media con t unilateral; umbrales O'Brien-Fleming en 12, 24 y 40 trimestres",
            "secondary": ["exceso trimestral del Top-20 frente al SPY", "exceso frente a RSP (S&P 500 equiponderado)"],
            "secondary_correction": "Holm sobre las 2, con los mismos umbrales secuenciales",
            "looks": LOOKS,
        },
        "decision": {"cruza_umbral_principal": "evidencia de capacidad predictiva del valor (fin del estudio)",
                     "no_cruza": "continuar sin cambios hasta la siguiente revisión",
                     "ultima_revision_sin_cruzar": "sin evidencia"},
        "rules": ["El modelo no cambia hasta la última revisión; si cambia, el registro termina en esa fecha.",
                  "Cada rebalanceo se registra a tiempo; la cadena de hashes y la de puntuaciones deben estar íntegras.",
                  "Solo se miran resultados en las revisiones fijadas.",
                  "Cuenta como la configuración 30 del recuento de múltiples pruebas."],
        "blind_validation_gabi": "id 1, sin cambios",
    }


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fractions() -> list[float]:
    counts = list(LOOKS.values())
    return [n / counts[-1] for n in counts]


def sequential_plan(boundaries: list[float], spending) -> dict:
    """Umbrales O'Brien-Fleming de las revisiones fijadas (``boundaries`` y ``spending`` del plan prospectivo)."""
    return {"looks": [{"fecha": d, "trimestres": n, "umbral_z": b, "alfa_acumulado": spending(f)}
                      for (d, n), f, b in zip(LOOKS.items(), fractions(), boundaries, strict=True)]}
