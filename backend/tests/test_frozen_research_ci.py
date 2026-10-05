import json

import pytest

from gabi.infrastructure import frozen_research as ci


def copy_engines(root, endings="\n"):
    for relative in ci.FROZEN:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (ci.BACKEND / relative).read_text(encoding="utf-8")
        target.write_bytes(text.replace("\n", endings).encode("utf-8"))


@pytest.mark.parametrize("endings", ["\n", "\r\n"])
def test_frozen_engines_match_published_hashes_on_both_platforms(tmp_path, endings):
    copy_engines(tmp_path, endings)
    ci.verify_frozen(tmp_path)


def test_a_changed_engine_cannot_keep_its_lint_type_exceptions(tmp_path):
    copy_engines(tmp_path)
    path = tmp_path / next(iter(ci.FROZEN))
    path.write_text(path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="engine changed"):
        ci.verify_frozen(tmp_path)


def test_exact_baseline_normalizes_paths_but_never_other_diagnostics():
    baseline = ci.load_baseline()
    actual = [{**record, "file": record["file"].replace("/", "\\")} for record in baseline[::-1]]
    assert ci.diagnostic_differences(actual, baseline) == ({}, {})
    actual[0] = {**actual[0], "message": "a different type error"}
    added, removed = ci.diagnostic_differences(actual, baseline)
    assert sum(added.values()) == sum(removed.values()) == 1
    actual = baseline + [{**baseline[0], "file": "src/gabi/repurchase_cash_strategy.py"}]
    added, removed = ci.diagnostic_differences(actual, baseline)
    assert sum(added.values()) == 1 and not removed
    added, removed = ci.diagnostic_differences([], baseline)
    assert not added and sum(removed.values()) == 25  # disabling mypy must fail


def test_baseline_cannot_expand_to_mutable_modules(tmp_path):
    folder = tmp_path / ".github"
    folder.mkdir()
    baseline = ci.load_baseline()
    baseline[0]["file"] = "src/gabi/repurchase_cash_strategy.py"
    (folder / "mypy-baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    with pytest.raises(ValueError, match="archived-engine diagnostics"):
        ci.load_baseline(tmp_path)


@pytest.mark.parametrize("change", ["none", "added", "disabled"])
def test_typecheck_exit_code_requires_full_check_and_only_exact_debt(monkeypatch, capsys, change):
    from mypy import api

    records = ci.load_baseline()
    if change == "added":
        records.append({**records[0], "file": "src/gabi/scoring.py", "message": "new error"})
    if change == "disabled":
        records = []

    def run(arguments):
        assert arguments == ["--config-file", str(ci.BACKEND / "pyproject.toml"),
                             "--output=json", str(ci.BACKEND / "src")]
        return "\n".join(json.dumps(record) for record in records), "", 1 if records else 0

    monkeypatch.setattr(api, "run", run)
    assert ci.typecheck() == (0 if change == "none" else 1)
    output = capsys.readouterr()
    if change == "added":
        assert "new error" in output.err
    if change == "disabled":
        assert "diagnostics changed/missing" in output.err
