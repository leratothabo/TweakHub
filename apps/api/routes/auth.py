"""
app/routes/auth.py

Signup, login, email verification, and password reset. Actual password
hashing / token logic lives in services/auth_service.py; this module is
just the HTTP shape around it.

Note: login enforces email verification everywhere except
NODE_ENV=development (see auth_service.login) — that's a deliberate dev
convenience, not a security gap in production, since production always
runs with NODE_ENV=production.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from deps import create_access_token, get_current_user, rate_limit
from models import User
from services.auth_service import AuthError, auth_service
from services.oauth_service import (
    OAuthError,
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_userinfo,
    get_or_create_user_from_google,
    is_google_oauth_configured,
    verify_state,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _google_redirect_uri() -> str:
    settings = get_settings()
    return settings.google_redirect_uri or f"{settings.api_url}/api/auth/google/callback"


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None
    # Another user's referral_code (services/auth_service.py) — an
    # unrecognized/stale code is silently ignored rather than rejecting
    # the signup. See routes/auth.py's GET /referral for where a user
    # gets their own code to share.
    ref: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class RequestPasswordResetRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


@router.post(
    "/signup",
    status_code=201,
    dependencies=[Depends(rate_limit("auth_signup", "rate_limit_signup_per_hour"))],
)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    try:
        user = auth_service.signup(
            db, payload.email, payload.password, payload.full_name, referral_code=payload.ref
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "user_id": user.id,
        "email": user.email,
        "is_email_verified": user.is_email_verified,
        "message": "Account created. Check your email to verify your address.",
    }


@router.get("/referral")
def get_referral_info(user: User = Depends(get_current_user)):
    """A user's own referral code + a ready-to-share link. Bonus credits
    (services/auth_service.py's _grant_referral_bonus_if_applicable) land
    on both sides once the invitee verifies their email — not at signup."""
    settings = get_settings()
    return {
        "referral_code": user.referral_code,
        "referral_link": f"{settings.base_url}/signup?ref={user.referral_code}",
        "bonus_credits_invitee": settings.referral_bonus_credits_invitee,
        "bonus_credits_referrer": settings.referral_bonus_credits_referrer,
    }


@router.post(
    "/login",
    dependencies=[Depends(rate_limit("auth_login", "rate_limit_login_per_hour"))],
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        user = auth_service.login(db, payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    return {"access_token": create_access_token(user.id), "user_id": user.id}


@router.post("/verify-email")
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    try:
        user = auth_service.verify_email(db, payload.token)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"user_id": user.id, "is_email_verified": user.is_email_verified}


@router.post(
    "/request-password-reset",
    dependencies=[Depends(rate_limit("auth_password_reset", "rate_limit_password_reset_per_hour"))],
)
def request_password_reset(payload: RequestPasswordResetRequest, db: Session = Depends(get_db)):
    auth_service.request_password_reset(db, payload.email)
    # Always 200, regardless of whether the email is registered, so this
    # endpoint can't be used to enumerate accounts.
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        auth_service.reset_password(db, payload.token, payload.new_password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"message": "Password updated. You can now sign in."}


# -- Google OAuth (services/oauth_service.py) --------------------------------


@router.get("/google/status")
def google_oauth_status():
    """Lets the frontend decide whether to show a "Sign in with Google"
    button at all, rather than showing one that 501s on click."""
    return {"enabled": is_google_oauth_configured()}


@router.get("/google/login")
def google_login():
    if not is_google_oauth_configured():
        raise HTTPException(status_code=501, detail="Google OAuth is not configured")
    return RedirectResponse(build_authorization_url(_google_redirect_uri()))


@router.get("/google/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """Always redirects back to the frontend (base_url) rather than
    returning a JSON error — the browser is mid-redirect from Google, not
    an API client that can parse a JSON body. Success carries the JWT as
    ?oauth_token=...; any failure carries ?oauth_error=1 with no detail
    (the detail is server-logged via the OAuthError, not exposed in a
    URL a browser history/referrer could leak)."""
    settings = get_settings()
    error_redirect = RedirectResponse(f"{settings.base_url}/?oauth_error=1")

    if not is_google_oauth_configured():
        raise HTTPException(status_code=501, detail="Google OAuth is not configured")
    if error or not code or not verify_state(state):
        return error_redirect

    try:
        tokens = exchange_code_for_tokens(code, _google_redirect_uri())
        userinfo = fetch_userinfo(tokens["access_token"])
        user = get_or_create_user_from_google(db, userinfo)
    except (OAuthError, KeyError):
        return error_redirect

    token = create_access_token(user.id)
    return RedirectResponse(f"{settings.base_url}/?oauth_token={token}")
