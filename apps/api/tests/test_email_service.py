"""
Tests for services/email_service.py's two backends.

The console backend (the default, unchanged from before this file had a
backend abstraction) is verified via caplog. The smtp backend is verified
against a real local SMTP server (aiosmtpd's Controller, not smtplib
mocked out) — it really opens a socket, does the SMTP conversation, and
the test asserts on the message content the server actually received, so
this exercises real network I/O the way the project's other "don't fake
the thing you're supposed to be testing" tests do (see test_engines.py,
test_job_worker.py).
"""
import logging
import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.email_service import EmailService  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _CapturingHandler:
    """aiosmtpd message handler that just records what it received,
    rather than actually delivering anything — this is a real SMTP
    server, just one with nowhere further to forward mail to."""

    def __init__(self):
        self.messages: list[dict] = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append(
            {
                "mail_from": envelope.mail_from,
                "rcpt_tos": list(envelope.rcpt_tos),
                "content": envelope.content.decode("utf-8", errors="replace"),
            }
        )
        return "250 Message accepted for delivery"


@pytest.fixture
def smtp_server():
    """A real local SMTP server for the duration of one test."""
    aiosmtpd = pytest.importorskip("aiosmtpd.controller", reason="aiosmtpd not installed")

    handler = _CapturingHandler()
    port = _free_port()
    controller = aiosmtpd.Controller(handler, hostname="127.0.0.1", port=port)
    controller.start()
    try:
        yield handler, port
    finally:
        controller.stop()


def test_console_backend_logs_the_email(override_settings):
    # The "tweakhub.email" logger deliberately sets propagate=False (see
    # the module docstring — it needs to be visible under uvicorn without
    # depending on root-logger config), which also means pytest's caplog
    # fixture never sees its records since caplog listens on the root
    # logger. Attach a plain handler directly to this logger instead.
    override_settings(email_backend="console", base_url="https://tweakhub.com")
    service = EmailService()

    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    target_logger = logging.getLogger("tweakhub.email")
    collector = _Collector()
    target_logger.addHandler(collector)
    try:
        service.send_verification_email("someone@example.com", "tok123")
    finally:
        target_logger.removeHandler(collector)

    assert any(
        "someone@example.com" in r.getMessage() and "tok123" in r.getMessage() for r in records
    )


def test_smtp_backend_really_delivers_to_a_real_server(override_settings, smtp_server):
    handler, port = smtp_server
    override_settings(
        email_backend="smtp",
        base_url="https://tweakhub.com",
        smtp_host="127.0.0.1",
        smtp_port=port,
        smtp_use_tls=False,
        smtp_from_address="noreply@tweakhub.com",
    )
    service = EmailService()

    service.send_verification_email("newuser@example.com", "verify-tok-456")

    assert len(handler.messages) == 1
    msg = handler.messages[0]
    assert msg["mail_from"] == "noreply@tweakhub.com"
    assert msg["rcpt_tos"] == ["newuser@example.com"]
    assert "verify-tok-456" in msg["content"]
    assert "https://tweakhub.com/verify-email?token=verify-tok-456" in msg["content"]


def test_smtp_backend_password_reset_email_content(override_settings, smtp_server):
    handler, port = smtp_server
    override_settings(
        email_backend="smtp",
        base_url="https://tweakhub.com",
        smtp_host="127.0.0.1",
        smtp_port=port,
        smtp_use_tls=False,
    )
    service = EmailService()

    service.send_password_reset_email("forgetful@example.com", "reset-tok-789")

    assert len(handler.messages) == 1
    assert "reset-tok-789" in handler.messages[0]["content"]
    assert handler.messages[0]["rcpt_tos"] == ["forgetful@example.com"]


def test_smtp_backend_without_host_configured_raises_clear_error(override_settings):
    override_settings(email_backend="smtp", smtp_host="")
    service = EmailService()

    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        service.send_verification_email("x@example.com", "tok")


def test_unknown_backend_raises_clear_error(override_settings):
    override_settings(email_backend="carrier_pigeon")
    service = EmailService()

    with pytest.raises(RuntimeError, match="carrier_pigeon"):
        service.send_verification_email("x@example.com", "tok")
