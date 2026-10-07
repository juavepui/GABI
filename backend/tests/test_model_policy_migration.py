"""Reference model identity, status and banner for the frozen hypothesis."""

import json
from pathlib import Path

import pytest

from gabi.domain.market import model_policy
from gabi.infrastructure.legacy.market import model_policy as create_policy

REFERENCE = json.loads((Path(__file__).parent / "fixtures/model_policy_migration.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", REFERENCE["cases"])
def test_model_policy_reference(case):
    weights = dict(case["weights"])
    assert model_policy.weights_match_frozen(weights) == case["matches"]
    assert model_policy.model_status(weights, live_forward_active=case["live"]) == case["status"]
    assert model_policy.experimental_banner_message(weights) == case["banner"]
    assert weights == case["weights"]


def test_modern_policy_has_no_file_or_legacy_configuration_dependency(monkeypatch):
    from gabi import app_mode

    def forbidden(*args, **kwargs):
        raise AssertionError("implicit file access")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(app_mode, "FROZEN_WEIGHTS", {"other": 1.0})
    policy = create_policy()
    assert policy.frozen_weights == {"value": .3, "quality": .35, "momentum": .25, "risk": .1}
    assert policy.matches(policy.frozen_weights)
    assert policy.status(policy.frozen_weights, live_forward_active=True) == "LIVE_FORWARD"
    with pytest.raises(TypeError):
        model_policy.FROZEN_WEIGHTS["value"] = 1.0


def test_legacy_facade_keeps_explicit_compatibility_overrides(monkeypatch):
    from gabi import app_mode

    weights = {"value": .5, "quality": .3, "momentum": .1, "risk": .1}
    monkeypatch.setattr(app_mode, "FROZEN_WEIGHTS", weights)
    assert app_mode.weights_match_frozen(weights)
    assert app_mode.model_status(weights) == "FROZEN"
    assert app_mode.experimental_banner_message(weights) is None
