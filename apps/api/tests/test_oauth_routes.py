"""
HTTP-level tests for the three Google OAuth endpoints in routes/auth.py:
GET /api/auth/google/status, GET /api/auth/google/login, and
GET /api/auth/google/callback. services/oauth_service.py's own unit tests
(test_oauth_service.py) cover the token-exchange/userinfo/user-creation
logic in depth against the same kind of local stand-in HTTP server used
here — these confirm the route wiring: redirects, query params, the
not-configured 501s, and a full browser-shaped round trip through
/login -> (fake Google) -> /callback.
"""
import http.server
import json
import socket
import threading
import urllib.parse

import pytest


class _FakeGoogleHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - keep test output quiet
        pass

    def _json(self, status: int, body: dict):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path != "/token":
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        params = urllib.parse.parse_qs(body)
        code = params.get("code", [""])[0]
        if code == "bad-code":
            self._json(400, {"error": "invalid_grant"})
            return
        self._json(
            200,
            {
                "access_token": f"fake-access-token-for-{code}",
                "token_type": "Bearer",
                "expires_in": 3600,
                "id_token": "fake-id-token",
            },
        )

    def do_GET(self):
        if self.path != "/userinfo":
            self._json(404, {"error": "not_found"})
            return
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer fake-access-token-for-"):
            self._json(401, {"error": "invalid_token"})
            return
        code = auth.removeprefix("Bearer fake-access-token-for-")
        self._json(
            200,
            {
                "email": f"{code}@example.com",
                "email_verified": True,
                "name": "OAuth Route Test User",
                "sub": "1234567890",
            },
        )


@pytest.fixture()
def fake_google_server():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _FakeGoogleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def google_configured(override_settings, fake_google_server):
    override_settings(
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
        google_auth_url=f"{fake_google_server}/auth",
        google_token_url=f"{fake_google_server}/token",
        google_userinfo_url=f"{fake_google_server}/userinfo",
    )
    return fake_google_server


def _extract_state(login_location: str) -> str:
    query = urllib.parse.urlparse(login_location).query
    return urllib.parse.parse_qs(query)["state"][0]


def test_google_status_reports_disabled_by_default(client):
    resp = client.get("/api/auth/google/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}


def test_google_login_returns_501_when_not_configured(client):
    resp = client.get("/api/auth/google/login", follow_redirects=False)
    assert resp.status_code == 501


def test_google_callback_returns_501_when_not_configured(client):
    resp = client.get("/api/auth/google/callback", follow_redirects=False)
    assert resp.status_code == 501


def test_google_status_reports_enabled_when_configured(client, google_configured):
    resp = client.get("/api/auth/google/status")
    assert resp.json() == {"enabled": True}


def test_google_login_redirects_to_google_authorization_url(client, google_configured):
    resp = client.get("/api/auth/google/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith(f"{google_configured}/auth?")
    assert "client_id=test-client-id" in location
    assert "state=" in location


def test_google_callback_full_success_round_trip(client, google_configured, db_session):
    from models import User

    login_resp = client.get("/api/auth/google/login", follow_redirects=False)
    state = _extract_state(login_resp.headers["location"])

    callback_resp = client.get(
        "/api/auth/google/callback",
        params={"code": "good-code", "state": state},
        follow_redirects=False,
    )
    assert callback_resp.status_code in (302, 307)
    location = callback_resp.headers["location"]
    query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    assert "oauth_token" in query
    assert query["oauth_token"][0]  # non-empty JWT

    user = db_session.query(User).filter(User.email == "good-code@example.com").first()
    assert user is not None
    assert user.is_email_verified is True
    assert user.password_hash is None


def test_google_callback_missing_state_redirects_with_error(client, google_configured):
    resp = client.get(
        "/api/auth/google/callback", params={"code": "good-code"}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(resp.headers["location"]).query)
    assert query["oauth_error"] == ["1"]


def test_google_callback_bogus_state_redirects_with_error(client, google_configured):
    resp = client.get(
        "/api/auth/google/callback",
        params={"code": "good-code", "state": "not-a-real-state"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(resp.headers["location"]).query)
    assert query["oauth_error"] == ["1"]


def test_google_callback_bad_code_redirects_with_error(client, google_configured):
    login_resp = client.get("/api/auth/google/login", follow_redirects=False)
    state = _extract_state(login_resp.headers["location"])

    resp = client.get(
        "/api/auth/google/callback",
        params={"code": "bad-code", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(resp.headers["location"]).query)
    assert query["oauth_error"] == ["1"]


def test_google_callback_google_error_param_redirects_with_error(client, google_configured):
    login_resp = client.get("/api/auth/google/login", follow_redirects=False)
    state = _extract_state(login_resp.headers["location"])

    resp = client.get(
        "/api/auth/google/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(resp.headers["location"]).query)
    assert query["oauth_error"] == ["1"]


def test_google_callback_reuses_existing_password_account(client, google_configured, db_session):
    signup_resp = client.post(
        "/api/auth/signup",
        json={"email": "good-code@example.com", "password": "correct horse battery"},
    )
    assert signup_resp.status_code == 201

    login_resp = client.get("/api/auth/google/login", follow_redirects=False)
    state = _extract_state(login_resp.headers["location"])

    callback_resp = client.get(
        "/api/auth/google/callback",
        params={"code": "good-code", "state": state},
        follow_redirects=False,
    )
    location = callback_resp.headers["location"]
    query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    assert "oauth_token" in query

    from models import User

    matches = db_session.query(User).filter(User.email == "good-code@example.com").all()
    assert len(matches) == 1  # no duplicate account created
    assert matches[0].password_hash is not None  # still a real password account too
