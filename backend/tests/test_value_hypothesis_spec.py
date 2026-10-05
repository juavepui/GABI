"""#43: the preregistered value specification keeps its published fingerprint after ADR 0002."""
import json
import shutil

from gabi import config
from gabi import value_hypothesis as cited
from gabi.domain.research import value_hypothesis as hypothesis
from gabi.infrastructure.legacy.value_hypothesis import preregister, specification

PUBLISHED = config.BASE_DIR / "docs" / "value-hypothesis" / "preregistro.json"


def test_cited_name_domain_and_bridge_reproduce_the_sealed_fingerprint():
    record = json.loads(PUBLISHED.read_text(encoding="utf-8"))
    assert cited.spec_hash() == hypothesis.spec_hash(specification()) == record["sha256"]
    assert specification() == record["spec"]


def test_published_plan_follows_from_its_thresholds():
    record = json.loads(PUBLISHED.read_text(encoding="utf-8"))
    from gabi import prospective_plan

    bounds = [look["umbral_z"] for look in record["plan_secuencial"]["looks"]]
    assert hypothesis.sequential_plan(bounds, prospective_plan.obrien_fleming_spending) == record["plan_secuencial"]


def test_existing_preregistration_is_checked_never_rewritten(tmp_path):
    shutil.copyfile(PUBLISHED, tmp_path / "preregistro.json")
    before = (tmp_path / "preregistro.json").read_bytes()
    assert preregister(tmp_path)["sha256"] == json.loads(before)["sha256"]
    assert (tmp_path / "preregistro.json").read_bytes() == before
