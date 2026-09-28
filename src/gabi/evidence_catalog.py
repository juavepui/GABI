"""Pinned, read-only retrospective studies; no blind or unfinished results read."""

import hashlib
import json

from . import config, live_ledger

RULE_SHA256 = "2a0776de996c8044e4997da925e0b603da03c0721a883810bfd9cdfe541064ab"
SOURCES_SHA256 = "312e51e6d6cb90291b90c28ab4ff48f775c6b4d78e35055fde607651529db1a2"


def load() -> dict:
    """Fail closed for any changed/missing artifact, independent of its p-values."""
    folder = config.BASE_DIR / "docs" / "evidence-confidence"
    catalogue: dict = {"available": False, "errors": [], "sources": {}, "factors": {},
                       "model": {}, "placebos": {}, "bootstrap": {}, "independent_confirmations": []}
    try:
        rules = json.loads((folder / "preregistro.json").read_text(encoding="utf-8"))
        manifest = json.loads((folder / "sources.json").read_text(encoding="utf-8"))
        if live_ledger.fingerprint(rules) != RULE_SHA256 or live_ledger.fingerprint(manifest) != SOURCES_SHA256:
            raise ValueError("Reglas o catálogo diferentes de los publicados.")
        catalogue.update(rule_version=rules["rule_version"], rule_sha256=RULE_SHA256, scope=manifest,
                         sources_fingerprint=SOURCES_SHA256, limitations=manifest["limitations"])
        artifacts = {}
        for name, source in manifest["artifacts"].items():
            try:
                result = json.loads((config.BASE_DIR / source["path"]).read_text(encoding="utf-8"))
                if live_ledger.fingerprint(result) != source["sha256"]:
                    raise ValueError("huella distinta")
                artifacts[name] = result
                catalogue["sources"][name] = {**source, "stage": "RETROSPECTIVE", "verified": True,
                                               "experiment_id": name, "spec_sha256": result.get("spec_sha256"),
                                               "code_sha256": result.get("code_sha256"),
                                               "inputs_fingerprint": live_ledger.fingerprint(result["inputs_sha256"]) if result.get("inputs_sha256") else None}
            except (OSError, ValueError, TypeError):
                catalogue["errors"].append(f"{name}: resultado ausente, ilegible o modificado")
        catalogue["available"] = not catalogue["errors"]
        if "factor-zoo" in artifacts:
            catalogue["factors"] = artifacts["factor-zoo"]["factors"]
        if "cross-section-test" in artifacts:
            result = artifacts["cross-section-test"]
            principal = result["principal_ic"]
            secondary = result["secundarias"]
            passed = principal["media"] > 0 and principal["p_unilateral"] < .05
            passed &= all(v["media"] > 0 and v["p_holm"] < .05 for v in secondary.values())
            catalogue["model"] = {"pass": passed, "primary": principal, "secondary": secondary,
                                   "decision": result["decision"], "stage": "RETROSPECTIVE"}
        if "placebo-engine" in artifacts:
            result = artifacts["placebo-engine"]
            controls = {n: result["nulls"][n]["metrics"]["excess_mean"] for n in ("random_ranking", "random_top_n")}
            catalogue["placebos"] = {"pass": False, "conditional_pass": all(v["observed"] > 0 and v["p_empirical"] < .05 for v in controls.values()),
                                      "controls": controls, "pbo": result["pbo_weight_family"]["pbo"],
                                      "dsr": result["dsr_weight_family"]["dsr"],
                                      "reason": "Controles aleatorios favorables, condicionados al histórico; sectores no identificables y PBO frágil."}
        if "block-bootstrap" in artifacts:
            result = artifacts["block-bootstrap"]
            dataset = result["datasets"]["v2_daily_net"]
            intervals = {b: r["comparisons"]["spy"]["metrics"]["cagr_difference"] for b, r in dataset["runs"].items()}
            catalogue["bootstrap"] = {"pass": False, "primary_block": dataset["primary_block"],
                                       "v2_cagr_difference": intervals,
                                       "unavailable": result.get("unavailable_datasets", {}),
                                       "reason": "V1 neto no estimable; el intervalo principal de CAGR de V2 incluye cero y cambia con la longitud de bloque."}
        if "tail-effect-test" in artifacts:
            catalogue["tail"] = {"primary": artifacts["tail-effect-test"].get("primary"),
                                  "interpretation": "Efecto retrospectivo de cola; no sustituye el contraste principal del Composite ni valida cada factor."}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        catalogue["available"] = False
        catalogue["errors"].append(str(exc))
    return catalogue


def matches(catalogue: dict, weights: dict, universe_id: str) -> bool:
    scope = catalogue.get("scope", {})
    code = config.BASE_DIR / "src" / "gabi" / "scoring.py"
    try:
        code_hash = hashlib.sha256(code.read_text(encoding="utf-8").encode()).hexdigest()
    except OSError:
        return False
    return (set(weights) == set(scope.get("weights", {}))
            and all(abs(weights[k] - v) <= 1e-10 for k, v in scope.get("weights", {}).items())
            and universe_id == scope.get("universe_id") and code_hash == scope.get("scoring_sha256"))
