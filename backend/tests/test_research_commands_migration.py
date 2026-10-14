"""Reproduction commands of #33, #35 and #44 under `gabi_cli research` (ADR 0002, #133).

The old ``python -m gabi.<module>`` entry points are captured in a fixture; each is run
next to the new subcommand with the engines replaced by recorders, so both must make the
same calls and print the same bytes. The published artifacts keep their recorded hashes.
"""

import ast
import contextlib
import io
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pandas as pd
import pytest

from gabi import config, storage
from gabi import factor_stability as fs
from gabi import historical_revalidation as hr
from gabi import historical_validation as hv
from gabi import smallmid_feasibility as sf
from gabi.domain.research import periods
from gabi.infrastructure.storage.historical_archive_schema import SCHEMA as ARCHIVE
from gabi.infrastructure.storage.identity_writes import SCHEMA as IDENTITY
from gabi_cli.research import bootstrap

REFERENCE = json.loads((Path(__file__).parent / "fixtures/research_commands_migration.json").read_text(encoding="utf-8"))
DOCS = Path(__file__).resolve().parents[2] / "docs"
REPORT = {"historical_validation": {"summary": {"ratio": 0.5, "missing": float("nan")}, "issue": 33}}


def captured(name: str, function: str, namespace: dict):
    """Compile one function of the captured module against ``namespace``."""
    source = REFERENCE[name]
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == function)
    exec(compile(ast.Module([node], []), f"captured_{name}", "exec"), namespace)
    return namespace[function]


def output(call) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        call()
    return buffer.getvalue()


def old_main(name: str, module, argv: list[str]) -> str:
    import argparse
    main = captured(name, "main", {**vars(module), "argparse": argparse, "json": json, "Path": Path})
    original = sys.argv
    sys.argv = [f"{name}.py", *argv]
    try:
        return output(main)
    finally:
        sys.argv = original


def new_main(command: str, argv: list[str]) -> str:
    return output(lambda: bootstrap.main([command, *argv]))


@pytest.mark.parametrize("argv", [[], ["--analysis-only"], ["--cache", "c", "--output", "o"]])
def test_historical_validation_command_matches_captured_entry_point(monkeypatch, argv):
    calls = []
    monkeypatch.setattr(hv, "run", lambda *args, **kwargs: calls.append((args, kwargs)) or REPORT)
    old = old_main("historical_validation", hv, argv)
    new = new_main("historical-validation", argv)
    assert new == old and '"missing": null' in new
    assert calls[0] == calls[1]
    assert calls[0][0][:2] == ((Path("c"), Path("o")) if "--cache" in argv else (hv.CACHE, hv.OUTPUT))


@pytest.mark.parametrize("argv", [["--summarize"], ["--prepare", "acreditado-38"], ["--evaluate", "operativo"],
                                  ["--analyze", "acreditado-38-continua"],
                                  ["--prepare", "operativo", "--evaluate", "operativo", "--analyze", "operativo",
                                   "--summarize"]])
def test_historical_revalidation_command_matches_captured_entry_point(monkeypatch, argv):
    calls = []
    long = {f"k{n}": "x" * 50 for n in range(200)}  # --summarize truncates at 4000 characters
    monkeypatch.setattr(hr, "prepare", lambda key: calls.append(("prepare", key)) or {"dates": [1, 2, 3]})
    monkeypatch.setattr(hr, "evaluate", lambda view, **kw: calls.append(("evaluate", view, kw)) or REPORT)
    monkeypatch.setattr(hr, "summarize", lambda: calls.append(("summarize",)) or long)
    old = old_main("historical_revalidation", hr, argv)
    half = len(calls)
    new = new_main("historical-revalidation", argv)
    assert new == old
    assert calls[:half] == calls[half:] and half


def test_revalidation_choices_are_the_protocol_ones():
    assert bootstrap.REVALIDATION_VARIANTS == sorted(hr.VARIANTS)
    assert bootstrap.REVALIDATION_VIEWS == sorted(hr.VIEWS)


@pytest.mark.parametrize("argv", [[], ["--sample"]])
def test_smallmid_feasibility_command_matches_captured_entry_point(monkeypatch, argv):
    calls = []
    monkeypatch.setattr(sf, "run", lambda **kw: calls.append(kw) or {"tasa": float("inf"), "fechas": {"2012": 3}})
    assert new_main("smallmid-feasibility", argv) == old_main("smallmid_feasibility", sf, argv)
    assert calls[0] == calls[1] == {"sample": bool(argv)}


def test_old_modules_have_no_entry_points_or_storage():
    for module in (hv, hr, sf):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "__main__" not in source and "argparse" not in source and "storage" not in vars(module)


def test_feasibility_year_is_the_captured_constant_query():
    node = next(n for n in ast.walk(ast.parse(REFERENCE["smallmid_feasibility"]))
                if isinstance(n, ast.Constant) and n.value == "SELECT '2025'")
    with closing(sqlite3.connect(":memory:")) as conn:
        assert max(int(r[0][:4]) for r in conn.execute(node.value)) == 2025
    assert "frames_ultimo_ano\"] = 2025" in Path(sf.__file__).read_text(encoding="utf-8")


def _prices(path: Path):
    frame = pd.DataFrame({c: [100.0, 101.0] for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]},
                         index=pd.to_datetime(["2015-01-02", "2015-01-05"]))
    config.DB_PATH = path
    storage.upsert_prices("SPY", frame)


def test_validation_benchmark_reads_the_redirected_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    _prices(tmp_path / "snapshot.db")
    expected = storage.get_prices("SPY")["adj_close"]
    monkeypatch.setattr(storage, "get_prices", lambda symbol: pytest.fail("storage facade"))
    calendar = type("Calendar", (), {"date_to_session": lambda self, d, direction: pd.Timestamp("2015-01-02"),
                                     "next_session": lambda self, d: pd.Timestamp("2015-01-02")})()
    monkeypatch.setattr(hv.xcals, "get_calendar", lambda name: calendar)
    seen = {}
    monkeypatch.setattr(hv, "_returns", lambda *args: seen.setdefault("spy", True) and {})
    monkeypatch.setattr(hv, "weights", lambda table, floats: ({}, 0))
    monkeypatch.setattr(hv, "_floats", lambda date: {})
    table = pd.DataFrame({"composite_score": [None], "score_coverage": [0.0], "price_source": [None]}, index=["AAA"])
    result = hv.benchmarks_by_period({"2015-01-02": table}, {"dates": ["2015-01-02"], "end": "2015-01-05"})
    assert result["spy"].iloc[0] == float(expected.loc["2015-01-02"] / expected.loc["2015-01-02"] - 1) == 0


def seed_freshness(path: Path) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(ARCHIVE + IDENTITY)
        source = periods.P2016.identity_source
        db.executemany("INSERT INTO historical_identity_intervals VALUES (?,?,?,?,?,?,?,?,?,?)", [
            (source, "AAA", "0000000001", "2016-01-01", "2020-01-01", "confirmed_historical_ticker", 1, None, None, "[]"),
            (source, "AAA", "0000000001", "2020-01-01", "2026-01-01", "confirmed_historical_ticker", 1, None, None, "[]"),
            (source, "BBB", "0000000002", "2016-01-01", "2024-01-01", "confirmed_historical_ticker", 1, None, None, "[]"),
            (source, "CCC", "0000000003", "2016-01-01", "2024-01-01", "rejected", 1, None, None, "[]"),
            ("other", "DDD", "0000000004", "2016-01-01", "2024-01-01", "confirmed_historical_ticker", 1, None, None, "[]"),
            (source, "EEE", "0000000005", "2016-01-01", "2017-01-01", "confirmed_historical_ticker", 1, None, None, "[]"),
        ])
        db.executemany("INSERT INTO entities VALUES (?,?,?,?)",
                       [(f"cik:000000000{n}", f"000000000{n}", None, "2026-01-01") for n in (1, 2, 5)])
        db.executemany("INSERT INTO entity_observations VALUES (?,?,?,?,?,?)", [
            ("cik:0000000001", "edgar_facts", "AAA", "a", json.dumps({"filed_date": "2025-10-01"}), "s"),
            ("cik:0000000002", "edgar_facts", "BBB", "b", json.dumps({"filed_date": "2015-02-01"}), "s"),
            ("cik:0000000002", "edgar_facts", "BBB", "c", json.dumps({"filed_date": "2016-02-01"}), "s"),
            ("cik:0000000005", "prices", "EEE", "d", json.dumps({"filed_date": "2016-12-01"}), "s"),
        ])


def test_stale_issuer_facts_match_captured_query(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    with pytest.raises(ValueError, match="Missing local identity tables"):
        hr.stale_issuer_facts()
    seed_freshness(tmp_path / "gabi.db")
    old = captured("historical_revalidation", "stale_issuer_facts", {"__package__": "gabi", "__name__": "gabi.captured"})
    assert hr.stale_issuer_facts() == old()
    assert {cik for cik, *_ in old()} == {"0000000002", "0000000005"}
    assert hr.stale_issuer_facts(10_000) == old(10_000) == [("0000000005", None, "2017-01-01")]


@pytest.mark.parametrize("folder, document, key", [
    ("historical-validation-2010-2015", "audit.json", ("historical_validation", "artifacts")),
    ("historical-revalidation-2011-2025", "summary.json", ("artifacts",)),
])
def test_published_artifacts_keep_their_hashes(folder, document, key):
    record = json.loads((DOCS / folder / document).read_text(encoding="utf-8"))
    for part in key:
        record = record[part]
    assert record
    for name, digest in record.items():
        assert fs.content_hash(DOCS / folder / name) == digest
