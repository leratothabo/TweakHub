"""
app/middleware.py

Two ASGI middlewares wired into main.py, covering two "Should-have"
security-checklist items from docs/TODO.md:

- SecurityHeadersMiddleware adds the standard defensive response headers
  (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy,
  Permissions-Policy, and — in production only — Strict-Transport-
  Security) that a security review expects on a public API.
  /docs, /redoc, and /openapi.json get a relaxed CSP since FastAPI's
  bundled Swagger UI / ReDoc pages need a CDN script and inline styles to
  render at all; every other route is a JSON API response with no HTML of
  its own, so it gets a strict default-src 'none'.
- RequestLoggingMiddleware writes one structured log line per request
  (method, path, status, duration_ms, client IP, and user id when a valid
  bearer token is present) to a dedicated "tweakhub.access" logger.
  Deliberately excludes request/response bodies, file bytes, the raw
  Authorization header value, and query strings — a signed download URL's
  token (routes/files.py) is a query param, and logging it would defeat
  the point of it being signed. The user id is recovered by decoding the
  bearer token the same way deps.get_current_user does, but purely
  best-effort for the log line: an invalid/missing/expired token here
  just logs user=- rather than rejecting the request, since the actual
  auth check is deps.get_current_user's job, not this middleware's.
"""
from __future__ import annotations

import logging
import time

from fastapi import Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings
from deps import get_client_ip

access_logger = logging.getLogger("tweakhub.access")
# Same reasoning as services/email_service.py's logger setup: uvicorn
# doesn't raise the root logger to INFO by default, so give this logger
# its own handler + level so access logs are visible regardless of how
# the app is launched.
if not access_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    access_logger.addHandler(_handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False

_DOCS_PREFIXES = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if request.url.path.startswith(_DOCS_PREFIXES):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' fonts.googleapis.com cdn.jsdelivr.net; "
                "img-src 'self' data: fastapi.tiangolo.com; "
                "font-src 'self' fonts.gstatic.com"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        # Only meaningful over HTTPS, which is what "production" means in
        # this repo's deploy path (certbot-issued TLS via nginx — see
        # scripts/setup-truehost.sh). Sending it in dev over plain HTTP
        # would be a no-op at best, so it's gated on env rather than
        # always-on.
        if get_settings().node_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        return response


def _best_effort_user_id(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[len("bearer "):].strip()
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except JWTError:
        return None
    return payload.get("sub")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.monotonic() - started) * 1000, 1)
            access_logger.info(
                "%s %s status=%s duration_ms=%s client=%s user=%s",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                get_client_ip(request),
                _best_effort_user_id(request) or "-",
            )
