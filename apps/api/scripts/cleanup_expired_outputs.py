"""
apps/api/scripts/cleanup_expired_outputs.py

Enforces the 24-48h output retention policy (FILE_RETENTION_HOURS,
default 48). Neither storage backend does this on its own —
LocalStorageBackend has no TTL concept at all, and while S3/MinIO bucket
lifecycle rules *can* expire objects automatically, configuring them is a
separate, easy-to-forget step outside this codebase, and this script
would still be needed to null out ProcessingJob.output_storage_key so the
API stops handing out download_url values for objects that no longer
exist. So: run this regardless of backend.

Deletes the storage object for every SUCCEEDED job whose expires_at has
passed and clears output_storage_key on the row (the row itself is kept —
job history/audit trail, and services/job_presenter.py already reports
`status: "expired"` for a succeeded job with no output_storage_key).

Usage:
    cd apps/api && source .venv/bin/activate
    python -m scripts.cleanup_expired_outputs

Meant to run on a schedule (hourly is reasonable given the 24-48h window)
— there's no scheduler wired up in this repo yet, so add it to the VPS's
crontab after deploy, e.g.:
    0 * * * * cd /path/to/tweakhub/apps/api && .venv/bin/python -m scripts.cleanup_expired_outputs >> /var/log/tweakhub-cleanup.log 2>&1
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tweakhub.cleanup")


def cleanup_expired_outputs(batch_size: int = 500) -> int:
    """Returns the number of jobs cleaned up. Importable so tests can call
    it directly against a throwaway DB rather than shelling out."""
    from db import SessionLocal
    from models import JobStatus, ProcessingJob
    from services.storage_service import StorageError, get_storage

    db = SessionLocal()
    storage = get_storage()
    cleaned = 0
    try:
        now = datetime.now(timezone.utc)
        expired = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.status == JobStatus.SUCCEEDED,
                ProcessingJob.output_storage_key.isnot(None),
                ProcessingJob.expires_at.isnot(None),
                ProcessingJob.expires_at <= now,
            )
            .limit(batch_size)
            .all()
        )

        for job in expired:
            try:
                storage.delete(job.output_storage_key)
            except StorageError as exc:
                # Already gone (deleted out-of-band, or a previous run
                # crashed after deleting but before committing the row
                # update) — still clear the key so we don't retry forever.
                logger.warning("Job %s: storage delete failed (%s) — clearing key anyway", job.id, exc)
            job.output_storage_key = None
            db.add(job)
            cleaned += 1

        db.commit()
    finally:
        db.close()

    return cleaned


def main() -> None:
    cleaned = cleanup_expired_outputs()
    logger.info("Cleaned up %d expired output(s)", cleaned)


if __name__ == "__main__":
    main()
