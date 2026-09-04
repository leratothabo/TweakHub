"""
app/services/job_presenter.py

Turns a ProcessingJob row into the JSON shape handed back to clients —
shared by routes/tools.py (the response to POST .../process, sync or
async) and routes/jobs.py (GET /api/jobs/{id}, GET /api/jobs), so the two
call sites can't drift into different shapes for what is, underneath,
the exact same row.
"""
from __future__ import annotations

import json

from config import get_settings
from models import JobStatus, ProcessingJob
from services.storage_service import get_storage


def job_to_response(job: ProcessingJob) -> dict:
    payload: dict = {
        "job_id": job.id,
        "tool_name": job.tool_name,
        "status": job.status.value,
        "is_async": job.is_async,
        "credits_spent": job.credits_spent,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }

    if job.status == JobStatus.SUCCEEDED and job.output_storage_key:
        settings = get_settings()
        payload.update(
            {
                "download_url": get_storage().signed_url(
                    job.output_storage_key,
                    settings.signed_url_expires_seconds,
                    filename=job.filename,
                ),
                "content_type": job.content_type,
                "filename": job.filename,
                "expires_at": job.expires_at.isoformat() if job.expires_at else None,
                "meta": json.loads(job.meta_json) if job.meta_json else {},
            }
        )
    elif job.status == JobStatus.SUCCEEDED:
        # Succeeded once, but the output has since been purged — see
        # scripts/cleanup_expired_outputs.py. Surface this distinctly
        # rather than as a plain "succeeded" with no download_url.
        payload["status"] = "expired"
    elif job.status == JobStatus.FAILED:
        payload["error"] = job.error

    return payload
