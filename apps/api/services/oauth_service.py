"""
app/services/oauth_service.py

Google OAuth2 (Authorization Code flow) — see routes/auth.py for the two
HTTP endpoints (login redirect + callback) built on this, plus
GET /api/auth/google/status for the frontend to check whether it's
configured at all.

Real HTTP calls to Google's token/userinfo endpoints via httpx (already a
dependency), not a mock of our own code. The endpoint URLs are
configurable (config.py's google_auth_url/google_token_url/
google_userinfo_url) specifically so tests can point them at a local
stand-in HTTP server instead of the real Google — Google's actual consent
screen needs a real user clicking through it in a real browser, which
can't be exercised end-to-end by an automated test suite no matter what.
What tests/test_oauth_service.py actually verifies is TweakHub's side of
the protocol — the token exchange request, the userinfo fetch, and the
signup-or-login decision — run for real against a server that speaks
Google's actual response shape. Same pattern this project already uses
for SMTP (aiosmtpd, see test_email_service.py) and S3 (moto, see
test_storage_service.py): don't fake the boundary, stand in for the one
external dependency that genuinely can't run in this environment.

Gracefully disabled (not a 500) when GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET
aren't set — see is_google_oauth_configured().

Account model: identity is the email address, not a separate
provider+external-id row. If a user already has a password-based account
under the same email Google reports, signing in with Google just logs
into that same account (Google already verified the email, which is the
same trust bar routes/auth.py's own verify-email flow establishes) —
there's no separate "linked accounts" concept to manage. A first-time
Google sign-in creates a new User with no password_hash (the field is
nullable specifically for this — see models/user.py) and
is_email_verified=True immediately, since Google already did that
verification.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from config import get_settings
from models import PlanTier, User

from .auth_service import SIGNUP_BONUS_CREDITS, generate_referral_code

STATE_TTL_SECONDS = 600


class OAuthError(Exception):
    """Raised for any Google-OAuth-specific failure — routes/auth.py
    turns these into a redirect back to the frontend with an error
    marker, not a raw 5xx (the user is mid-browser-redirect, not calling
    an API client that can parse a JSON error body)."""


def is_google_oauth_configured() -> bool:
    settings = get_settings()
    return bool(settings.google_client_id and settings.google_client_secret)


def _sign_state(nonce: str, expires_at: int) -> str:
    settings = get_settings()
    message = f"{nonce}:{expires_at}".encode("utf-8")
    return hmac.new(settings.jwt_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def make_state() -> str:
    """A CSRF state param that doesn't need server-side session
    storage — this API is otherwise fully stateless (JWT-only auth, no
    session store) and adding one just for OAuth's state param would be a
    lot of new infrastructure for one field. Signed + time-boxed instead,
    the same shape as storage_service.py's signed download URLs, and
    verified the same way in verify_state()."""
    nonce = secrets.token_urlsafe(16)
    expires_at = int(time.time()) + STATE_TTL_SECONDS
    signature = _sign_state(nonce, expires_at)
    return f"{nonce}.{expires_at}.{signature}"


def verify_state(state: str | None) -> bool:
    if not state:
        return False
    try:
        nonce, expires_at_str, signature = state.split(".")
        expires_at = int(expires_at_str)
    except ValueError:
        return False
    if time.time() > expires_at:
        return False
    expected = _sign_state(nonce, expires_at)
    return hmac.compare_digest(expected, signature)


def build_authorization_url(redirect_uri: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": make_state(),
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{settings.google_auth_url}?{urlencode(params)}"


def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    settings = get_settings()
    resp = httpx.post(
        settings.google_token_url,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        raise OAuthError(f"Google token exchange failed: {resp.status_code} {resp.text}")
    return resp.json()


def fetch_userinfo(access_token: str) -> dict:
    settings = get_settings()
    resp = httpx.get(
        settings.google_userinfo_url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise OAuthError(f"Google userinfo fetch failed: {resp.status_code} {resp.text}")
    return resp.json()


def get_or_create_user_from_google(db: Session, userinfo: dict) -> User:
    email = userinfo.get("email")
    if not email:
        raise OAuthError("Google did not return an email address")
    # Some scopes/consent states omit this field entirely rather than
    # sending true — only reject when it's explicitly present and false,
    # not merely absent.
    if userinfo.get("email_verified") is False:
        raise OAuthError("Google account email is not verified")

    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        return existing

    user = User(
        email=email,
        full_name=userinfo.get("name"),
        password_hash=None,  # OAuth-only account — nothing to check on password login
        credit_balance=SIGNUP_BONUS_CREDITS,
        is_email_verified=True,  # Google already verified it
        plan_tier=PlanTier.FREE,
        referral_code=generate_referral_code(db),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
