import socket
import sys

import pytest

from gabi_cli import bootstrap


@pytest.fixture
def listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    yield sock.getsockname()[1]
    sock.close()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_port_in_use_detects_a_listener(listener):
    assert bootstrap.port_in_use(listener)


def test_port_in_use_accepts_a_free_port():
    assert not bootstrap.port_in_use(free_port())


@pytest.fixture
def serve_env(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setenv("GABI_FRONTEND_DIST", str(dist))
    monkeypatch.setenv("GABI_DATA_DIR", str(tmp_path / "data"))

    def no_worker(*args, **kwargs):
        raise AssertionError("serve must not start the worker")

    monkeypatch.setattr(bootstrap.subprocess, "Popen", no_worker)


def test_serve_on_a_busy_port_stops_before_the_worker_with_a_clear_message(serve_env, listener, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gabi_cli", "serve", "--port", str(listener)])
    with pytest.raises(SystemExit) as stopped:
        bootstrap.main()
    assert stopped.value.code == 2
    error = capsys.readouterr().err
    assert f"El puerto {listener} ya está en uso" in error
    assert "--port" in error


def test_serve_rejects_an_invalid_port(serve_env, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gabi_cli", "serve", "--port", "70000"])
    with pytest.raises(SystemExit):
        bootstrap.main()
    assert "--port debe estar entre 1 y 65535" in capsys.readouterr().err
