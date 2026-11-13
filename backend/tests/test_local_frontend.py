"""The production UI and API share a loopback origin without exposing files."""

from fastapi.testclient import TestClient

from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def test_built_frontend_serves_spa_paths_and_keeps_api_errors(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>GABI_LOCAL_BUILD</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('local')", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("HIDDEN", encoding="utf-8")
    with TestClient(create_app(Settings(tmp_path / "data"), frontend_dist=dist)) as api:
        assert "GABI_LOCAL_BUILD" in api.get("/").text
        assert "GABI_LOCAL_BUILD" in api.get("/investigacion").text
        assert api.get("/assets/app.js").text == "console.log('local')"
        assert api.get("/api/v1/health").json()["status"] == "ok"
        assert api.get("/api/v1/unknown").status_code == 404
        assert api.get("/missing.js").status_code == 404
        assert "HIDDEN" not in api.get("/%2e%2e/secret.txt").text
    assert not (tmp_path / "data").exists()


def test_frontend_requires_completed_build(tmp_path):
    try:
        create_app(Settings(tmp_path / "data"), frontend_dist=tmp_path / "missing")
    except ValueError as exc:
        assert "Build React" in str(exc)
    else:
        raise AssertionError("Missing build was accepted")
