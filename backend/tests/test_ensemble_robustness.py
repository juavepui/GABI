import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gabi import config
from gabi.application.research import ensemble_robustness as use_case
from gabi.domain.research import ensemble_robustness as ens
from gabi.infrastructure.storage import ensemble_inputs

PREREGISTRATION = config.BASE_DIR / "docs" / "ensemble-robustness" / "preregistro.json"


def spec() -> dict:
    return json.loads(PREREGISTRATION.read_text(encoding="utf-8"))["spec"]


def frame(rows: list[dict]) -> pd.DataFrame:
    table = pd.DataFrame(rows)
    return table.set_index("symbol", drop=False)


def test_sealed_preregistration_matches_its_fingerprint_and_the_use_case():
    record = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    assert ens.fingerprint(record["spec"]) == record["sha256"] == use_case.SEALED_SPEC_SHA256
    assert record["spec"]["aggregation"]["weight_optimization"] == "prohibida"
    assert record["spec"]["demonstrated"] is False


def test_selection_caps_divisions_breaks_ties_by_symbol_and_keeps_cash():
    rules = {"portfolios": {"slots": 3, "maximum_per_division": 1}}
    table = frame([{"symbol": "B", "division": "D", "entity_id": "b"},
                   {"symbol": "A", "division": "D", "entity_id": "a"},
                   {"symbol": "C", "division": "E", "entity_id": "c"}])
    chosen, cash = ens.select(pd.Series([1.0, 1.0, 0.5], index=table.index), table, rules)
    assert chosen == frozenset({"a", "c"})  # A wins the tie with B; D is capped at one
    assert cash == 1


def synthetic_dates(rng: np.random.Generator, dates: list[str], n: int = 50) -> pd.DataFrame:
    columns = ens.metric_columns(spec())
    rows = []
    for date in dates:
        for i in range(n):
            row = {"fecha": date, "symbol": f"S{i:03d}", "entity_id": f"E{i:03d}", "division": "DEFGHI"[i % 6]}
            row.update(dict(zip(columns, rng.uniform(0, 1, len(columns)), strict=True)))
            if i % 7 == 0:
                row["pb_pct"] = np.nan  # value still available with two metrics
            if i % 11 == 0:
                row["expectations_gap_pct"] = np.nan  # outside U_t
            rows.append(row)
    table = pd.DataFrame(rows)
    blocks = ens.blocks(table, spec())
    for block in ens.BLOCKS:
        table[block] = blocks[block]
        table[block + "_available"] = table[spec()["components"]["metrics"][block]].notna().sum(axis=1)
    return table


def test_published_blocks_must_be_reproduced_before_anything_else():
    table = synthetic_dates(np.random.default_rng(1), ["2011-07-02"])
    ens.check_published_blocks(table, spec())
    table.loc[3, "quality"] += 1e-9
    with pytest.raises(ValueError, match="quality"):
        ens.check_published_blocks(table, spec())


def test_zero_noise_keeps_every_selection_and_draws_are_shared():
    table = ens.universe(synthetic_dates(np.random.default_rng(2), ["2011-07-02"])).set_index("symbol", drop=False)
    _, base = ens.date_metrics(table, pd.DataFrame(np.nan, index=table.index, columns=[
        "volatility", "max_drawdown", "beta_calc", "market_cap"]), spec())
    small = {**spec(), "endpoints": {"P2_noise_persistence": {"replicates": 3}}}
    assert ens.noise_persistence(table, small, base, np.random.default_rng(0), 0.0) == dict.fromkeys(ens.SIGNALS, 1.0)
    noisy = ens.noise_persistence(table, small, base, np.random.default_rng(0), 0.5)
    assert all(0 <= value <= 1 for value in noisy.values())


def test_array_noise_path_equals_the_pandas_definition():
    table = ens.universe(synthetic_dates(np.random.default_rng(5), ["2011-07-02"], n=90)).set_index(
        "symbol", drop=False)
    draws = np.random.default_rng(6).uniform(-.1, .1, size=(len(table), len(ens.metric_columns(spec()))))
    reference = ens.signals(ens.blocks(table, spec(), noise=draws), spec())
    fast = ens._fast_signals(table[ens.metric_columns(spec())].to_numpy(dtype=float) + draws, spec())
    for position, name in enumerate(ens.SIGNALS):
        assert np.array_equal(reference[name].to_numpy(), fast[position], equal_nan=True)
        assert ens._fast_select(fast[position], table, spec()) == ens.select(reference[name], table, spec())[0]


def test_bootstrap_refuses_gaps_and_brackets_a_constant_difference():
    table = pd.DataFrame({"ENS": [0.2] * 12, "value": [0.5] * 12, "quality": [0.4] * 12, "expectations": [0.3] * 12})
    intervals = ens.bootstrap_differences(table, spec(), 7)
    assert intervals["value"] == pytest.approx({"observed": -0.3, "low": -0.3, "high": -0.3})
    table.loc[4, "quality"] = np.nan
    assert ens.bootstrap_differences(table, spec(), 7) is None


@pytest.mark.parametrize(("redundancy", "dominance", "p1_high", "p2_low", "label"), [
    (0.85, 0.2, -1, 1, "redundante"),
    (0.10, 0.80, -1, 1, "equivalente_a_un_componente"),
    (0.10, 0.20, -1, 1, "mas_robusto"),
    (0.10, 0.20, -1, -1, "parcial"),
    (0.10, 0.20, 1, -1, "sin_mejora"),
])
def test_decision_rule_is_the_preregistered_one(redundancy, dominance, p1_high, p2_low, label):
    p1 = {block: {"high": p1_high} for block in ens.BLOCKS}
    p2 = {block: {"low": p2_low} for block in ens.BLOCKS}
    decision = ens.decide({"value_quality": redundancy}, dominance, p1, p2)
    assert decision["label"] == label
    assert decision["prospective_v1_allowed"] is (label != "redundante")
    assert ens.decide({"value_quality": 0.1}, 0.2, None, p2)["label"] == "no_estimable"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def synthetic_root(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    (root / "docs" / "ensemble-robustness").mkdir(parents=True)
    shutil.copy(PREREGISTRATION, root / "docs" / "ensemble-robustness" / "preregistro.json")
    dates = [date for year in range(2011, 2026) for month in (1, 4, 7, 10)
             if "2011-07-02" <= (date := f"{year}-{month:02d}-02") <= "2025-07-02"]
    assert len(dates) == 57 and dates[0] == "2011-07-02"
    scores = synthetic_dates(np.random.default_rng(3), dates)
    discovery = root / "docs" / "strategy-discovery"
    discovery.mkdir(parents=True)
    scores.to_csv(discovery / "scores.csv", index=False, lineterminator="\n")
    (discovery / "resultado.json").write_text(json.dumps(
        {"artifacts_sha256": {"scores.csv": file_hash(discovery / "scores.csv")}}), encoding="utf-8")
    rankings = root / "data" / "revalidation_2011_2025" / "acreditado-38"
    rankings.mkdir(parents=True)
    rng = np.random.default_rng(4)
    hashes = {}
    for date in dates:
        risk = scores.loc[scores.fecha == date, ["symbol", "entity_id"]].assign(
            volatility=rng.uniform(.1, .5, 50), max_drawdown=rng.uniform(-.6, -.1, 50),
            beta_calc=rng.uniform(.5, 1.5, 50), market_cap=rng.uniform(1e9, 1e11, 50), retorno=99.0)
        risk.to_csv(rankings / f"ranking-{date}.csv", index=False, lineterminator="\n")
        (rankings / f"forward-{date}.csv").write_text("symbol,retorno\nS000,99\n", encoding="utf-8")
        hashes[f"data\\revalidation_2011_2025\\acreditado-38\\ranking-{date}.csv"] = file_hash(
            rankings / f"ranking-{date}.csv")
        hashes[f"data\\cross_section_test\\forward-{date}.csv"] = "0" * 64
    zoo = {"inputs_sha256": hashes}
    (root / "docs" / "factor-zoo").mkdir(parents=True)
    (root / "docs" / "factor-zoo" / "resultado.json").write_text(json.dumps(zoo), encoding="utf-8")
    return root, ens.fingerprint(zoo)


def test_end_to_end_reads_only_declared_files_and_reproduces(synthetic_root, tmp_path, monkeypatch):
    root, zoo_sha = synthetic_root
    sealed = ens.noise_persistence

    def fewer_replicates(frame, spec, base, rng, delta):  # speed only; the rules are tested above
        rules = {**spec["endpoints"]["P2_noise_persistence"], "replicates": 4}
        return sealed(frame, {**spec, "endpoints": {"P2_noise_persistence": rules}}, base, rng, delta)

    monkeypatch.setattr(ens, "noise_persistence", fewer_replicates)
    inputs = ensemble_inputs.PublishedEnsembleInputs(root, factor_zoo_sha256=zoo_sha)
    result, tables = use_case.analyze(inputs)
    opened = result["inputs"]["files_opened"]
    assert not any("forward-" in name or "quarterly" in name or ".db" in name for name in opened)
    assert result["returns_read"] is False and result["n_evaluable"] == 57
    assert "retorno" not in "".join(table.to_csv() for table in tables.values())
    assert set(tables["ruido.csv"].delta) == {0.05, 0.02, 0.10}
    assert len(tables["rotacion.csv"]) == 56
    published = root / "docs" / "ensemble-robustness"
    saved = ensemble_inputs.save(published, result, tables)
    with pytest.raises(FileExistsError):
        ensemble_inputs.save(published, result, tables)
    again = ensemble_inputs.verify(root, published, tmp_path / "check", factor_zoo_sha256=zoo_sha)
    assert again["sha256"] == saved["sha256"]
    (published / "rotacion.csv").write_text("alterado\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rotacion.csv"):
        ensemble_inputs.verify(root, published, tmp_path / "check2", factor_zoo_sha256=zoo_sha)


def test_inputs_reject_forbidden_or_altered_sources(synthetic_root):
    root, zoo_sha = synthetic_root
    inputs = ensemble_inputs.PublishedEnsembleInputs(root, factor_zoo_sha256=zoo_sha)
    with pytest.raises(PermissionError):
        inputs._path("data/cross_section_test/forward-2011-07-02.csv")
    with pytest.raises(PermissionError, match="fuera"):
        inputs.risk("2010-01-02", ["volatility"])
    scores = root / "docs" / "strategy-discovery" / "scores.csv"
    scores.write_text(scores.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="#60"):
        inputs.scores(spec()["inputs"]["scores"]["columns"])
    with pytest.raises(ValueError, match="#48"):
        ensemble_inputs.PublishedEnsembleInputs(root, factor_zoo_sha256="0" * 64).risk("2011-07-02", ["volatility"])
