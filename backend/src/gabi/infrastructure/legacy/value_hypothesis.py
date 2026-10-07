"""Preregistration of the value hypothesis (#43): blind validation, experiment log and the sealed record.

Explicit write through ``python -m gabi_cli research value-hypothesis --preregister``; an
existing record is only checked against the current specification, never rewritten.
"""
import json
from pathlib import Path

from gabi.domain.research import value_hypothesis as hypothesis
from gabi.domain.research.prospective_plan import boundaries, obrien_fleming_spending
from gabi.infrastructure.statistics.prospective import ScipyNormalCDF


def specification() -> dict:
    from gabi import scoring

    return hypothesis.specification(scoring.SCORE_METRICS["value"])


def preregister(output: Path) -> dict:
    """Congela la especificación, crea la prueba ciega con puntuaciones y registra el plan secuencial."""
    from gabi import blind_validation, research_lab
    from gabi import factor_stability as fs

    spec = specification()
    output.mkdir(parents=True, exist_ok=True)
    path = output / "preregistro.json"
    digest = hypothesis.spec_hash(spec)
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["sha256"] != digest:
            raise ValueError("La especificación cambió después del preregistro.")
        return record
    plan = hypothesis.sequential_plan(boundaries(hypothesis.fractions(), cdf=ScipyNormalCDF()),
                                      obrien_fleming_spending)
    validation_id = blind_validation.create_validation(
        "Hipótesis de valor -- prueba prospectiva ciega (#43)", hypothesis.WEIGHTS, 20, 3, hypothesis.START,
        hypothesis.FIRST_LOOK, model_id=hypothesis.MODEL_ID)
    blind_validation.enable_ranking_snapshots(validation_id)
    experiment = research_lab.log_experiment(
        hypothesis.MODEL_ID, "LIVE_FORWARD", True, family="r4_value", universe="S&P 500 (camino operativo)",
        weights=hypothesis.WEIGHTS, n_positions=20, rebalance="trimestral", oos_start=hypothesis.START,
        oos_end=list(hypothesis.LOOKS)[-1],
        notes=f"Preregistro #43, sha256 {digest}; prueba ciega id {validation_id}; sin resultados")
    record = {"sha256": digest, "spec": spec, "plan_secuencial": plan,
              "blind_validation_id": validation_id, "experiment_id": experiment}
    path.write_text(json.dumps(fs._json_safe(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record
