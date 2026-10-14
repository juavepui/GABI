"""Ledger lock/anchor, git provenance and market date moved out of the #133 facades unchanged."""

import subprocess
from datetime import UTC, datetime

import pytest

from gabi import config, evidence_confidence, history_refresh, live_ledger, research_lab
from gabi.domain.market import freshness
from gabi.infrastructure.legacy import blind_validation
from gabi.infrastructure.providers import research_environment
from gabi.infrastructure.storage import live_ledger_files


def test_writer_lock_is_exclusive_and_released(tmp_path):
    with live_ledger_files.writer_lock(tmp_path / "ledger"):
        with pytest.raises(OSError), live_ledger_files.writer_lock(tmp_path / "ledger"):
            pass
    with live_ledger_files.writer_lock(tmp_path / "ledger"):
        pass
    assert (tmp_path / "ledger" / "writer.lock").read_bytes() == b"0"


def test_live_ledger_anchor_bytes_and_lock_location(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with live_ledger._locked():
        assert (tmp_path / "live_ledger" / "writer.lock").exists()
        live_ledger._write_anchor(7, "abc")
    # Text mode, as before: the platform newline is kept.
    assert (tmp_path / "live_ledger" / "head.json").read_text(encoding="utf-8") == '{"hash":"abc","seq":7}\n'
    assert not (tmp_path / "live_ledger" / "head.json.tmp").exists()


def test_working_tree_flag_keeps_its_failure_rules(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append((args, kw["cwd"]))
                        or subprocess.CompletedProcess(args, 0, " M backend/src/gabi/x.py\n", ""))
    assert research_environment.working_tree_modified(tmp_path, "backend/src/gabi") is True
    assert calls == [(["git", "status", "--porcelain", "--", "backend/src/gabi"], tmp_path)]
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    assert research_environment.working_tree_modified(tmp_path, "x") is False
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("git")))
    assert research_environment.working_tree_modified(tmp_path, "x") is None
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("git", 5)))
    with pytest.raises(subprocess.TimeoutExpired):  # as before: only OSError means "unknown"
        research_environment.working_tree_modified(tmp_path, "x")


@pytest.mark.parametrize("now", [datetime(2026, 2, 3, 15, tzinfo=UTC), datetime(2026, 2, 3, 22, tzinfo=UTC),
                                 datetime(2026, 2, 7, 12, tzinfo=UTC)])
def test_market_date_is_the_previous_string_session(now):
    expected = freshness.last_completed_session(now).isoformat()
    assert freshness.market_date(now) == history_refresh.last_completed_session(now) == expected
    assert live_ledger.last_completed_session(now) == evidence_confidence.last_completed_session(now) == expected


def test_blind_commit_is_the_research_lab_commit():
    assert blind_validation._current_git_commit() == research_lab._current_git_commit()
