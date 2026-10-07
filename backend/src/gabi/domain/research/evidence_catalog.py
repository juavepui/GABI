"""Interpret already verified retrospective studies and compare their declared scope."""
RULE_SHA256 = "2a0776de996c8044e4997da925e0b603da03c0721a883810bfd9cdfe541064ab"
SOURCES_SHA256 = "2d1f928a2bc87f5ce77c051fbc1885f57507f028d8b313d903c3354e3c55e684"


def interpret(catalogue: dict, artifacts: dict) -> dict:
    catalogue = dict(catalogue)
    catalogue["errors"] = list(catalogue.get("errors", []))
    try:
        if "factor-zoo" in artifacts:
            catalogue["factors"] = {metric: dict(data) for metric, data in artifacts["factor-zoo"]["factors"].items()}
            if "factor-zoo-sector" in artifacts:
                for metric, data in catalogue["factors"].items():
                    data["sic_division_stability"] = artifacts["factor-zoo-sector"]["factors"].get(metric, {})
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
    except (ValueError, KeyError, TypeError) as exc:
        catalogue["available"] = False
        catalogue["errors"].append(str(exc))
    return catalogue


def matches(catalogue: dict, weights: dict, universe_id: str, *, scoring_sha256: str | None) -> bool:
    if scoring_sha256 is None:
        return False
    scope = catalogue.get("scope", {})
    code_hash = scoring_sha256
    return (set(weights) == set(scope.get("weights", {}))
            and all(abs(weights[k] - v) <= 1e-10 for k, v in scope.get("weights", {}).items())
            and universe_id == scope.get("universe_id") and code_hash == scope.get("scoring_sha256"))
