"""
Tests for services/oauth_service.py. Google's real consent screen can't be
exercised by an automated suite (it needs a real user in a real browser),
so what's verified here is TweakHub's side of the OAuth2 protocol — the
token exchange, the userinfo fetch, and the signup-or-login decision — run
for real over HTTP against a tiny local server (fake_google_server below)
that speaks Google's actual token/userinfo response shape. Same pattern
this project already uses for SMTP (aiosmtpd, test_email_service.py) and
S3 (moto, test_storage_service.py).
"""
import http.server
import json
import os
import socket
import sys
import threading
import urllib.parse

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.oauth_service import (  # noqa: E402
    OAuthError,
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_userinfo,
    get_or_create_user_from_google,
    is_google_oauth_configured,
    make_state,
    verify_state,
)


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
        if code == "unverified-code":
            self._json(200, {"email": "unverified@example.com", "email_verified": False, "name": "Nope"})
            return
        if code == "no-email-code":
            self._json(200, {"email_verified": True, "name": "No Email"})
            return
        self._json(
            200,
            {
                "email": "oauth-user@example.com",
                "email_verified": True,
                "name": "OAuth Test User",
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


def test_not_configured_by_default(override_settings):
    override_settings(google_client_id="", google_client_secret="")
    assert is_google_oauth_configured() is False


def test_configured_when_both_client_id_and_secret_set(override_settings):
    override_settings(google_client_id="x", google_client_secret="y")
    assert is_google_oauth_configured() is True


def test_configured_requires_both_fields(override_settings):
    override_settings(google_client_id="x", google_client_secret="")
    assert is_google_oauth_configured() is False


def test_build_authorization_url_includes_expected_params(google_configured):
    url = build_authorization_url("https://tweakhub.example/callback")
    assert url.startswith(f"{google_configured}/auth?")
    assert "client_id=test-client-id" in url
    assert "scope=openid" in url
    assert "state=" in url
    assert urllib.parse.quote("https://tweakhub.example/callback", safe="") in url


def test_state_round_trips():
    state = make_state()
    assert verify_state(state) is True


def test_state_rejects_tampered_signature():
    nonce, expires_at, _sig = make_state().split(".")
    assert verify_state(f"{nonce}.{expires_at}.0" * 16) is False


def test_state_rejects_expired():
    from services import oauth_service as oauth_service_module

    original = oauth_service_module.STATE_TTL_SECONDS
    oauth_service_module.STATE_TTL_SECONDS = -10  # already expired the moment it's made
    try:
        state = make_state()
    finally:
        oauth_service_module.STATE_TTL_SECONDS = original
    assert verify_state(state) is False


def test_state_rejects_malformed():
    assert verify_state(None) is False
    assert verify_state("not-a-real-state") is False
    assert verify_state("") is False


def test_exchange_code_and_fetch_userinfo_real_round_trip(google_configured):
    tokens = exchange_code_for_tokens("good-code", "https://tweakhub.example/callback")
    assert tokens["access_token"] == "fake-access-token-for-good-code"

    userinfo = fetch_userinfo(tokens["access_token"])
    assert userinfo["email"] == "oauth-user@example.com"
    assert userinfo["email_verified"] is True


def test_exchange_code_failure_raises_oauth_error(google_configured):
    with pytest.raises(OAuthError, match="token exchange failed"):
        exchange_code_for_tokens("bad-code", "https://tweakhub.example/callback")


def test_fetch_userinfo_with_bad_token_raises_oauth_error(google_configured):
    with pytest.raises(OAuthError, match="userinfo fetch failed"):
        fetch_userinfo("not-a-real-token")


def test_get_or_create_user_from_google_creates_new_user(db_session):
    userinfo = {
        "email": "brand-new-oauth@example.com",
        "email_verified": True,
        "name": "Brand New",
    }
    user = get_or_create_user_from_google(db_session, userinfo)
    assert user.email == "brand-new-oauth@example.com"
    assert user.full_name == "Brand New"
    assert user.password_hash is None
    assert user.is_email_verified is True
    assert user.credit_balance == 25
    assert user.referral_code is not None


def test_get_or_create_user_from_google_reuses_existing_account(db_session):
    userinfo = {"email": "repeat-oauth@example.com", "email_verified": True, "name": "Repeat"}
    first = get_or_create_user_from_google(db_session, userinfo)
    second = get_or_create_user_from_google(db_session, userinfo)
    assert first.id == second.id


def test_get_or_create_user_from_google_reuses_existing_password_account(db_session):
    from services.auth_service import auth_service

    existing = auth_service.signup(db_session, "already-has-password@example.com", "correct horse battery", None)
    userinfo = {"email": "already-has-password@example.com", "email_verified": True, "name": "Whoever"}

    user = get_or_create_user_from_google(db_session, userinfo)
    assert user.id == existing.id
    assert user.password_hash is not None  # untouched — still a real password account too


def test_get_or_create_user_from_google_rejects_missing_email(db_session):
    with pytest.raises(OAuthError, match="email"):
        get_or_create_user_from_google(db_session, {"email_verified": True})


def test_get_or_create_user_from_google_rejects_explicitly_unverified_email(db_session):
    with pytest.raises(OAuthError, match="not verified"):
        get_or_create_user_from_google(
            db_session, {"email": "unverified@example.com", "email_verified": False}
        )
