"""Versioned operating model (ADR 0008): GABI-MF-v1 keeps its exact values and rules."""

import ast
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from gabi import config
from gabi.application.administration.model import LocalModel, ModelQueries
from gabi.domain.market import model_policy
from gabi.domain.market.model_version import ModelVersion
from gabi.infrastructure import model_versions
from gabi.infrastructure.legacy.market import model_policy as create_policy
from gabi.infrastructure.model_versions import GABI_MF_V1, active_model

SRC = Path(__file__).resolve().parents[1] / "src"
REFERENCE = json.loads((Path(__file__).parent / "fixtures/model_policy_migration.json").read_text(encoding="utf-8"))
NEW = replace(GABI_MF_V1, model_id="GABI-MF-v2", label="Nueva versión", sealed_hypothesis=False,
              weights={"value": .25, "quality": .40, "momentum": .25, "risk": .10})


def test_v1_declares_the_values_of_the_sealed_snapshot():
    assert dict(GABI_MF_V1.weights) == config.DEFAULT_WEIGHTS == dict(model_policy.FROZEN_WEIGHTS)
    assert asdict(GABI_MF_V1.technical) == {
        "sma_short": config.SMA_SHORT, "sma_long": config.SMA_LONG, "rsi_period": config.RSI_PERIOD,
        "momentum_short_days": config.MOMENTUM_SHORT_DAYS, "momentum_long_days": config.MOMENTUM_LONG_DAYS}
    assert (GABI_MF_V1.benchmark_symbol, GABI_MF_V1.risk_free_rate) == (config.BENCHMARK_SYMBOL, config.RISK_FREE_RATE)
    assert (GABI_MF_V1.model_id, GABI_MF_V1.label) == (model_policy.FROZEN_MODEL_ID, model_policy.FROZEN_LABEL)
    assert GABI_MF_V1.sealed_hypothesis and active_model() is GABI_MF_V1


@pytest.mark.parametrize("case", REFERENCE["cases"])
def test_v1_policy_keeps_the_reference_rules(case):
    policy = create_policy(GABI_MF_V1)
    assert policy.matches(dict(case["weights"])) == case["matches"]
    assert policy.status(dict(case["weights"]), live_forward_active=case["live"]) == case["status"]


@pytest.mark.parametrize("live", [False, True])
def test_a_new_version_has_its_own_identity_and_no_inherited_evidence(live):
    policy = create_policy(NEW)
    reader = type("Reader", (), {"local_model": lambda self: LocalModel("INVESTOR", {}, weak_tracking=live)})()
    state = ModelQueries(reader, policy).model()
    assert (state.model_id, state.status, state.weights) == ("GABI-MF-v2", "EXPERIMENTAL", dict(NEW.weights))
    assert state.matches_frozen and not state.independent_advantage_demonstrated
    assert not create_policy(GABI_MF_V1).matches(dict(NEW.weights))


@pytest.mark.parametrize("change", [
    {"model_id": "EXPERIMENTAL"}, {"model_id": ""}, {"benchmark_symbol": ""},
    {"weights": {"value": .5, "quality": .5, "momentum": .5, "risk": -.5}},
    {"weights": {"value": .5, "quality": .5}}, {"risk_free_rate": float("nan")},
    {"technical": replace(GABI_MF_V1.technical, sma_short=0)},
])
def test_invalid_versions_are_rejected(change):
    with pytest.raises(ValueError):
        replace(NEW, **change)


def test_versions_are_immutable_and_unknown_ids_fail():
    with pytest.raises(TypeError):
        GABI_MF_V1.weights["value"] = 1.0  # type: ignore[index]
    with pytest.raises(ValueError, match="Unknown model version"):
        active_model("GABI-MF-v9")
    assert isinstance(GABI_MF_V1, ModelVersion)


@pytest.mark.parametrize("path", ["gabi/infrastructure/model_versions.py", "gabi/infrastructure/legacy/market.py",
                                  "gabi/domain/market/model_version.py"])
def test_the_active_model_path_does_not_read_the_sealed_config(path):
    tree = ast.parse((SRC / path).read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == "gabi"
                for alias in node.names}
    imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert "config" not in imported and "gabi.config" not in imported
    assert model_versions.ACTIVE_MODEL_ID in model_versions.VERSIONS
