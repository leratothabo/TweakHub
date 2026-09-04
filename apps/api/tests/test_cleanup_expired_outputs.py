"""
Tests for scripts/cleanup_expired_outputs.py — the retention-policy
enforcement that neither storage backend provides on its own (see that
file's docstring).
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import JobStatus, PlanTier, ProcessingJob, User  # noqa: E402
from scripts.cleanup_expired_outputs import cleanup_expired_outputs  # noqa: E402


def _make_user(db_session) -> User:
    user = User(email="cleanup-test@example.com", credit_balance=100, plan_tier=PlanTier.FREE)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_succeeded_job(db_session, local_storage, user, *, expires_delta: timedelta, has_output=True) -> ProcessingJob:
    job = ProcessingJob(
        user_id=user.id,
        tool_name="image_convert",
        status=JobStatus.SUCCEEDED,
        credits_spent=5,
        finished_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + expires_delta,
    )
    if has_output:
        key = f"outputs/{uuid.uuid4()}.bin"
        local_storage.save(key, b"fake output bytes")
        job.output_storage_key = key
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_cleanup_deletes_expired_outputs_and_clears_key(db_session, local_storage):
    user = _make_user(db_session)
    expired = _make_succeeded_job(db_session, local_storage, user, expires_delta=timedelta(hours=-1))

    cleaned = cleanup_expired_outputs()

    assert cleaned == 1
    db_session.refresh(expired)
    assert expired.output_storage_key is None
    assert expired.status == JobStatus.SUCCEEDED  # row kept for history


def test_cleanup_leaves_unexpired_outputs_alone(db_session, local_storage):
    user = _make_user(db_session)
    still_valid = _make_succeeded_job(db_session, local_storage, user, expires_delta=timedelta(hours=47))

    cleaned = cleanup_expired_outputs()

    assert cleaned == 0
    db_session.refresh(still_valid)
    assert still_valid.output_storage_key is not None
    assert local_storage.exists(still_valid.output_storage_key) is True


def test_cleanup_is_idempotent_when_storage_object_already_gone(db_session, local_storage):
    user = _make_user(db_session)
    job = _make_succeeded_job(db_session, local_storage, user, expires_delta=timedelta(hours=-1))
    local_storage.delete(job.output_storage_key)  # simulate an out-of-band deletion

    cleaned = cleanup_expired_outputs()  # must not raise

    assert cleaned == 1
    db_session.refresh(job)
    assert job.output_storage_key is None


def test_cleanup_ignores_jobs_without_expires_at(db_session, local_storage):
    user = _make_user(db_session)
    # A job that's SUCCEEDED but has no expires_at (shouldn't normally
    # happen post-this-phase, but a pre-migration row could look like
    # this) must not be treated as "already expired".
    job = ProcessingJob(
        user_id=user.id,
        tool_name="image_convert",
        status=JobStatus.SUCCEEDED,
        credits_spent=5,
        output_storage_key="outputs/no-expiry.bin",
    )
    local_storage.save("outputs/no-expiry.bin", b"data")
    db_session.add(job)
    db_session.commit()

    cleaned = cleanup_expired_outputs()

    assert cleaned == 0
