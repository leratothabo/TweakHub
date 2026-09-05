"""
app/routes/tools.py

Public tool catalog + the core "run a tool" endpoint: validate the upload
against the user's plan limit, price it via CreditService, spend credits,
and run it through ToolRouter — refunding on failure so a broken engine
never silently costs the user credits.

Every call creates a ProcessingJob row (models/processing_job.py). Most
tools resolve it inline, in this request, and the output goes straight to
object storage (services/storage_service.py) with the response carrying a
signed `download_url` rather than the file bytes themselves — the change
from the previous phase, where the response body *was* the file. Tools in
ASYNC_TOOL_NAMES (video-category tools, and everything routed to the
`document` engine — LibreOffice/Playwright/OCR, all meaningfully slower
than the in-memory PDF/image engines) skip straight to `202 Accepted`
with the job PENDING; an rq worker (services/job_worker.py) picks it up
from there. GET /api/jobs/{id} (routes/jobs.py) is how a client finds out
when an async job finishes — same response shape either way, since
services/job_presenter.py builds it from the same ProcessingJob row.
"""
from __future__ import annotations

import io
import json
import mimetypes
import pickle
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from deps import get_current_user
from models import JobStatus, PlanTier, ProcessingJob, User
from services import ToolRouter, UnknownToolError, credit_service
from services.job_presenter import job_to_response
from services.job_queue import enqueue_processing_job
from services.rate_limiter import get_rate_limiter
from services.storage_service import get_storage
from services.tools_catalog import list_tools

router = APIRouter(prefix="/api/tools", tags=["tools"])
tool_router = ToolRouter()

PLAN_LIMITS_MB = {
    PlanTier.FREE: "max_upload_mb_free",
    PlanTier.PRO: "max_upload_mb_pro",
    PlanTier.BUSINESS: "max_upload_mb_business",
    PlanTier.ENTERPRISE: None,  # unlimited
}

# Same shape as PLAN_LIMITS_MB, keyed to hourly request-count limits instead
# of upload size. ENTERPRISE stays unmetered, same rationale as above.
PLAN_RATE_LIMITS_PER_HOUR = {
    PlanTier.FREE: "rate_limit_free_per_hour",
    PlanTier.PRO: "rate_limit_pro_per_hour",
    PlanTier.BUSINESS: "rate_limit_business_per_hour",
    PlanTier.ENTERPRISE: None,  # unlimited
}

# Computed from the catalog, not hand-maintained, so tool #71 through #200
# fall on the right side of this automatically as long as their category/
# engine is accurate: every video-category tool (ffmpeg on real video is
# slow) and every tool the `document` engine handles (LibreOffice headless
# and Playwright+Chromium are both subprocesses, plus OCR — all
# meaningfully slower than the in-memory pypdf/pikepdf/Pillow engines).
# See docs/engines.md for the current resolved list.
ASYNC_TOOL_NAMES: frozenset[str] = frozenset(
    t.name for t in list_tools() if t.category == "video" or t.engine == "document"
)


@router.get("")
def get_tools(category: str | None = None):
    """List available tools, optionally filtered by category (pdf, image, video, audio, document)."""
    specs = list_tools(category)
    return {
        "count": len(specs),
        "tools": [
            {
                "name": t.name,
                "label": t.label,
                "category": t.category,
                "base_credits": t.base_credits,
                "is_async": t.name in ASYNC_TOOL_NAMES,
            }
            for t in specs
        ],
    }


@router.post("/{tool_name}/process")
async def process_tool(
    tool_name: str,
    file: UploadFile = File(...),
    extra_files: list[UploadFile] = File(default=[]),
    options: str = Form(default="{}"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    `extra_files` is for tools that combine multiple inputs (pdf_merge,
    video_merge, audio_merge, pdf_compare, subtitle_burn). `options` is a
    JSON object of tool-specific parameters (e.g. {"angle": 180} for
    pdf_rotate, {"password": "..."} for pdf_protect, {"target_format":
    "webp"} for image_convert) — see docs/engines.md for what each tool
    reads.

    Returns `200` with a `download_url` once processing is done (most
    tools — this happens inline, in this same request), or `202` with a
    `job_id` for async tools (see ASYNC_TOOL_NAMES above) — poll
    GET /api/jobs/{job_id} until its status leaves pending/processing.
    """
    settings = get_settings()

    rate_limit_attr = PLAN_RATE_LIMITS_PER_HOUR.get(user.plan_tier)
    if rate_limit_attr:
        limit = getattr(settings, rate_limit_attr)
        result = get_rate_limiter().hit(f"tool_process:{user.id}", limit, window_seconds=3600)
        if not result.allowed:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded for the {user.plan_tier.value} plan "
                    f"({limit} requests/hour). Try again later."
                ),
                headers={"Retry-After": str(result.retry_after_seconds)},
            )

    try:
        spec = tool_router.get_tool_spec(tool_name)
    except UnknownToolError:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")

    try:
        parsed_options = json.loads(options) if options else {}
        if not isinstance(parsed_options, dict):
            raise ValueError("options must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid options JSON: {exc}")

    raw = await file.read()
    extra_raw = [await f.read() for f in extra_files]

    total_size_mb = (len(raw) + sum(len(b) for b in extra_raw)) / (1024 * 1024)

    limit_attr = PLAN_LIMITS_MB.get(user.plan_tier)
    if limit_attr:
        limit_mb = getattr(settings, limit_attr)
        if total_size_mb > limit_mb:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {limit_mb} MB limit for the {user.plan_tier.value} plan",
            )

    try:
        tx = credit_service.spend_credits(db, user, tool_name, total_size_mb)
    except Exception as exc:  # InsufficientCreditsError
        raise HTTPException(status_code=402, detail=str(exc))

    job = ProcessingJob(
        user_id=user.id,
        tool_name=tool_name,
        is_async=tool_name in ASYNC_TOOL_NAMES,
        credit_transaction_id=tx.id,
        credits_spent=-tx.amount,
        options_json=json.dumps(parsed_options),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if job.is_async:
        # The worker runs in a separate process (possibly a separate
        # machine) and can't read `raw`/`extra_raw` out of this request,
        # so they go to object storage first — bundled together with
        # pickle rather than as two storage objects, since it's our own
        # server-generated data round-tripping through our own storage,
        # not untrusted input (see storage_service.py's key-safety note
        # for the boundary that *does* need to stay careful).
        storage = get_storage()
        input_key = f"inputs/{job.id}"
        storage.save(input_key, pickle.dumps({"raw": raw, "extra": extra_raw}))
        job.input_storage_key = input_key
        db.add(job)
        db.commit()
        db.refresh(job)

        enqueue_processing_job(job.id, tool_name=tool_name)
        # In production this job is still PENDING here — a real worker
        # process picks it up later. In tests (JOB_QUEUE_SYNCHRONOUS=true,
        # see services/job_queue.py) enqueue_processing_job() just ran it
        # to completion in-process, so refreshing can reveal it's already
        # SUCCEEDED/FAILED — report that accurately rather than a stale 202.
        db.refresh(job)

        payload = job_to_response(job)
        payload["credit_balance"] = credit_service.get_effective_balance(db, user)
        still_running = job.status in (JobStatus.PENDING, JobStatus.PROCESSING)
        return JSONResponse(status_code=202 if still_running else 200, content=payload)

    # --- synchronous path: resolve inline, in this request ---
    job.status = JobStatus.PROCESSING
    job.started_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()

    engine_options = dict(parsed_options)
    if extra_raw:
        engine_options["extra_files"] = extra_raw

    result = tool_router.route_tool(tool_name, io.BytesIO(raw), engine_options)

    if not result.ok:
        if result.refundable:
            credit_service.refund_credits(
                db, user, tool_name, amount=job.credits_spent, note=f"Refund: {result.error}",
                original_transaction=tx,
            )
            job.error = result.error
        else:
            # Failure was caused by the input/options the user sent (bad
            # password, corrupted file, invalid options, ...) — no refund,
            # but say so on the job record so support/the user can see why.
            job.error = f"{result.error} (not refunded: failure caused by input/options, not a TweakHub error)"
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Processing failed: {result.error}")

    ext = mimetypes.guess_extension(result.content_type or "") or ""
    output_key = f"outputs/{job.id}{ext}"
    get_storage().save(output_key, result.output_bytes, result.content_type)

    job.status = JobStatus.SUCCEEDED
    job.output_storage_key = output_key
    job.content_type = result.content_type or "application/octet-stream"
    job.filename = f"{spec.name}{ext}"
    job.meta_json = json.dumps(result.meta or {})
    job.finished_at = datetime.now(timezone.utc)
    job.expires_at = job.finished_at + timedelta(hours=settings.file_retention_hours)
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = job_to_response(job)
    payload["credit_balance"] = credit_service.get_effective_balance(db, user)
    return payload
