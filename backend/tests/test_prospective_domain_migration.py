"""Original prospective plans and hash/JSON bytes, with integration and output ports."""

import argparse
import hashlib
import json
import types
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import norm

from gabi.application.research.prospective_plan import publish_plan
from gabi.domain.research import prospective_plan as plans
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.prospective_plans import FileProspectivePlans

REFERENCE = json.loads((Path(__file__).parent / "fixtures/prospective_plan_migration.json").read_text(encoding="utf-8"))


def independent_cdf(values, covariance):
    return float(np.prod(norm.cdf(values)))


@pytest.mark.parametrize("case", REFERENCE["boundaries"])
def test_boundary_reference(case):
    assert plans.boundaries(case["fractions"], cdf=independent_cdf) == pytest.approx(case["expected"], rel=1e-12, abs=1e-14)


@pytest.mark.parametrize("case", REFERENCE["spending"])
def test_spending_reference(case):
    assert plans.obrien_fleming_spending(case["fraction"]) == pytest.approx(case["value"], rel=1e-12, abs=1e-14)


def test_record_hashes_retain_original_json_normalization():
    assert plans.plan_hash(REFERENCE["fixed"]) == REFERENCE["fixed_hash"]
    assert plans.plan_hash(REFERENCE["sequential"]) == REFERENCE["sequential_hash"]
    assert plans.json_value({1: [float("nan"), float("inf")]}) == {1: [None, None]}


def test_whole_plan_and_published_bytes_match_original(tmp_path):
    source = REFERENCE["original_source"]
    assert hashlib.sha256(source.encode()).hexdigest() == REFERENCE["source_sha256"]
    original = types.ModuleType("gabi._prospective_reference")
    original.__package__ = "gabi"
    exec(compile(source, "original_prospective_plan", "exec"), original.__dict__)

    class IndependentNormal:
        def __init__(self, mean, cov):
            self.cov = cov

        def cdf(self, values):
            return independent_cdf(values, self.cov)

    original.multivariate_normal = IndependentNormal
    original.OUTPUT = tmp_path / "old"
    assert plans.plan(cdf=independent_cdf) == original.plan()
    assert plans.gabi_blind_plan() == original.gabi_blind_plan()
    writer = FileProspectivePlans(tmp_path / "new")
    sequential = publish_plan(plans.plan(cdf=independent_cdf), writer, name="plan.json")
    fixed = publish_plan(plans.gabi_blind_plan(), writer, name="gabi-id1.json")
    assert sequential == original.write()
    assert fixed == original.write_gabi_blind_plan()
    for name in ("plan.json", "gabi-id1.json"):
        assert (tmp_path / "new" / name).read_bytes() == (tmp_path / "old" / name).read_bytes()


def test_plan_preview_has_no_io_and_does_not_modify_fractions(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("file access")

    monkeypatch.setattr(Path, "open", forbidden)
    fractions = [.3, .6, 1.]
    plans.boundaries(fractions, cdf=independent_cdf)
    assert fractions == [.3, .6, 1.]
    assert plans.gabi_blind_plan()["look"] == "2029-09-21"
    with pytest.raises(TypeError):
        plans.boundaries(fractions)


def test_cli_preview_and_write_are_explicit(tmp_path, capsys):
    from gabi_cli.research.bootstrap import prospective_plan

    settings = Settings(tmp_path / "data")
    args = argparse.Namespace(gabi=True, write=False, output=tmp_path / "output")
    prospective_plan(settings, args)
    assert json.loads(capsys.readouterr().out) == {"plan": plans.gabi_blind_plan()}
    assert not args.output.exists() and not settings.data_dir.exists()
    args.write = True
    prospective_plan(settings, args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["sha256"] == plans.plan_hash(payload["plan"])
    assert json.loads((args.output / "gabi-id1.json").read_text(encoding="utf-8")) == payload
    assert not settings.data_dir.exists()


def test_unknown_output_name_never_creates_a_file(tmp_path):
    with pytest.raises(ValueError):
        FileProspectivePlans(tmp_path / "new").save("../other.json", {})
    assert not (tmp_path / "new").exists()
