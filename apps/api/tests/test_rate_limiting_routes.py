"""
HTTP-level tests: does a request actually get a 429 (with Retry-After) once
it crosses the configured limit, for each place rate limiting was wired in
— auth signup/login/password-reset (IP-keyed), tool processing (user-keyed,
per plan), and the DPO payment callback (IP-keyed, plus the source-IP
allowlist). Unit coverage of the limiter algorithm itself lives in
test_rate_limiter.py; this file is about the FastAPI wiring.

All of these go through the real app (see conftest.py's `client` /
`client_factory` fixtures) with a fakeredis-backed limiter and a throwaway
SQLite DB — no real Redis or Postgres needed.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_signup_rate_limited_by_ip(client, override_settings):
    override_settings(rate_limit_signup_per_hour=2)

    for i in range(2):
        resp = client.post(
            "/api/auth/signup",
            json={"email": f"signup{i}@example.com", "password": "correct horse battery"},
        )
        assert resp.status_code == 201, resp.text

    blocked = client.post(
        "/api/auth/signup",
        json={"email": "signup-blocked@example.com", "password": "correct horse battery"},
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_login_rate_limited_by_ip_even_on_repeated_failures(client, override_settings):
    override_settings(rate_limit_login_per_hour=2)

    client.post(
        "/api/auth/signup",
        json={"email": "loginlimit@example.com", "password": "correct horse battery"},
    )

    for _ in range(2):
        resp = client.post(
            "/api/auth/login",
            json={"email": "loginlimit@example.com", "password": "wrong password"},
        )
        assert resp.status_code == 401

    blocked = client.post(
        "/api/auth/login",
        json={"email": "loginlimit@example.com", "password": "wrong password"},
    )
    assert blocked.status_code == 429


def test_password_reset_request_rate_limited_by_ip(client, override_settings):
    override_settings(rate_limit_password_reset_per_hour=2)

    for _ in range(2):
        resp = client.post(
            "/api/auth/request-password-reset", json={"email": "ghost@example.com"}
        )
        assert resp.status_code == 200

    blocked = client.post(
        "/api/auth/request-password-reset", json={"email": "ghost@example.com"}
    )
    assert blocked.status_code == 429


def test_tool_processing_rate_limited_per_user_by_plan(client, override_settings, sample_png_bytes):
    override_settings(rate_limit_free_per_hour=2)

    signup = client.post(
        "/api/auth/signup",
        json={"email": "toollimit@example.com", "password": "correct horse battery"},
    )
    assert signup.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"email": "toollimit@example.com", "password": "correct horse battery"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    def _run():
        return client.post(
            "/api/tools/image_convert/process",
            files={"file": ("in.png", sample_png_bytes, "image/png")},
            data={"options": '{"target_format": "png"}'},
            headers=headers,
        )

    for _ in range(2):
        resp = _run()
        assert resp.status_code == 200, resp.text

    blocked = _run()
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_payments_callback_rate_limited_by_ip(client, override_settings):
    override_settings(rate_limit_payments_callback_per_hour=2)

    for _ in range(2):
        resp = client.post("/api/payments/callback", params={"transaction_token": "no-such-token"})
        assert resp.status_code == 404  # unknown attempt, but not yet rate-limited

    blocked = client.post("/api/payments/callback", params={"transaction_token": "no-such-token"})
    assert blocked.status_code == 429


def test_payments_callback_rejects_ip_outside_allowlist(client, override_settings):
    override_settings(dpo_webhook_ip_allowlist="203.0.113.0/24")

    resp = client.post(
        "/api/payments/callback",
        params={"transaction_token": "whatever"},
        headers={"X-Forwarded-For": "198.51.100.9"},
    )
    assert resp.status_code == 403


def test_payments_callback_allows_ip_inside_allowlist(client, override_settings):
    override_settings(dpo_webhook_ip_allowlist="203.0.113.0/24")

    # Passes the allowlist check and reaches the normal "unknown payment
    # attempt" handling — 404, not 403, is the signal the IP check let it
    # through.
    resp = client.post(
        "/api/payments/callback",
        params={"transaction_token": "whatever"},
        headers={"X-Forwarded-For": "203.0.113.42"},
    )
    assert resp.status_code == 404


def test_payments_callback_allowlist_disabled_by_default(client):
    # No override_settings call — DPO_WEBHOOK_IP_ALLOWLIST is unset, so any
    # source IP reaches the normal handling.
    resp = client.post(
        "/api/payments/callback",
        params={"transaction_token": "whatever"},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert resp.status_code == 404
