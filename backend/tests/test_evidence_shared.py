"""#342: the catalogue, the common trace and each factor's studies are sanitized once per assessment; every
company's evidence stays exactly the same, keys and order included."""
from copy import deepcopy
from datetime import date

import numpy as np
import pandas as pd
import pytest
from test_evidence_confidence import NOW, frame, scoring, synthetic_catalogue

from gabi import evidence_catalog as catalogue
from gabi.application.market.evidence_assessment import build_evidence
from gabi.domain.market import evidence
from gabi.domain.research.live_ledger import safe


def _rich_catalogue():
    """Synthetic studies with the values safe() rewrites: numpy scalars, NaN, dates, tuples, int keys."""
    cat = synthetic_catalogue()
    metrics = list(cat["factors"])
    for position, metric in enumerate(metrics):
        cat["factors"][metric].update(
            windows={"36m": np.float64(.02), "60m": float("nan")},
            sector_stability={1: (np.int64(3), None)},
            size_stability={"small": {"ic": np.float64(-.01), "date": date(2024, 1, 2)}},
            sic_division_stability={f"D{position}": {"ic": np.float32(.5), "n": np.int64(10)}})
    del cat["factors"][metrics[-1]]  # A scored metric absent from the catalogue keeps the plain path.
    cat["tail"] = {"p": np.float64(.3), "when": pd.Timestamp("2024-01-01")}
    cat["placebos"]["values"] = [np.float64(1.5), float("inf")]
    return cat


def _identical(left, right):
    assert left == right
    assert list(left) == list(right)
    for one, other in zip(left["factors"], right["factors"], strict=True):
        assert list(one) == list(other)
    assert list(left["trace"]) == list(right["trace"])


@pytest.mark.parametrize("make", [synthetic_catalogue, _rich_catalogue, catalogue.load])
def test_shared_sanitizing_gives_the_same_evidence_for_every_company(make):
    cat, table = make(), frame()
    trace = {"model_version": "exact-model", "weights": {"value": np.float64(.25)}, "sources": cat.get("sources", {})}
    shared = evidence.sanitized_shared(cat, trace)
    before = deepcopy(cat)
    for symbol, row in table.iterrows():
        arguments = {"catalogue": cat, "quality": {"fresh": True}, "stability": {"top20_inclusion": np.float64(1.)},
                     "trace": {**trace, "symbol": symbol}, "model_matches": True}
        _identical(evidence.assess(row, scoring.DEFAULT_WEIGHTS, **arguments, shared=shared),
                   evidence.assess(row, scoring.DEFAULT_WEIGHTS, **arguments))
    assert safe(cat) == safe(before)  # Nothing in the catalogue was changed.


def test_build_evidence_matches_the_per_company_assessment():
    cat, table = _rich_catalogue(), frame()

    def stability(frame, weights):
        return {}, pd.DataFrame(), pd.DataFrame({"top20_inclusion": [1.] * len(frame)}, index=frame.index)

    result = build_evidence(table, scoring.DEFAULT_WEIGHTS, now=NOW, market_date="2024-01-10", catalogue=cat,
                            matching=True, metadata={"model_version": "exact-model"}, analyze_stability=stability,
                            model_id="GABI-MF-v1", benchmark="SPY")
    for symbol in table.index:
        trace = dict(result[symbol]["trace"])
        expected = evidence.assess(table.loc[symbol], scoring.DEFAULT_WEIGHTS, catalogue=cat,
                                   quality=result[symbol]["quality"], stability={"top20_inclusion": 1.},
                                   trace=trace, model_matches=True)
        _identical(result[symbol], expected)


@pytest.mark.parametrize("change", ["value", "extra", "no_symbol", "catalogue"])
def test_a_trace_or_catalogue_that_is_not_the_common_one_is_refused(change):
    cat, common = synthetic_catalogue(), {"model_version": "exact-model", "weights": {"value": .25}}
    shared = evidence.sanitized_shared(cat, common)
    trace = {**common, "symbol": "F00"}
    if change == "value":
        trace["weights"] = {"value": .25}  # Equal but not the same object: refused, never assumed equal.
    elif change == "extra":
        trace["extra"] = 1
    elif change == "no_symbol":
        del trace["symbol"]
    with pytest.raises(ValueError, match="comunes"):
        evidence.assess(frame().iloc[0], scoring.DEFAULT_WEIGHTS,
                        catalogue=deepcopy(cat) if change == "catalogue" else cat, quality={"fresh": True},
                        stability={}, trace=trace, model_matches=True, shared=shared)
