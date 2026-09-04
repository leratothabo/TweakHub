"""
app/services/email_service.py

Transactional email, with two backends selected by EMAIL_BACKEND:

- "console" (default) — logs every "sent" email instead of delivering it.
  This is what makes the signup/password-reset flows fully testable and
  runnable in local dev with zero provider setup: copy the link out of the
  server log. Unchanged from before this file had a backend abstraction.
- "smtp" — sends for real via smtplib + STARTTLS. Works with any SMTP
  relay (SendGrid/Postmark/SES's SMTP endpoints, a plain Gmail/Workspace
  account, or a self-hosted MTA) — there's no ESP-specific API client here
  on purpose, since SMTP is the one interface every mainstream provider
  supports, and it means swapping providers later is a config change
  (SMTP_HOST/PORT/USERNAME/PASSWORD in .env), not a code change.

EmailService itself doesn't know which backend is active — it builds the
subject/body and hands off to _backend.send(). Verified against a real
local SMTP server (aiosmtpd) in tests/test_email_service.py, not mocked:
the smtp backend really opens a socket, does STARTTLS/AUTH, and the test
asserts on the message the server actually received.
"""
from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText

from config import get_settings

logger = logging.getLogger("tweakhub.email")
# Uvicorn doesn't raise the root logger to INFO by default, which would
# silently swallow every "sent" email. Give this logger its own handler +
# level so the console backend is actually visible regardless of how the
# app is launched (uvicorn, pytest, a script).
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class EmailBackend(ABC):
    @abstractmethod
    def send(self, to_email: str, subject: str, body: str) -> None: ...


class ConsoleEmailBackend(EmailBackend):
    def send(self, to_email: str, subject: str, body: str) -> None:
        logger.info("EMAIL to=%s subject=%r body=%r", to_email, subject, body)


class SmtpEmailBackend(EmailBackend):
    """Real delivery via smtplib. Reads settings fresh on every send()
    (not cached at construction) so EMAIL_BACKEND/SMTP_* changes — in
    tests via the override_settings fixture, or in production via env
    reload — take effect without needing a new EmailService instance."""

    def send(self, to_email: str, subject: str, body: str) -> None:
        settings = get_settings()
        if not settings.smtp_host:
            raise RuntimeError(
                "EMAIL_BACKEND=smtp but SMTP_HOST is not set — see .env.example"
            )

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from_address
        msg["To"] = to_email

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)


_BACKENDS: dict[str, EmailBackend] = {
    "console": ConsoleEmailBackend(),
    "smtp": SmtpEmailBackend(),
}


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send_verification_email(self, to_email: str, token: str) -> None:
        link = f"{self.settings.base_url}/verify-email?token={token}"
        self._send(to_email, "Verify your TweakHub account", f"Verify your email: {link}")

    def send_password_reset_email(self, to_email: str, token: str) -> None:
        link = f"{self.settings.base_url}/reset-password?token={token}"
        self._send(to_email, "Reset your TweakHub password", f"Reset your password: {link}")

    def send_org_invite_email(self, to_email: str, org_name: str, token: str) -> None:
        link = f"{self.settings.base_url}/accept-invite?token={token}"
        self._send(
            to_email,
            f"You've been invited to join {org_name} on TweakHub",
            f"Accept your invite to join {org_name}: {link}",
        )

    def _send(self, to_email: str, subject: str, body: str) -> None:
        # Backend chosen per-call from fresh settings, not cached at
        # __init__ time — the module-level `email_service` singleton below
        # is constructed once at import time, before tests get a chance to
        # override EMAIL_BACKEND.
        backend_name = get_settings().email_backend
        backend = _BACKENDS.get(backend_name)
        if backend is None:
            raise RuntimeError(
                f"Unknown EMAIL_BACKEND={backend_name!r} — expected 'console' or 'smtp'"
            )
        backend.send(to_email, subject, body)


email_service = EmailService()
