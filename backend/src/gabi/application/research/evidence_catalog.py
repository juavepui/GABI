"""Load only pinned retrospective evidence through specific source ports."""
from typing import Protocol

from gabi.domain.research.evidence_catalog import RULE_SHA256, SOURCES_SHA256, interpret
from gabi.domain.research.live_ledger import fingerprint


class CatalogueInputs(Protocol):
    def document(self, relative_path: str) -> dict: ...
    def verify_sector(self, expected_sha256: str) -> dict: ...


class ReviewedCatalogue(Protocol):
    def load(self) -> dict: ...
    def matches(self, catalogue: dict, weights: dict, universe_id: str) -> bool: ...


def load_catalog(inputs: CatalogueInputs, *, rules_sha256: str = RULE_SHA256,
                 sources_sha256: str = SOURCES_SHA256) -> dict:
    """Fail closed for any changed/missing artifact, independent of its p-values."""
    catalogue: dict = {"available": False, "errors": [], "sources": {}, "factors": {},
                       "model": {}, "placebos": {}, "bootstrap": {}, "independent_confirmations": []}
    try:
        rules = inputs.document("docs/evidence-confidence/preregistro.json")
        manifest = inputs.document("docs/evidence-confidence/sources.json")
        if fingerprint(rules) != rules_sha256 or fingerprint(manifest) != sources_sha256:
            raise ValueError("Reglas o catálogo diferentes de los publicados.")
        catalogue.update(rule_version=rules["rule_version"], rule_sha256=rules_sha256, scope=manifest,
                         sources_fingerprint=sources_sha256, limitations=manifest["limitations"])
        artifacts = {}
        for name, source in manifest["artifacts"].items():
            try:
                result = inputs.document(source["path"])
                if fingerprint(result) != source["sha256"]:
                    raise ValueError("huella distinta")
                if name == "factor-zoo-sector":
                    result = inputs.verify_sector(source["sha256"])
                artifacts[name] = result
                catalogue["sources"][name] = {**source, "stage": "RETROSPECTIVE_DESCRIPTIVE" if name == "factor-zoo-sector" else "RETROSPECTIVE", "verified": True,
                                               "experiment_id": name, "spec_sha256": result.get("spec_sha256"),
                                               "code_sha256": result.get("code_sha256"),
                                               "inputs_fingerprint": fingerprint(result["inputs_sha256"]) if result.get("inputs_sha256") else None}
            except (OSError, ValueError, TypeError, KeyError):
                catalogue["errors"].append(f"{name}: resultado ausente, ilegible o modificado")
        catalogue["available"] = not catalogue["errors"]
        catalogue = interpret(catalogue, artifacts)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        catalogue["available"] = False
        catalogue["errors"].append(str(exc))
    return catalogue


