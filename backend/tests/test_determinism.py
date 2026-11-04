"""Determinism (#296): explicit seeds, a fixed integration generator and the ranking fingerprint."""

import numpy as np
import pandas as pd
import pytest

from gabi.domain.research.statistics import bootstrap_sharpe_ci
from gabi.infrastructure.statistics.prospective import ScipyNormalCDF

RETURNS = pd.Series(np.random.default_rng(7).normal(0.0005, 0.01, 300))


def test_the_bootstrap_needs_an_explicit_seed_and_repeats_with_it():
    with pytest.raises(TypeError):
        bootstrap_sharpe_ci(RETURNS, periods_per_year=252, n_boot=50)
    with pytest.raises(TypeError):
        bootstrap_sharpe_ci(RETURNS, periods_per_year=252, n_boot=50, seed=None)
    first = bootstrap_sharpe_ci(RETURNS, periods_per_year=252, n_boot=50, seed=11)
    assert bootstrap_sharpe_ci(RETURNS, periods_per_year=252, n_boot=50, seed=11) == first


def test_the_normal_integration_is_fixed_by_default_and_unseeded_only_on_request():
    covariance = np.array([[1.0, 0.6, 0.3], [0.6, 1.0, 0.6], [0.3, 0.6, 1.0]])
    values = np.array([1.2, 1.5, 1.8])
    # Two fresh default instances give the same number: the generator is fixed, not shared state.
    assert ScipyNormalCDF()(values, covariance) == ScipyNormalCDF()(values, covariance)
    assert ScipyNormalCDF(rng=None).rng is None  # The published-plan commands keep SciPy's own integration.
    seeded = ScipyNormalCDF(rng=np.random.default_rng(3))
    assert 0 < seeded(values, covariance) < 1


# Reference fingerprints of the ranking on the fixed fixture (market_fixture), one per model version.
# A change here is a change of result: update it only on purpose, saying why in the commit.
# GABI-MF-v3 equals v2 on this fixture because it holds no implausible value (#295).
RANKING_FINGERPRINTS = {
    "GABI-MF-v1": "6b252e6e2ee598c4c0b07ae0054610628974f52cf70d0c98c1d32f1728a3aa90",
    "GABI-MF-v2": "058fe775e149f2fb7c9ea444ec4fd2eefdcc4938c52a6d218e4868010dad1482",
    "GABI-MF-v3": "058fe775e149f2fb7c9ea444ec4fd2eefdcc4938c52a6d218e4868010dad1482",
}


def ranking_fingerprint(version, root) -> str:
    """SHA-256 of the ordered (symbol, composite score to 9 decimals) pairs."""
    import hashlib
    import json

    from market_fixture import TODAY

    from gabi.infrastructure.legacy.market import calculators, model_policy
    from gabi.infrastructure.settings import Settings
    from gabi.infrastructure.storage.market import ReadOnlyMarket

    market = ReadOnlyMarket(Settings(root), calculators(version.technical, input_checks=version.input_checks),
                            model_policy(version), version.benchmark_symbol, version.risk_free_rate,
                            metrics_version=version.metrics_version)
    try:
        table = market.ranking(dict(version.weights), TODAY).table
    finally:
        market.close()
    rows = [[str(symbol), None if pd.isna(score) else round(float(score), 9)]
            for symbol, score in table["composite_score"].items()]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def test_the_ranking_of_every_model_version_keeps_its_reference_fingerprint(tmp_path):
    from market_fixture import seed_fixture

    from gabi.infrastructure.model_versions import VERSIONS

    seed_fixture(tmp_path)
    assert set(RANKING_FINGERPRINTS) == set(VERSIONS), "Una versión nueva necesita su huella de referencia."
    found = {model_id: ranking_fingerprint(version, tmp_path) for model_id, version in VERSIONS.items()}
    assert found == RANKING_FINGERPRINTS, (
        "El ranking ha cambiado sobre los datos de prueba. Si el cambio es intencionado, actualiza "
        "RANKING_FINGERPRINTS y explica el motivo en el commit.")
    # The same call twice gives the same fingerprint.
    assert ranking_fingerprint(VERSIONS["GABI-MF-v1"], tmp_path) == found["GABI-MF-v1"]
