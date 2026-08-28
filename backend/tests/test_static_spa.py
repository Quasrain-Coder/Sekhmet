"""Tests for mount_spa — static SPA hosting with client-route fallback."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sekhmet.main import mount_spa


def _app_with_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>sekhmet-spa</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app, dist


def test_spa_serves_index_assets_and_fallback(tmp_path):
    app, dist = _app_with_dist(tmp_path)
    assert mount_spa(app, dist) is True
    client = TestClient(app)

    assert "sekhmet-spa" in client.get("/").text
    assert client.get("/assets/app.js").text == "console.log(1)"
    # client-side routes load index.html directly (deep link / refresh)
    assert "sekhmet-spa" in client.get("/history/42").text
    # API-shaped routes registered before the mount still win
    assert client.get("/health").json() == {"status": "ok"}


def test_spa_rejects_path_escape(tmp_path):
    app, dist = _app_with_dist(tmp_path)
    mount_spa(app, dist)
    client = TestClient(app)
    # ../ escape must fall back to index.html, never serve outside dist
    r = client.get("/%2e%2e/%2e%2e/pyproject.toml")
    assert "sekhmet-spa" in r.text


def test_mount_spa_without_build_is_noop(tmp_path):
    app = FastAPI()
    assert mount_spa(app, tmp_path / "no-dist") is False
    assert TestClient(app).get("/").status_code == 404
