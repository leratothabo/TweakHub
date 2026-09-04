"""
app/services/job_queue.py

Thin wrapper around RQ (Redis Queue) — enqueue_processing_job() is called
from routes/tools.py right after a ProcessingJob row is created and
committed; the actual work (services/job_worker.run_processing_job) runs
in a separate `rq worker` process (see apps/workers/README.md), not in
the API process.

RQ over Celery: this app already depends on Redis for rate limiting, so
RQ adds no new infrastructure (Celery would want its own broker story
even though it *can* use Redis) — the right choice for "one queue, one
worker pool," not for a system that will eventually need multiple queues
with different routing/retry policies.

Tests set JOB_QUEUE_SYNCHRONOUS=true (see tests/conftest.py's
override_settings) so RQ runs enqueued jobs in-process immediately
instead of waiting for a worker — that exercises the real
job_worker.run_processing_job function end-to-end without needing an
`rq worker` process alongside the test run.
"""
from __future__ import annotations

import redis
from rq import Queue

from config import get_settings
from services.tool_timeouts import get_job_timeout_seconds


def get_queue() -> Queue:
    """Not cached (unlike rate_limiter.get_rate_limiter/storage_service.
    get_storage) because JOB_QUEUE_SYNCHRONOUS is meant to change between
    test runs within the same process, and Queue construction is cheap —
    it doesn't open a connection until a command actually needs one."""
    settings = get_settings()
    redis_url = settings.job_queue_redis_url or settings.redis_url
    connection = redis.Redis.from_url(redis_url)
    return Queue(
        settings.job_queue_name,
        connection=connection,
        is_async=not settings.job_queue_synchronous,
    )


def enqueue_processing_job(job_id: str, tool_name: str | None = None) -> None:
    # tool_name drives a per-tool RQ timeout (services/tool_timeouts.py)
    # instead of one blanket settings.job_timeout_seconds for every async
    # tool. Optional and falls back to the flat setting so any other
    # caller (or a job re-enqueued without knowing its tool name) still
    # gets a safe default rather than an error.
    settings = get_settings()
    job_timeout = get_job_timeout_seconds(tool_name) if tool_name else settings.job_timeout_seconds
    get_queue().enqueue(
        "services.job_worker.run_processing_job",
        job_id,
        job_timeout=job_timeout,
        result_ttl=0,  # the ProcessingJob row is the source of truth, not RQ's own result store
        failure_ttl=3600,  # keep failed-job metadata around briefly for operator debugging
    )
