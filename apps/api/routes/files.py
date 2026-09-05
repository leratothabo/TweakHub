"""
app/routes/files.py

Serves LocalStorageBackend objects via a signed URL (HMAC token + expiry
in the query string) — the same shape as an S3 presigned URL, so
routes/tools.py and routes/jobs.py can hand back a `download_url` that
works identically regardless of which storage backend is configured. When
STORAGE_BACKEND=s3, `download_url` is a real S3 presigned URL instead and
this route is never used.

Deliberately has no bearer-auth dependency: the signature *is* the
authorization, exactly like a presigned S3 URL — anyone with the link can
download until it expires, and that's the intended behavior (it's what
lets a browser follow the link directly rather than needing to attach an
Authorization header).
"""
from __future__ import annotations

import mimetypes
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from services.storage_service import LocalStorageBackend, StorageError, get_storage

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{key:path}")
def download_file(
    key: str,
    expires: int = Query(...),
    sig: str = Query(...),
    filename: str | None = Query(default=None),
):
    backend = get_storage()
    if not isinstance(backend, LocalStorageBackend):
        # STORAGE_BACKEND=s3 — clients should have been handed a real S3
        # presigned URL, not one of these, so reaching here means a stale
        # link from before a backend switch.
        raise HTTPException(status_code=404, detail="Not found")

    if not backend.verify(key, expires, sig, filename):
        raise HTTPException(status_code=403, detail="Link is invalid or has expired")

    try:
        data = backend.load(key)
    except StorageError:
        raise HTTPException(status_code=404, detail="File not found (it may have expired)")

    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    disposition_name = unquote(filename) if filename else key.rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{disposition_name}"'},
    )
