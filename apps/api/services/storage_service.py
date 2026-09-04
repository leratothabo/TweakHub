"""
app/services/storage_service.py

Object storage for processed tool outputs (and, for async jobs, the
uploaded input while it waits for a worker). Two backends behind one
interface:

- LocalStorageBackend: writes under STORAGE_LOCAL_DIR on the API
  container's own disk. "Signed URL" here means a short-lived HMAC token
  checked by routes/files.py — no cloud account needed, works out of the
  box for local dev and a single-VPS deploy. It does NOT work if the API
  runs as more than one replica without a shared volume (each replica
  only sees its own disk) — that's the point at which switching to "s3"
  (self-hosted MinIO on the same VPS, or real AWS S3) stops being
  optional. See docs/TODO.md.
- S3StorageBackend: any S3-compatible API via boto3 — real AWS S3, or
  MinIO (set S3_ENDPOINT_URL to MinIO's URL; leave it empty for AWS).
  Signed URLs are real presigned S3 URLs.

Neither backend enforces retention on its own — LocalStorageBackend has
no TTL concept at all, and relying on S3 bucket lifecycle rules would be
invisible to this codebase (and MinIO's lifecycle support is opt-in and
easy to forget to configure). scripts/cleanup_expired_outputs.py is the
one enforcement path that works the same way regardless of backend; see
that file and docs/TODO.md for how it's meant to be scheduled.

Encryption at rest, transparent to every caller (StorageBackend's
interface is unchanged — save()/load() still take/return plain bytes):

- LocalStorageBackend encrypts client-side with Fernet (AES128-CBC + HMAC,
  from the `cryptography` package, already a transitive dependency via
  python-jose[cryptography]) before every write, and decrypts on every
  read. The key is derived (SHA-256, then base64) from
  STORAGE_ENCRYPTION_KEY — or, if that's unset, from JWT_SECRET, so
  encryption is on by default with no extra config needed. A file written
  under one key cannot be read back after that key changes; load() raises
  StorageError with a specific message in that case rather than a raw
  cryptography exception, since "wrong/rotated key" needs a different
  operator response than "file doesn't exist."
- S3StorageBackend passes ServerSideEncryption on every put_object — real
  AWS S3 supports this (SSE-S3, S3-managed keys) with no setup on the
  bucket. Self-hosted MinIO needs its own KMS/encryption configured before
  it will accept the parameter; this codebase has no way to verify that
  from here (this sandbox's network egress blocks reaching MinIO's own
  release host to test against a real instance), so it's documented
  rather than assumed — see config.py's s3_server_side_encryption.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from config import get_settings

logger = logging.getLogger("tweakhub.storage")


def _derive_fernet_key(secret: str) -> bytes:
    """Turns an arbitrary secret string (STORAGE_ENCRYPTION_KEY or
    JWT_SECRET, neither of which is guaranteed to be a valid Fernet key on
    its own — Fernet needs exactly 32 url-safe-base64-encoded bytes) into
    one, deterministically, so the same secret always derives the same
    key and a previously-encrypted file stays readable across restarts."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


class StorageError(Exception):
    pass


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str | None = None) -> None:
        ...

    @abstractmethod
    def load(self, key: str) -> bytes:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Must not raise if the key is already gone — cleanup jobs and
        double-deletes should be no-ops, not errors."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def signed_url(self, key: str, expires_in: int, filename: str | None = None) -> str:
        ...


def _safe_key(key: str) -> str:
    """Reject anything that could escape STORAGE_LOCAL_DIR. Keys are
    always generated server-side (job ids / uuids), never taken verbatim
    from a client, but this is cheap insurance against a future caller
    that forgets that."""
    if not key or key.startswith("/") or ".." in key.split("/"):
        raise StorageError(f"Unsafe storage key: {key!r}")
    return key


class LocalStorageBackend(StorageBackend):
    def __init__(self, base_dir: str, secret: str, encryption_secret: str | None = None) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._secret = secret.encode("utf-8")
        # Falls back to `secret` (JWT_SECRET, via get_storage() below) when
        # no dedicated STORAGE_ENCRYPTION_KEY is set — see the module
        # docstring for the tradeoff that's a deliberate default, not an
        # oversight.
        self._fernet = Fernet(_derive_fernet_key(encryption_secret or secret))

    def _path(self, key: str) -> Path:
        return self.base_dir / _safe_key(key)

    def save(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self._fernet.encrypt(data))

    def load(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"No such object: {key}")
        try:
            return self._fernet.decrypt(path.read_bytes())
        except InvalidToken as exc:
            raise StorageError(
                f"Could not decrypt object {key!r} — STORAGE_ENCRYPTION_KEY (or JWT_SECRET, "
                "if that's what it was encrypted under) may have changed since this was written"
            ) from exc

    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def _sign(self, key: str, expires_at: int) -> str:
        message = f"{key}:{expires_at}".encode("utf-8")
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def verify(self, key: str, expires_at: int, signature: str) -> bool:
        if time.time() > expires_at:
            return False
        expected = self._sign(key, expires_at)
        return hmac.compare_digest(expected, signature)

    def signed_url(self, key: str, expires_in: int, filename: str | None = None) -> str:
        settings = get_settings()
        expires_at = int(time.time()) + expires_in
        signature = self._sign(key, expires_at)
        url = f"{settings.api_url}/api/files/{key}?expires={expires_at}&sig={signature}"
        if filename:
            from urllib.parse import quote

            url += f"&filename={quote(filename)}"
        return url


class S3StorageBackend(StorageBackend):
    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        server_side_encryption: str = "",
    ) -> None:
        if not bucket:
            raise StorageError("S3_BUCKET must be set when STORAGE_BACKEND=s3")

        import boto3  # imported lazily so the "local" backend never needs boto3 installed

        self.bucket = bucket
        self._server_side_encryption = server_side_encryption
        self._client = boto3.client(
            "s3",
            region_name=region or None,
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
        )

    def save(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        if self._server_side_encryption:
            extra["ServerSideEncryption"] = self._server_side_encryption
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)

    def load(self, key: str) -> bytes:
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
        except self._client.exceptions.NoSuchKey as exc:
            raise StorageError(f"No such object: {key}") from exc
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        # S3's delete_object is already idempotent (204 whether or not the
        # key existed), so no existence check needed here.
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise

    def signed_url(self, key: str, expires_in: int, filename: str | None = None) -> str:
        params = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return self._client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=expires_in
        )


@lru_cache
def get_storage() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3StorageBackend(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            server_side_encryption=settings.s3_server_side_encryption,
        )
    if settings.storage_backend != "local":
        logger.warning(
            "Unknown STORAGE_BACKEND=%r — falling back to 'local'", settings.storage_backend
        )
    return LocalStorageBackend(
        base_dir=settings.storage_local_dir,
        secret=settings.jwt_secret,
        encryption_secret=settings.storage_encryption_key or None,
    )
