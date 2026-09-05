"""
Unit tests for services/storage_service.py. LocalStorageBackend is
exercised directly against a throwaway directory (via the `local_storage`
fixture); S3StorageBackend is exercised against a mocked S3 API (moto)
rather than skipped outright — the S3 code path (boto3 client
construction, put/get/delete/presign) is real enough to be worth
verifying without needing real AWS credentials or a running MinIO.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.storage_service import StorageError, _safe_key  # noqa: E402


def test_local_backend_save_load_roundtrip(local_storage):
    local_storage.save("outputs/a.txt", b"hello world", "text/plain")
    assert local_storage.load("outputs/a.txt") == b"hello world"
    assert local_storage.exists("outputs/a.txt") is True


def test_local_backend_load_missing_key_raises(local_storage):
    with pytest.raises(StorageError):
        local_storage.load("outputs/does-not-exist.txt")


def test_local_backend_exists_false_for_missing_key(local_storage):
    assert local_storage.exists("outputs/nope.bin") is False


def test_local_backend_delete_is_idempotent(local_storage):
    local_storage.save("outputs/b.txt", b"x")
    local_storage.delete("outputs/b.txt")
    assert local_storage.exists("outputs/b.txt") is False
    local_storage.delete("outputs/b.txt")  # second delete must not raise


def test_safe_key_rejects_path_traversal():
    with pytest.raises(StorageError):
        _safe_key("../../etc/passwd")
    with pytest.raises(StorageError):
        _safe_key("/etc/passwd")
    with pytest.raises(StorageError):
        _safe_key("")


def test_local_backend_signed_url_round_trips(local_storage):
    local_storage.save("outputs/c.pdf", b"%PDF-fake", "application/pdf")
    url = local_storage.signed_url("outputs/c.pdf", expires_in=60, filename="result.pdf")

    assert "expires=" in url and "sig=" in url and "filename=result.pdf" in url

    # Pull the key/expires/sig/filename back out the way routes/files.py's
    # query params would arrive, and confirm verify() accepts them —
    # filename is part of what's signed (see storage_service.py's _sign),
    # so it has to be passed through here too, not just key/expires/sig.
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert (
        local_storage.verify(
            "outputs/c.pdf", int(qs["expires"][0]), qs["sig"][0], qs["filename"][0]
        )
        is True
    )


def test_local_backend_signed_url_rejects_tampered_filename(local_storage):
    """filename is signed alongside key/expires_at specifically so a
    holder of a valid link can't rewrite it to spoof the suggested
    save-as name — verify() must reject a signature computed for one
    filename when checked against a different one."""
    local_storage.save("outputs/c2.pdf", b"%PDF-fake", "application/pdf")
    url = local_storage.signed_url("outputs/c2.pdf", expires_in=60, filename="real.pdf")
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(url).query)
    expires, sig = int(qs["expires"][0]), qs["sig"][0]

    assert local_storage.verify("outputs/c2.pdf", expires, sig, "real.pdf") is True
    assert local_storage.verify("outputs/c2.pdf", expires, sig, "spoofed.pdf") is False
    assert local_storage.verify("outputs/c2.pdf", expires, sig, None) is False


def test_local_backend_signed_url_rejects_tampered_signature(local_storage):
    local_storage.save("outputs/d.pdf", b"data")
    url = local_storage.signed_url("outputs/d.pdf", expires_in=60)
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(url).query)
    expires = int(qs["expires"][0])
    assert local_storage.verify("outputs/d.pdf", expires, "0" * 64) is False


def test_local_backend_signed_url_rejects_expired_link(local_storage):
    local_storage.save("outputs/e.pdf", b"data")
    expires_at = int(time.time()) - 10  # already in the past
    signature = local_storage._sign("outputs/e.pdf", expires_at)
    assert local_storage.verify("outputs/e.pdf", expires_at, signature) is False


def test_local_backend_signed_url_rejects_wrong_key(local_storage):
    local_storage.save("outputs/f.pdf", b"data")
    url = local_storage.signed_url("outputs/f.pdf", expires_in=60)
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(url).query)
    expires = int(qs["expires"][0])
    sig = qs["sig"][0]
    # Same signature, different key — must not verify.
    assert local_storage.verify("outputs/other-key.pdf", expires, sig) is False


def test_s3_backend_save_load_delete_roundtrip(override_settings):
    moto = pytest.importorskip("moto")
    with moto.mock_aws():
        import boto3

        from services.storage_service import S3StorageBackend

        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="tweakhub-test-bucket")

        backend = S3StorageBackend(
            bucket="tweakhub-test-bucket",
            region="us-east-1",
            endpoint_url="",
            access_key_id="",
            secret_access_key="",
        )
        backend.save("outputs/g.txt", b"s3 hello", "text/plain")
        assert backend.exists("outputs/g.txt") is True
        assert backend.load("outputs/g.txt") == b"s3 hello"

        url = backend.signed_url("outputs/g.txt", expires_in=60, filename="g.txt")
        assert "tweakhub-test-bucket" in url

        backend.delete("outputs/g.txt")
        assert backend.exists("outputs/g.txt") is False


def test_local_backend_encrypts_bytes_on_disk(local_storage):
    # The roundtrip tests above only prove save()/load() round-trips
    # transparently — that alone wouldn't catch a no-op "encryption" that
    # just stores the plaintext. Read the raw file off disk directly and
    # confirm it's neither the plaintext nor something that merely
    # contains it as a substring.
    plaintext = b"this is definitely not encrypted if you can read it"
    local_storage.save("outputs/plain-check.bin", plaintext)

    raw_on_disk = (local_storage.base_dir / "outputs" / "plain-check.bin").read_bytes()
    assert raw_on_disk != plaintext
    assert plaintext not in raw_on_disk


def test_local_backend_wrong_encryption_key_fails_to_decrypt(tmp_path):
    from services.storage_service import LocalStorageBackend

    base_dir = str(tmp_path / "storage")
    writer = LocalStorageBackend(base_dir=base_dir, secret="jwt-secret-a", encryption_secret="key-one")
    writer.save("outputs/h.txt", b"secret contents")

    reader = LocalStorageBackend(base_dir=base_dir, secret="jwt-secret-a", encryption_secret="key-two")
    with pytest.raises(StorageError, match="Could not decrypt"):
        reader.load("outputs/h.txt")

    # The original key still reads it back fine — the file itself wasn't
    # corrupted, only decrypting it under the wrong key fails.
    assert writer.load("outputs/h.txt") == b"secret contents"


def test_local_backend_falls_back_to_jwt_secret_when_no_dedicated_key_set(tmp_path):
    from services.storage_service import LocalStorageBackend

    base_dir = str(tmp_path / "storage")
    # No encryption_secret passed — should derive from `secret` (mirrors
    # get_storage() passing settings.jwt_secret when
    # STORAGE_ENCRYPTION_KEY is unset).
    writer = LocalStorageBackend(base_dir=base_dir, secret="the-jwt-secret")
    writer.save("outputs/i.txt", b"fallback-key contents")

    reader = LocalStorageBackend(base_dir=base_dir, secret="the-jwt-secret")
    assert reader.load("outputs/i.txt") == b"fallback-key contents"

    other = LocalStorageBackend(base_dir=base_dir, secret="a-different-jwt-secret")
    with pytest.raises(StorageError, match="Could not decrypt"):
        other.load("outputs/i.txt")


def test_s3_backend_requests_server_side_encryption(override_settings):
    moto = pytest.importorskip("moto")
    with moto.mock_aws():
        import boto3

        from services.storage_service import S3StorageBackend

        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="tweakhub-sse-bucket")

        backend = S3StorageBackend(
            bucket="tweakhub-sse-bucket",
            region="us-east-1",
            endpoint_url="",
            access_key_id="",
            secret_access_key="",
            server_side_encryption="AES256",
        )
        backend.save("outputs/j.txt", b"sse hello")

        # moto tracks and echoes back whatever encryption was requested on
        # put_object — assert on the real head_object response rather than
        # inspecting call args, so this fails if save() ever stops passing
        # the parameter through.
        head = backend._client.head_object(Bucket="tweakhub-sse-bucket", Key="outputs/j.txt")
        assert head.get("ServerSideEncryption") == "AES256"


def test_s3_backend_skips_encryption_param_when_disabled(override_settings):
    moto = pytest.importorskip("moto")
    with moto.mock_aws():
        import boto3

        from services.storage_service import S3StorageBackend

        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="tweakhub-no-sse-bucket")

        backend = S3StorageBackend(
            bucket="tweakhub-no-sse-bucket",
            region="us-east-1",
            endpoint_url="",
            access_key_id="",
            secret_access_key="",
            server_side_encryption="",
        )
        backend.save("outputs/k.txt", b"no sse here")

        head = backend._client.head_object(Bucket="tweakhub-no-sse-bucket", Key="outputs/k.txt")
        assert "ServerSideEncryption" not in head


def test_get_storage_falls_back_to_local_for_unknown_backend(override_settings):
    from services import storage_service as storage_service_module

    override_settings(storage_backend="not-a-real-backend")
    storage_service_module.get_storage.cache_clear()
    try:
        backend = storage_service_module.get_storage()
        assert isinstance(backend, storage_service_module.LocalStorageBackend)
    finally:
        storage_service_module.get_storage.cache_clear()
