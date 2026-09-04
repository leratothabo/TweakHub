"""
Shared pytest fixtures. Auth/DB tests run against a throwaway SQLite file
DB rather than the real Postgres — good enough to exercise SQLAlchemy
model behavior and service logic without requiring a running Postgres
instance in CI. NODE_ENV is forced to "development" for the test process
so auth_service.login's email-verification bypass matches what the tests
expect (see services/auth_service.py's login docstring).
"""
import os
import sys

os.environ.setdefault("NODE_ENV", "development")
os.environ["DATABASE_URL"] = "sqlite:///./_test.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from config import get_settings  # noqa: E402

get_settings.cache_clear()

from db import Base, SessionLocal, engine  # noqa: E402
import models  # noqa: E402,F401


@pytest.fixture()
def db_session():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def fake_rate_limiter():
    """Points the shared RateLimiter singleton at an in-memory fakeredis
    instance instead of a real Redis server, so rate-limit tests are
    deterministic and don't need Redis running. Patches
    RateLimiter._get_client on the class (rather than swapping the
    get_rate_limiter function) so it doesn't matter which module imported
    get_rate_limiter — deps.py, routes/tools.py, and routes/payments.py
    all end up hitting the same fake client."""
    import fakeredis

    from services import rate_limiter as rate_limiter_module

    fake_client = fakeredis.FakeRedis()
    original_get_client = rate_limiter_module.RateLimiter._get_client
    rate_limiter_module.RateLimiter._get_client = lambda self: fake_client
    rate_limiter_module.get_rate_limiter.cache_clear()
    try:
        yield fake_client
    finally:
        rate_limiter_module.RateLimiter._get_client = original_get_client
        rate_limiter_module.get_rate_limiter.cache_clear()
        fake_client.flushall()


@pytest.fixture()
def local_storage(tmp_path, override_settings):
    """Points services.storage_service.get_storage() at a throwaway
    directory instead of the repo's real ./storage_outputs, and clears
    its lru_cache so the override actually takes effect. Every HTTP-level
    test goes through this via the `client` fixture; storage_service unit
    tests can also depend on it directly."""
    from services import storage_service as storage_service_module

    override_settings(storage_backend="local", storage_local_dir=str(tmp_path / "storage_outputs"))
    storage_service_module.get_storage.cache_clear()
    try:
        yield storage_service_module.get_storage()
    finally:
        storage_service_module.get_storage.cache_clear()


def _redis_reachable() -> bool:
    import redis

    from config import get_settings

    try:
        redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1).ping()
        return True
    except redis.RedisError:
        return False


needs_redis = pytest.mark.skipif(
    not _redis_reachable(),
    reason="Redis not reachable at REDIS_URL — RQ needs a real Redis (see test_job_queue.py)",
)


@pytest.fixture()
def client(db_session, fake_rate_limiter, local_storage):
    """A TestClient wired to the same throwaway SQLite session as
    db_session (so assertions can inspect what a request wrote) and to the
    fake Redis-backed rate limiter, so HTTP-level tests never touch a real
    Postgres or Redis. httpx's ASGITransport reports a fixed synthetic
    client address (127.0.0.1) for every request unless a test overrides
    it with an X-Forwarded-For header — deps.get_client_ip() checks that
    header first, same as it would behind the real nginx proxy in
    infrastructure/nginx/nginx.conf."""
    from fastapi.testclient import TestClient

    from db import get_db
    from main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def override_settings(monkeypatch):
    """Set one or more Settings fields for the duration of a test via env
    vars, clearing the get_settings() lru_cache before and after so the
    change actually takes effect. Usage: override_settings(rate_limit_signup_per_hour=2)."""
    from config import get_settings

    def _apply(**fields):
        for key, value in fields.items():
            monkeypatch.setenv(key.upper(), str(value))
        get_settings.cache_clear()

    yield _apply
    get_settings.cache_clear()


@pytest.fixture()
def sample_pdf_bytes() -> bytes:
    """A real, valid 2-page PDF — not a mock. Engine tests run this through
    actual pikepdf/pypdf/poppler/etc, not a fake."""
    import io as _io

    from reportlab.pdfgen import canvas

    buf = _io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "TweakHub test document — page 1")
    c.showPage()
    c.drawString(100, 750, "page 2")
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture()
def sample_png_bytes() -> bytes:
    import io as _io

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 300), (255, 120, 60))
    d = ImageDraw.Draw(img)
    d.text((10, 10), "TweakHub", fill=(255, 255, 255))
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
