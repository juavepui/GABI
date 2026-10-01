"""Preregistered plans of the blind validations, checked with their unchanged legacy fingerprints."""

import hashlib
import json
from pathlib import Path

GABI_PLAN = Path("docs") / "prospective-plan" / "gabi-id1.json"
VALUE_PLAN = Path("docs") / "value-hypothesis" / "preregistro.json"


def _read(path: Path) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError(f"{path.name} supera el límite de lectura.")
    return json.loads(raw)


def gabi_plan(root: Path) -> dict:
    from gabi import prospective_plan

    record = _read(root / GABI_PLAN)
    if prospective_plan.plan_hash(record["plan"]) != record["sha256"]:
        raise ValueError("El plan de la prueba ciega de GABI no coincide con su huella.")
    plan = record["plan"]
    return {"validation_id": int(plan["blind_validation_id"]), "issue": plan["issue"], "looks": [plan["look"]],
            "sha256": record["sha256"], "source": GABI_PLAN.as_posix()}


def value_plan(root: Path) -> dict:
    from gabi import value_hypothesis

    record = _read(root / VALUE_PLAN)
    digest = hashlib.sha256(json.dumps(record["spec"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if digest != record["sha256"] or value_hypothesis.spec_hash() != record["sha256"]:
        raise ValueError("El preregistro de la hipótesis de valor no coincide con su huella.")
    return {"validation_id": int(record["blind_validation_id"]), "issue": record["spec"]["issue"],
            "looks": [look["fecha"] for look in record["plan_secuencial"]["looks"]],
            "sha256": record["sha256"], "source": VALUE_PLAN.as_posix()}
