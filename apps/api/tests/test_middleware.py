"""
Tests for middleware.py's SecurityHeadersMiddleware and
RequestLoggingMiddleware, exercised over real HTTP via the `client`
fixture (main.app with both middlewares actually wired in — not testing
the middleware classes in isolation) so this verifies the real request
path, not just the class logic.
"""
import logging

from deps import create_access_token
from models import PlanTier, User


def test_json_response_gets_strict_csp_and_security_headers(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in resp.headers["Permissions-Policy"]
    assert resp.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    # Dev (NODE_ENV=development in tests, see conftest.py) — HSTS is a
    # production-only header since it's meaningless without HTTPS.
    assert "Strict-Transport-Security" not in resp.headers


def test_docs_page_gets_a_relaxed_csp_that_still_sets_other_headers(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "default-src 'none'" not in resp.headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in resp.headers["Content-Security-Policy"]
    # Still gets the headers that don't conflict with rendering Swagger UI.
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_hsts_header_present_in_production(client, override_settings):
    override_settings(node_env="production")
    resp = client.get("/health")
    assert resp.headers["Strict-Transport-Security"] == "max-age=63072000; includeSubDomains"


def test_error_response_still_gets_security_headers(client):
    # A 404 goes through ExceptionMiddleware, not a normal route handler —
    # confirms the security headers apply regardless of how the response
    # was produced, not just on the happy path.
    resp = client.get("/api/tools/not_a_real_tool/does_not_exist")
    assert resp.status_code == 404
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def _collect_access_logs(fn):
    """Runs fn() while capturing tweakhub.access records directly (that
    logger sets propagate=False, same reasoning/pattern as
    test_email_service.py's console-backend test — pytest's caplog relies
    on root-logger propagation, so it never sees these records)."""
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    target_logger = logging.getLogger("tweakhub.access")
    collector = _Collector()
    target_logger.addHandler(collector)
    try:
        fn()
    finally:
        target_logger.removeHandler(collector)
    return records


def test_access_log_records_method_path_and_status(client):
    records = _collect_access_logs(lambda: client.get("/health"))
    assert len(records) == 1
    message = records[0].getMessage()
    assert "GET" in message
    assert "/health" in message
    assert "status=200" in message


def test_access_log_never_includes_query_string_or_auth_header(client):
    # download_url tokens (routes/files.py) live in the query string —
    # logging them would defeat the point of a signed URL. Use a bogus
    # signed-file request as a stand-in for "a URL with a sensitive query
    # param" without needing a real successful download.
    records = _collect_access_logs(
        lambda: client.get(
            "/api/files/some-key?sig=super-secret-token-should-never-be-logged",
            headers={"Authorization": "Bearer should-also-never-be-logged"},
        )
    )
    assert len(records) == 1
    message = records[0].getMessage()
    assert "super-secret-token-should-never-be-logged" not in message
    assert "should-also-never-be-logged" not in message


def test_access_log_includes_user_id_for_an_authenticated_request(client, db_session):
    user = User(email="mw-test@example.com", credit_balance=100, plan_tier=PlanTier.FREE)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id)

    records = _collect_access_logs(
        lambda: client.get("/api/credits/balance", headers={"Authorization": f"Bearer {token}"})
    )
    assert len(records) == 1
    assert f"user={user.id}" in records[0].getMessage()


def test_access_log_shows_placeholder_user_for_unauthenticated_request(client):
    records = _collect_access_logs(lambda: client.get("/health"))
    assert "user=-" in records[0].getMessage()
