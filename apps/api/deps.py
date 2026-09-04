"""
Shared FastAPI dependencies: JWT auth (decodes a bearer token and loads the
corresponding User row — the actual signup/login/verify/reset flow lives in
services/auth_service.py and routes/auth.py) and rate limiting (thin
wiring around services/rate_limiter.py's RateLimiter — client-IP extraction
here, the actual counting there).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from models import User
from services.rate_limiter import get_rate_limiter

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    return jwt.encode({"sub": user_id}, settings.jwt_secret, algorithm="HS256")


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
    nginx.conf` sets X-Forwarded-For on every request that reaches the API,
    since nginx is always the thing directly in front of it in this repo's
    deploy path — trusting that header here is safe *because* of that,
    not in general (an API exposed directly to the internet without a
    reverse proxy in front of it should not trust client-supplied
    headers). Falls back to the raw connection address for local dev,
    where there's no nginx in the loop."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
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
