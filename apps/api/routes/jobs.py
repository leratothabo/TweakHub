"""
app/routes/jobs.py

Status/result lookup for tool runs. Every call to
POST /api/tools/{tool_name}/process creates a ProcessingJob row — for the
"slow" tools in routes/tools.py's ASYNC_TOOL_NAMES it's created PENDING
and picked up by an rq worker (apps/api/services/job_worker.py); for
everything else it's created and resolved inline in that same request.
Either way, this router is how a client checks on it afterwards — the
frontend polls GET /api/jobs/{id} for async tools until status leaves
"pending"/"processing".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user
from models import ProcessingJob, User
from services.job_presenter import job_to_response

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(ProcessingJob, job_id)
    if job is None or job.user_id != user.id:
        # Same 404 either way — a job that exists but belongs to someone
        # else shouldn't be distinguishable from one that doesn't exist.
        raise HTTPException(status_code=404, detail="No such job")

    payload = job_to_response(job)
    payload["credit_balance"] = user.credit_balance
    return payload


@router.get("")
def list_jobs(
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.user_id == user.id)
        .order_by(desc(ProcessingJob.created_at))
        .limit(limit)
        .all()
    )
    return {"jobs": [job_to_response(job) for job in jobs]}
