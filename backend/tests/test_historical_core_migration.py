"""Accredited-period context moved from historical_pit to identity without changing its published behaviour."""

import ast
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

from gabi import historical_pit, identity
from gabi.domain.research import periods
from gabi.infrastructure.storage import reviewed_resources

REFERENCE = json.loads((Path(__file__).parent / "fixtures/historical_core_migration.json").read_text(encoding="utf-8"))
DAYS = ["2009-12-31", "2010-01-04", "2015-12-31", "2016-01-04", "2020-06-30", "2025-10-01", "2026-01-02"]


def captured() -> dict:
    namespace = {"historical_period": periods, "date": date, "contextmanager": contextmanager, "Iterator": Iterator}
    for node in ast.parse(REFERENCE["historical_pit"]).body:
        if isinstance(node, ast.FunctionDef) and node.name in {"accredited_periods", "active_periods", "period_for", "covers"} \
                or isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "_active":
            exec(ast.get_source_segment(REFERENCE["historical_pit"], node), namespace)
    # get_source_segment omits decorators; restore the captured @contextmanager.
    namespace["accredited_periods"] = contextmanager(namespace["accredited_periods"])
    return namespace


@pytest.mark.parametrize("keys", [None, ("2010-2015",), ("2016-2025",), ("2010-2015", "2016-2025"), ()])
def test_period_context_matches_capture(keys):
    old = captured()

    def observe(module):
        return [module["active_periods"]() if isinstance(module, dict) else module.active_periods(),
                *[(day, (module["covers"] if isinstance(module, dict) else module.covers)(day),
                   getattr((module["period_for"] if isinstance(module, dict) else module.period_for)(day), "key", None))
                  for day in DAYS]]

    if keys is None:
        assert observe(historical_pit) == observe(old)
        return
    with old["accredited_periods"](*keys):
        expected = observe(old)
    with historical_pit.accredited_periods(*keys):
        assert observe(historical_pit) == expected
        assert identity.active_accredited_periods() == tuple(periods.get(key) for key in keys)
        assert identity._reader().periods == identity.active_accredited_periods()
    assert historical_pit.active_periods() == ("2010-2015",)


def test_context_is_restored_after_errors_and_shared_with_identity():
    with pytest.raises(RuntimeError), identity.accredited_periods("2016-2025"):
        assert historical_pit.covers("2020-06-30")
        raise RuntimeError("boom")
    assert historical_pit.active_periods() == ("2010-2015",) and not historical_pit.covers("2020-06-30")
    assert historical_pit.accredited_periods is identity.accredited_periods


def test_reviewed_ledgers_are_read_once_from_the_package():
    from gabi import historical_ticker_corrections, membership_extension

    assert historical_ticker_corrections.identity_nominations is reviewed_resources.identity_nominations
    assert membership_extension.LEDGER_PATH == reviewed_resources.MEMBERSHIP_LEDGER
    assert membership_extension.reviewed_through() == reviewed_resources.membership_ledger()["verified_through"]
    assert all(path.is_file() for path in reviewed_resources.NOMINATION_PATHS)
    assert reviewed_resources.identity_nominations()
