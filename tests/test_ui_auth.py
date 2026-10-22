"""Web UI sign-in: credentials from env, signed session cookie, gated pages."""

import os

from fastapi.testclient import TestClient

from main import app

UI_EMAIL, UI_PASSWORD = os.environ["UI_LOGIN_EMAIL"], os.environ["UI_LOGIN_PASSWORD"]  # set in conftest

APP_PAGES = ["/app", "/review", "/export", "/express", "/wizard", "/settings"]
OLD_PAGES = ["/home", "/workflows"]  # now open the stepped flow
OFF_PAGES = ["/datasets", "/datasets/upload", "/export-mcp"]  # Datasets and AI chat are off by default


def fresh():
    return TestClient(app, raise_server_exceptions=False)


def test_root_is_sign_in_page():
    r = fresh().get("/")
    assert r.status_code == 200 and 'id="login-form"' in r.text


def test_app_pages_redirect_to_sign_in_with_next():
    c = fresh()
    for path in APP_PAGES:
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303, path
        assert r.headers["location"].startswith("/?next=%2F"), path


def test_wrong_password_is_refused():
    r = fresh().post("/auth/login", json={"email": UI_EMAIL, "password": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_sign_in_opens_pages_and_sign_out_closes_them():
    c = fresh()
    r = c.post("/auth/login", json={"email": UI_EMAIL.upper(), "password": UI_PASSWORD})
    assert r.status_code == 200 and r.json()["data"]["name"] == "Test Analyst"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/auth/me").json()["data"]["email"] == UI_EMAIL
    for path in APP_PAGES:
        assert c.get(path, follow_redirects=False).status_code == 200, path
    for path in OLD_PAGES:
        assert c.get(path, follow_redirects=False).headers["location"] == "/app", path
    assert c.get("/", follow_redirects=False).headers["location"] == "/app"
    c.post("/auth/logout")
    assert c.get("/auth/me").status_code == 401
    assert c.get("/app", follow_redirects=False).status_code == 303


def test_tampered_cookie_is_rejected():
    c = fresh()
    c.cookies.set("ic_session", "eyJlIjoiYUBiLmMiLCJ4Ijo5OTk5OTk5OTk5fQ==.deadbeef")
    assert c.get("/auth/me").status_code == 401


def test_public_pages_stay_open():
    c = fresh()
    for path in ("/upload", "/privacy", "/docs/mcp", "/static/ui/ic.css"):
        assert c.get(path).status_code == 200, path


def test_pages_are_not_served_raw_from_static():
    assert fresh().get("/static/app.html").status_code == 404


def test_optional_features_are_off_by_default():
    """Datasets (needs Supabase) and AI chat aren't served, and pages are told so they hide their links."""
    c = fresh()
    c.post("/auth/login", json={"email": UI_EMAIL, "password": UI_PASSWORD})
    for path in OFF_PAGES:
        assert c.get(path, follow_redirects=False).status_code == 404, path
    assert c.get("/v1/library/files").status_code == 404
    assert c.post("/v1/chat", json={}).status_code == 404
    assert 'window.__INDICO_FEATURES__ = {"datasets": false, "chat": false};' in c.get("/static/config.js").text
