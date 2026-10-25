"""Readable names for research codes; the codes themselves never change."""

import ast
import json
from pathlib import Path

from gabi.domain.research import labels


def frozen_classifications() -> set[str]:
    # Read the frozen module's source instead of importing it: SPEC is a literal there.
    source = (Path(labels.__file__).parents[2] / "factor_zoo.py").read_text(encoding="utf-8")
    spec = next(node.value for node in ast.parse(source).body
                if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "SPEC")
    keys = [key.value for key in spec.keys]
    classification = spec.values[keys.index("classification")]
    return {key.value for key in classification.keys}


def test_every_frozen_factor_classification_has_a_name_and_meaning():
    assert set(labels.FACTOR_CLASSIFICATIONS) == frozen_classifications()
    for code in labels.FACTOR_CLASSIFICATIONS:
        label, meaning = labels.factor_classification(code)
        assert "_" not in label and meaning
    assert labels.factor_classification("indicio")[0] == "Indicio no significativo"
    assert "p Holm ≥ 0,05" in labels.factor_classification("indicio")[1]
    assert labels.factor_classification("unknown") == ("unknown", "")


def test_families_known_by_prefix_or_left_as_typed():
    assert labels.family("stat_4") == "STAT-4 · empresas fuera del S&P 500"
    assert labels.family("blind_validation_3") == "Validación ciega n.º 3"
    assert labels.family("retrospective_v1_9b8c23744b39") == "Auditoría retrospectiva V1 (9b8c2374)"
    assert labels.family("mi familia") == "mi familia"
    assert labels.family(None) is None


def test_gate_failures_in_words():
    assert labels.failure("ic_not_positive_after_holm") == "IC no positivo tras la corrección Holm"
    assert labels.failure("base_2021-25_insufficient_or_nonpositive") == (
        "Escenario base 2021-25: muestra insuficiente o resultado no positivo")
    assert labels.failure("stress_insufficient_or_lower_bound_nonpositive") == (
        "Escenario de estrés: muestra insuficiente o cota inferior no positiva")
    assert labels.failure("other_code") == "other_code"


def test_every_published_family_and_failure_has_a_name():
    ledger = json.loads((Path(labels.__file__).parents[5] / "docs" / "search-ledger" / "ledger.json")
                        .read_text(encoding="utf-8"))
    rows = ledger["legacy_entries"] + ledger["additional_observed_records"]
    for row in rows:
        assert "_" not in labels.family(row["family"])
        for code in row["failures"] or []:
            assert "_" not in labels.failure(code)
