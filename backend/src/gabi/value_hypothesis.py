"""Hipótesis de valor preregistrada con validación solo prospectiva (issue #43).

La elección de «valor» se hizo después de ver el IC por bloques de 2011-2025
(#40), así que ese periodo no puede validarla. La hipótesis se congela aquí,
con hash, y se evalúa solo con una prueba ciega nueva que guarda además la
puntuación completa del universo (IC prospectivo, la prueba de más potencia
según el #39). La prueba ciega de GABI (id 1) no se toca.
"""

import argparse
import hashlib
import json

from . import blind_validation, config, prospective_plan, research_lab, scoring
from . import factor_stability as fs

OUTPUT = config.BASE_DIR / "docs" / "value-hypothesis"
MODEL_ID = "GABI-VALUE-v1"
WEIGHTS = {"value": 1.0, "quality": 0.0, "momentum": 0.0, "risk": 0.0}
START = "2026-12-21"  # mismo calendario que la prueba ciega de GABI; datos frescos en cada registro
FIRST_LOOK = "2029-12-21"  # 12 trimestres; se continúa sin cambios hasta 40
LOOKS = {"2029-12-21": 12, "2032-12-21": 24, "2036-12-21": 40}

SPEC = {
    "issue": 43, "model_id": MODEL_ID, "stage": "LIVE_FORWARD",
    "hypothesis": "Entre los miembros del S&P 500 con datos suficientes, un composite de valor (E/P, B/P y "
                  "EBITDA/EV, percentiles dentro del sector) predice la rentabilidad relativa del trimestre "
                  "siguiente, y su Top-20 equiponderado supera al SPY y al S&P 500 equiponderado.",
    "rationale": "Composite de valor clásico (Fama-French 1992; Lakonishok-Shleifer-Vishny 1994; Loughran-Wellman "
                 "2011, EBITDA/EV; Asness-Moskowitz-Pedersen 2013). Se reutiliza el bloque de valor existente de "
                 "GABI para no añadir grados de libertad. Elegido tras ver el IC por bloques de 2011-2025 (#40): "
                 "ese periodo NO cuenta como evidencia.",
    "score": {"weights": WEIGHTS, "value_metrics": scoring.SCORE_METRICS["value"],
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


def spec_hash() -> str:
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def preregister() -> dict:
    """Congela la especificación, crea la prueba ciega con puntuaciones y registra el plan secuencial."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "preregistro.json"
    digest = spec_hash()
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["sha256"] != digest:
            raise ValueError("La especificación cambió después del preregistro.")
        return record
    counts = list(LOOKS.values())
    fractions = [n / counts[-1] for n in counts]
    bounds = prospective_plan.boundaries(fractions)
    plan = {"looks": [{"fecha": d, "trimestres": n, "umbral_z": b, "alfa_acumulado":
                       prospective_plan.obrien_fleming_spending(f)}
                      for (d, n), f, b in zip(LOOKS.items(), fractions, bounds, strict=True)]}
    validation_id = blind_validation.create_validation(
        "Hipótesis de valor -- prueba prospectiva ciega (#43)", WEIGHTS, 20, 3, START, FIRST_LOOK, model_id=MODEL_ID)
    blind_validation.enable_ranking_snapshots(validation_id)
    experiment = research_lab.log_experiment(
        MODEL_ID, "LIVE_FORWARD", True, family="r4_value", universe="S&P 500 (camino operativo)",
        weights=WEIGHTS, n_positions=20, rebalance="trimestral", oos_start=START, oos_end=list(LOOKS)[-1],
        notes=f"Preregistro #43, sha256 {digest}; prueba ciega id {validation_id}; sin resultados")
    record = {"sha256": digest, "spec": SPEC, "plan_secuencial": plan,
              "blind_validation_id": validation_id, "experiment_id": experiment}
    path.write_text(json.dumps(fs._json_safe(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregister", action="store_true")
    args = parser.parse_args()
    if args.preregister:
        record = preregister()
        print(json.dumps({"sha256": record["sha256"], "blind_validation_id": record["blind_validation_id"],
                          "plan": record["plan_secuencial"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
