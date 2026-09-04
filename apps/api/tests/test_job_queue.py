"""
Tests for services/job_queue.py — specifically, that
enqueue_processing_job() really resolves the dotted string
"services.job_worker.run_processing_job" through RQ and Redis, not just
that job_worker's function works when called directly (that's already
covered by test_job_worker.py). A typo in that dotted path is exactly the
kind of bug unit-testing job_worker.py in isolation would never catch.

Needs a real Redis (see conftest.py's needs_redis — RQ's registries and
Lua scripts aren't reliably emulated by fakeredis, unlike the simple
INCR/EXPIRE the rate limiter uses). JOB_QUEUE_SYNCHRONOUS=true makes RQ
run the job in-process immediately rather than waiting for a separate
`rq worker`, so these tests don't need one running alongside pytest.
"""
import json
import os
import pickle
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import JobStatus, PlanTier, ProcessingJob, User  # noqa: E402
from services.job_queue import enqueue_processing_job, get_queue  # noqa: E402


def _redis_reachable() -> bool:
    import redis

    from config import get_settings

    try:
        redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1).ping()
        return True
    except redis.RedisError:
        return False


needs_redis = pytest.mark.skipif(
    not _redis_reachable(), reason="Redis not reachable at REDIS_URL"
)


@needs_redis
def test_get_queue_uses_configured_name(override_settings):
    override_settings(job_queue_name=f"test-queue-{uuid.uuid4().hex[:8]}", job_queue_synchronous=True)
    queue = get_queue()
    assert queue.name.startswith("test-queue-")


@needs_redis
def test_enqueue_processing_job_runs_synchronously_in_tests(db_session, local_storage, override_settings, sample_pdf_bytes):
    override_settings(job_queue_synchronous=True, job_queue_name=f"test-{uuid.uuid4().hex[:8]}")

    user = User(email="queue-test@example.com", credit_balance=100, plan_tier=PlanTier.FREE)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    job = ProcessingJob(
        user_id=user.id,
        tool_name="html_to_pdf",
        is_async=True,
        credits_spent=5,
        options_json=json.dumps({}),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    input_key = f"inputs/{job.id}"
    local_storage.save(input_key, pickle.dumps({"raw": b"<html><body>hi</body></html>", "extra": []}))
    job.input_storage_key = input_key
    db_session.add(job)
    db_session.commit()

    # This is the real integration point: enqueue_processing_job() must
    # resolve "services.job_worker.run_processing_job" through RQ/Redis
    # and actually call it — not just prove job_worker works when called
    # directly (test_job_worker.py already does that).
    enqueue_processing_job(job.id)

    db_session.refresh(job)
    assert job.status == JobStatus.SUCCEEDED, job.error
    assert job.output_storage_key is not None


@needs_redis
def test_enqueue_processing_job_async_leaves_job_pending(db_session, local_storage, override_settings):
    # job_queue_synchronous defaults to False — a real enqueue should just
    # push the job onto Redis and return, leaving the row untouched until
    # a worker (not running here) picks it up.
    override_settings(job_queue_synchronous=False, job_queue_name=f"test-{uuid.uuid4().hex[:8]}")

    user = User(email="queue-async-test@example.com", credit_balance=100, plan_tier=PlanTier.FREE)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    job = ProcessingJob(
        user_id=user.id, tool_name="html_to_pdf", is_async=True, credits_spent=5, options_json="{}"
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    input_key = f"inputs/{job.id}"
    local_storage.save(input_key, pickle.dumps({"raw": b"<html></html>", "extra": []}))
    job.input_storage_key = input_key
    db_session.add(job)
    db_session.commit()

    enqueue_processing_job(job.id)

    db_session.refresh(job)
    assert job.status == JobStatus.PENDING  # no worker running — nothing should have touched it

    # Clean up: drain the queue so this job doesn't sit around confusing a
    # real worker if one happens to be running against the same Redis.
    queue = get_queue()
    queue.empty()
