"""Reconcile published search metadata without opening databases or blind reserves.

This catalog preserves the historical 34-entry convention; it does not certify
an exhaustive search count or recalculate any published result or correction.
"""

import argparse
import hashlib
import json
from pathlib import Path

from . import config

OUTPUT = config.BASE_DIR / "docs" / "search-ledger" / "ledger.json"
DIAGNOSTICS = (
    "factor-history", "tail-effect-test", "factor-zoo", "placebo-engine",
    "cross-section-test", "block-bootstrap", "rank-stability", "evidence-confidence",
    "factor-zoo-sector",
)


def fingerprint(value: object) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def build(root: Path = config.BASE_DIR) -> dict:
    """Read only explicitly named, already published repository artifacts."""
    sources: dict[str, str] = {}
    documents: dict[str, dict] = {}

    def pin(name: str) -> str:
        content = (root / name).read_text(encoding="utf-8")
        sources[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return content

    def read(name: str) -> dict:
        if name not in documents:
            documents[name] = json.loads(pin(name))
        return documents[name]

    def entry(key: str, family: str, settings: dict, specification: str, result: str | None,
              dates: dict, state: str, decision: str, *, failures: list | None = None) -> dict:
        return {
            "id": key, "family": family, "configuration": settings,
            "configuration_sha256": fingerprint(settings), "specification_ref": specification,
            "result_ref": result, "observed_sample": dates if state == "observed" else None,
            "planned_sample": dates if state != "observed" else None,
            "state": state, "decision": decision, "failures": failures,
            "demonstrated_superiority": False,
        }

    v1_path = "docs/overfitting-audit/audit.json"
    v1 = read(v1_path)
    v1_dates = {"start": v1["inputs"]["start"], "end": v1["inputs"]["end"],
                "periods": 36, "universe": "historical S&P 500, sample 200/date, seed 42"}
    legacy = [entry(
        "v1/" + trial["trial_id"], "v1_reconstructed", {"trial": trial,
        "common_configuration": {key: v1["inputs"][key] for key in
                                 ("start", "end", "max_symbols", "seed", "weights")},
        "engine": "V1 reconstruction; individual coverage 70%, universe coverage 50%",
        "common_inputs_ref": v1_path + "#/inputs"}, v1_path + f"#/catalog/{i}",
        "docs/overfitting-audit/returns.csv#" + trial["trial_id"], v1_dates, "observed",
        "historically_selected" if trial["trial_id"] == "top20_q" else "retained_for_audit",
    ) for i, trial in enumerate(v1["catalog"])]
    pin("docs/overfitting-audit/returns.csv")
    pin("HIPOTESIS_CONGELADA.md")

    rotation_path = "docs/rotation-experiment/protocol.json"
    rotation = read(rotation_path)
    rotation_result = read("docs/rotation-experiment/audit.json")
    rotation_dates = {"start": rotation["start"], "end": rotation["end"],
                      "universe": "historical S&P 500, full eligible universe"}
    additional: list[dict] = []
    for name, points in rotation["variants"].items():
        result_index = next(i for i, row in enumerate(rotation_result["metrics"])
                            if row["variant"] == name and row["window"] == "full_history")
        record = entry("rotation/" + name, "rotation_v2",
                       {"rotation_hurdle_points": points, "common_protocol": rotation},
                       rotation_path + "#/variants/" + name,
                       f"docs/rotation-experiment/audit.json#/metrics/{result_index}",
                       rotation_dates, "observed", "reference" if points == 0 else "not_promoted")
        (additional if points == 0 else legacy).append(record)

    r3_path = "docs/r3-e6-experiment/preregistro.json"
    r3 = read(r3_path)["spec"]
    analysis = read("docs/r3-e6-experiment/analysis.json")
    r3_dates = {"start": r3["sample"]["invested_from"], "end": r3["sample"]["end"],
                "periods": 57, "universe": "acreditado-38, same eligible issuers as control"}
    for name, settings in {"control_composite": r3["control"], **r3["variants"]}.items():
        result_path = f"docs/r3-e6-experiment/{name}/result.json"
        read(result_path)
        for top_n in r3["engine"]["top_n"]:
            record = entry(f"r3/{name}/top{top_n}", "r3_v2",
                           {"variant": settings, "top_n": top_n, "common_spec": r3},
                           r3_path + "#/spec/" + ("control" if name == "control_composite" else "variants/" + name),
                           result_path + f"#/top{top_n}", r3_dates, "observed",
                           "reference" if name == "control_composite" else
                           analysis["decisiones"][name]["decision"] if top_n == 20 else "secondary_not_promoted")
            (legacy if top_n == 20 else additional).append(record)

    value_path = "docs/value-hypothesis/preregistro.json"
    value = read(value_path)["spec"]
    legacy.append(entry("value/prospective", "value_forward", value, value_path + "#/spec", None,
                        {"start": value["portfolio"]["start"], "looks": value["tests"]["looks"],
                         "universe": value["universe"]}, "pending_prospective", "await_preregistered_looks"))

    discovery_path = "docs/strategy-discovery/preregistro.json"
    discovery = read(discovery_path)["spec"]
    results = read("docs/strategy-discovery/resultado.json")
    dates = {"start": "2011-07-02", "end": "2025-07-02", "periods": results["n_dates"],
             "universe": "acreditado-38, dated SIC and declared model eligibility",
             "continuous": False}
    for name, blocks in discovery["models"].items():
        legacy.append(entry("discovery/" + name, "discovery_three_models",
                            {"blocks": blocks, "common_spec": discovery},
                            discovery_path + "#/spec/models/" + name,
                            "docs/strategy-discovery/resultado.json#/models/" + name,
                            dates, "observed", "failed_daily_gate", failures=results["models"][name]["failures"]))

    rcf_path = "docs/strategy-discovery/repurchase-cash-v1/preregistro.json"
    rcf = read(rcf_path)["spec"]
    rcf_result = read("docs/strategy-discovery/repurchase-cash-v1/resultado.json")
    legacy.append(entry("repurchase/RCF", "repurchase_cash_v1", rcf, rcf_path + "#/spec",
                        "docs/strategy-discovery/repurchase-cash-v1/resultado.json#/summary",
                        dates, "observed", "failed_daily_gate", failures=rcf_result["summary"]["failures"]))

    diagnostics = []
    for family in DIAGNOSTICS:
        protocol = f"docs/{family}/preregistro.json"
        result = f"docs/{family}/resultado.json" if family != "evidence-confidence" else f"docs/{family}/sources.json"
        read(protocol)
        read(result)
        diagnostics.append({"family": family, "specification_ref": protocol, "result_ref": result,
                            "classification": "published_diagnostic_not_added_to_legacy_34"})
    for family in ("full-universe-audit", "factor-stability", "factor-benchmark"):
        path = f"docs/{family}/audit.json"
        read(path)
        diagnostics.append({"family": family, "result_ref": path,
                            "classification": "reconstruction_or_diagnostic_not_added_to_legacy_34"})
    for version in ("", "/v2"):
        path = f"docs/strategy-discovery/capital-inputs{version}/preregistro.json"
        read(path)
        diagnostics.append({"family": "capital_inputs" + version, "specification_ref": path,
                            "classification": "input_audit_zero_strategy_configurations"})
    pin("docs/strategy-discovery/capital-inputs/v2/resultado.json")
    pin("docs/placebo-engine/weight_perturbations.csv")
    pin("docs/placebo-engine/null_distributions.csv")

    if len(legacy) != 34 or len({item["id"] for item in legacy + additional}) != len(legacy + additional):
        raise ValueError("The historical convention changed; review the reconciliation before publishing.")
    return {
        "version": 1, "as_of": "2026-09-29", "scope": "explicit_published_repository_artifacts_only",
        "exhaustive_search_history": False, "global_error_control_established": False,
        "hash_convention": "UTF-8 text, canonical LF; does not replace original binary/canonical result hashes",
        "counts": {"legacy_guard_entries": len(legacy),
                   "legacy_observed_entries": sum(row["state"] == "observed" for row in legacy),
                   "legacy_pending_entries": sum(row["state"] != "observed" for row in legacy),
                   "additional_observed_records": len(additional), "diagnostic_groups": len(diagnostics)},
        "legacy_entries": legacy, "additional_observed_records": additional, "diagnostics": diagnostics,
        "unresolved_groups": v1["excluded"],
        "limitations": [
            "34 is the inherited bookkeeping convention, not an exhaustive count of observed searches.",
            "VALUE is specified but its prospective outcomes have not been observed.",
            "Reconstructed V1 rules do not recover all originally observed versions or sessions.",
            "Rotation control and three R3 Top-10 runs are retained separately; not declared independent trials.",
            "13 Factor Zoo tests, 256 weight perturbations and 8192 null paths also exposed retrospective information.",
            "Diagnostics and replications must not be summed as independent strategy trials.",
            "Private/manual/optimization sessions are not exhaustively recoverable from published artifacts.",
            "No operational DB, blind outcome, raw price snapshot or reserved smallmid dataset was opened.",
            "No old result, guard alpha, model or decision is recalculated or silently changed.",
        ],
        "sources_sha256_lf": dict(sorted(sources.items())),
    }


def verify(path: Path = OUTPUT, root: Path = config.BASE_DIR) -> None:
    published = json.loads(path.read_text(encoding="utf-8"))
    if published != build(root):
        raise ValueError("Search ledger or its published sources changed; publish an explicit new revision.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--write", type=Path, help="New destination; never overwrites a published ledger")
    actions.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify()
        print("Published search ledger and source fingerprints verified (history remains incomplete).")
    else:
        ledger = build()
        args.write.parent.mkdir(parents=True, exist_ok=True)
        with args.write.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(ledger, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        print(json.dumps(ledger["counts"]))


if __name__ == "__main__":
    main()
