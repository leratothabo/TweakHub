"""
app/services/job_worker.py

run_processing_job() is the actual work behind an async tool run — it's
what `rq worker` (see apps/workers/README.md) calls when it pulls a job
off the queue that services/job_queue.py enqueued. It never runs inside
the API process except in tests (JOB_QUEUE_SYNCHRONOUS=true makes RQ call
it in-process, synchronously, right from Queue.enqueue()).

Deliberately opens its own DB session (SessionLocal directly, not the
`get_db` FastAPI dependency) — there's no request to scope a session to
here, this function's only "request" is a job_id pulled off Redis.
"""
from __future__ import annotations

import io
import json
import logging
import mimetypes
import pickle
from datetime import datetime, timedelta, timezone

from config import get_settings
from db import SessionLocal
from models import JobStatus, ProcessingJob, User
from services import credit_service
from services.storage_service import StorageError, get_storage
from services.tool_router import ToolRouter

logger = logging.getLogger("tweakhub.job_worker")

# One ToolRouter per worker process is fine — the engines it holds are
# stateless (each call gets fresh scratch dirs, see engines/_util.py).
_tool_router = ToolRouter()


def _fail_job(db, job: ProcessingJob, error: str) -> None:
    user = db.get(User, job.user_id)
    if user is not None and job.credits_spent:
        credit_service.refund_credits(
            db, user, job.tool_name, amount=job.credits_spent, note=f"Refund: {error}"
        )
    job.status = JobStatus.FAILED
    job.error = error
    job.finished_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()


def run_processing_job(job_id: str) -> None:
    db = SessionLocal()
    job: ProcessingJob | None = None
    try:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            logger.error("run_processing_job: no ProcessingJob with id=%s", job_id)
            return

        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()

        storage = get_storage()

        try:
            bundle = pickle.loads(storage.load(job.input_storage_key))
        except (StorageError, pickle.PickleError) as exc:
            logger.error("Job %s: could not load input (%s)", job.id, exc)
            _fail_job(db, job, f"Could not load input for processing: {exc}")
            return

        options = json.loads(job.options_json) if job.options_json else {}
        if bundle.get("extra"):
            options["extra_files"] = bundle["extra"]

        try:
            result = _tool_router.route_tool(job.tool_name, io.BytesIO(bundle["raw"]), options)
        except Exception as exc:  # an engine bug that escaped EngineResult(ok=False) — still
            # shouldn't wedge the job in PROCESSING forever, so fail it
            # cleanly and re-raise so RQ's own failure tracking sees it too.
            logger.exception("Job %s: unhandled error in %s", job.id, job.tool_name)
            _fail_job(db, job, f"Unexpected processing error: {exc}")
            raise

        if not result.ok:
            _fail_job(db, job, result.error or "Processing failed")
            return

        spec = _tool_router.get_tool_spec(job.tool_name)
        ext = mimetypes.guess_extension(result.content_type or "") or ""
        output_key = f"outputs/{job.id}{ext}"
        storage.save(output_key, result.output_bytes, result.content_type)

        settings = get_settings()
        job.status = JobStatus.SUCCEEDED
        job.output_storage_key = output_key
        job.content_type = result.content_type or "application/octet-stream"
        job.filename = f"{spec.name}{ext}"
        job.meta_json = json.dumps(result.meta or {})
        job.finished_at = datetime.now(timezone.utc)
        job.expires_at = job.finished_at + timedelta(hours=settings.file_retention_hours)
        db.add(job)
        db.commit()
    finally:
        # The input is only ever needed to run the job once — drop it
        # whether the job succeeded or failed, so storage doesn't
        # accumulate every upload forever alongside the retained outputs.
        if job is not None and job.input_storage_key:
            try:
                get_storage().delete(job.input_storage_key)
            except Exception:
                logger.exception("Job %s: failed to delete input object", job.id)
        db.close()
