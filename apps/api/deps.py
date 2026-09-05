"""
Shared FastAPI dependencies: JWT auth (decodes a bearer token and loads the
corresponding User row — the actual signup/login/verify/reset flow lives in
services/auth_service.py and routes/auth.py) and rate limiting (thin
wiring around services/rate_limiter.py's RateLimiter — client-IP extraction
here, the actual counting there).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from models import User
from services.rate_limiter import get_rate_limiter

bearer_scheme = HTTPBearer(auto_error=False)

_DURATION_RE = re.compile(r"^(\d+)([smhdw])$")
_DURATION_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


def _parse_duration(value: str) -> timedelta:
    """Parse a short duration string like "7d"/"24h"/"30m" (config.py's
    JWT_EXPIRES_IN format) into a timedelta. Falls back to a hardcoded
    7-day default on anything that doesn't match that shape, rather than
    silently minting a token with no expiry at all if the setting is
    ever misconfigured."""
    match = _DURATION_RE.match(value.strip())
    if not match:
        return timedelta(days=7)
    amount, unit = match.groups()
    return timedelta(**{_DURATION_UNITS[unit]: int(amount)})


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    # JWT_EXPIRES_IN (config.py) was declared but never actually read
    # anywhere — tokens were minted with no "exp" claim at all, so once
    # issued one was valid forever: a token that leaked once (XSS,
    # browser history, a shared machine) stayed usable indefinitely, and
    # auth_service.reset_password() rotating the password hash didn't
    # revoke any already-issued token either, since there was no expiry
    # to have expired. python-jose's jwt.decode() only enforces `exp`
    # when the claim is present, so adding it here is enough — no change
    # needed on the decode side in get_current_user() below.
    expires_at = datetime.now(timezone.utc) + _parse_duration(settings.jwt_expires_in)
    return jwt.encode(
        {"sub": user_id, "exp": int(expires_at.timestamp())}, settings.jwt_secret, algorithm="HS256"
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise unauthorized

    user_id = payload.get("sub")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Same bearer-token auth as get_current_user, plus User.is_admin.
    Currently only guards routes/admin.py's bank-transfer confirmation
    endpoints — see that flag's docstring in models/user.py for why
    there's no self-service way to grant it."""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def get_client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limit keys. `infrastructure/nginx/
    nginx.conf` sets both of these on every request that reaches the API,
    since nginx is always the thing directly in front of it in this
    repo's deploy path — trusting them here is safe *because* of that,
    not in general (an API exposed directly to the internet without a
    reverse proxy in front of it should not trust client-supplied
    headers).

    X-Real-IP is checked first and is fully trustworthy: nginx's
    `proxy_set_header X-Real-IP $remote_addr` REPLACES whatever the
    client sent (nginx's proxy_set_header always overwrites the header,
    never appends to it), so this can't be attacker-controlled.

    X-Forwarded-For is the fallback, and the LAST comma-separated entry
    is used, not the first. nginx sets it via
    `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`, and
    that variable APPENDS the real connecting IP onto whatever the
    client already sent, rather than replacing it — a request arriving
    with "X-Forwarded-For: 1.2.3.4" reaches this code as
    "X-Forwarded-For: 1.2.3.4, <the real client IP>". Taking the first
    entry (the previous behavior here) let any client fully control its
    own rate-limit/log key by sending an arbitrary X-Forwarded-For value
    — defeating the signup/login/password-reset/tool-process rate limits
    entirely by varying that one header per request. The last entry is
    the one nginx itself appended and isn't attacker-controlled.

    Falls back to the raw connection address for local dev, where
    there's no nginx in the loop and neither header is set."""
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, limit_setting: str, window_seconds: int = 3600):
    """FastAPI dependency factory for IP-keyed rate limiting on
    unauthenticated (or pre-auth) endpoints — signup, login,
    password-reset, the DPO payment callback. `limit_setting` is the
    Settings attribute name, read at request time (not decoration time) so
    tests can change it via environment/monkeypatch without re-importing
    the route module. Raises 429 with a Retry-After header when exceeded;
    see services/rate_limiter.py for the fail-open behavior on a Redis
    outage."""

    def _dependency(request: Request) -> None:
        settings = get_settings()
        limit = getattr(settings, limit_setting)
        key = f"{bucket}:{get_client_ip(request)}"
        result = get_rate_limiter().hit(key, limit, window_seconds)
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests — please try again later.",
                headers={"Retry-After": str(result.retry_after_seconds)},
            )

    return _dependency
