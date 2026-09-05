"""
Tests for services/job_worker.py's run_processing_job() — the function an
rq worker calls (see apps/workers/README.md). Exercised directly, without
Redis or RQ in the loop: it only needs a DB session and object storage,
both of which db_session/local_storage already provide as throwaway
fixtures. test_job_queue.py separately verifies the RQ/Redis plumbing
that gets a job_id to this function for real.
"""
import json
import os
import pickle
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import JobStatus, PlanTier, ProcessingJob, User  # noqa: E402
from services.job_worker import run_processing_job  # noqa: E402


def _make_user(db_session, credit_balance=100) -> User:
    user = User(email="worker-test@example.com", credit_balance=credit_balance, plan_tier=PlanTier.FREE)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_async_job(db_session, local_storage, user, tool_name, raw: bytes, extra: list[bytes] | None = None, options=None):
    # Mirrors routes/tools.py's real order: spend credits first (so a
    # refund-on-failure test is checking a real deduction, not just
    # exercising the refund arithmetic against a balance that was never
    # actually reduced), then create the job row.
    from services import credit_service

    tx = credit_service.spend_credits(db_session, user, tool_name, file_size_mb=0.01)

    job = ProcessingJob(
        user_id=user.id,
        tool_name=tool_name,
        is_async=True,
        credit_transaction_id=tx.id,
        credits_spent=-tx.amount,
        options_json=json.dumps(options or {}),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    input_key = f"inputs/{job.id}"
    local_storage.save(input_key, pickle.dumps({"raw": raw, "extra": extra or []}))
    job.input_storage_key = input_key
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_run_processing_job_succeeds_and_stores_output(db_session, local_storage, sample_pdf_bytes):
    user = _make_user(db_session)
    # word_to_pdf isn't the right direction for a PDF input, but
    # html_to_pdf is a real async tool (document engine) that's fast and
    # deterministic — use that instead with a tiny HTML payload.
    job = _make_async_job(
        db_session, local_storage, user, "html_to_pdf", b"<html><body><h1>Hi</h1></body></html>"
    )

    run_processing_job(job.id)

    db_session.refresh(job)
    assert job.status == JobStatus.SUCCEEDED
    assert job.output_storage_key is not None
    assert job.content_type == "application/pdf"
    assert job.filename == "html_to_pdf.pdf"
    assert job.finished_at is not None
    assert job.expires_at is not None

    output_bytes = local_storage.load(job.output_storage_key)
    assert output_bytes.startswith(b"%PDF")

    # Input is cleaned up after processing, successful or not.
    assert local_storage.exists(job.input_storage_key) is False


def test_run_processing_job_engine_failure_refunds_credits_and_records_error(db_session, local_storage):
    """A TweakHub-side failure (here: epub_to_pdf, a documented stub — see
    document_convert.py — that always fails with EngineResult.refundable
    defaulting True) still refunds the credits it spent."""
    user = _make_user(db_session, credit_balance=100)
    balance_before = user.credit_balance

    job = _make_async_job(db_session, local_storage, user, "epub_to_pdf", b"not a real epub, doesn't matter")
    assert user.credit_balance < balance_before  # sanity: spend_credits actually deducted

    run_processing_job(job.id)

    db_session.refresh(job)
    db_session.refresh(user)
    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert "not refunded" not in job.error
    assert user.credit_balance == balance_before  # refunded back to where it started
    assert local_storage.exists(job.input_storage_key) is False


def test_run_processing_job_input_error_does_not_refund_credits(db_session, local_storage):
    """A failure caused by the uploaded file itself, not by TweakHub, must
    not be refunded — see EngineResult.refundable and document_convert.py's
    _pdf_to_word. LibreOffice's docx import is surprisingly tolerant of
    garbage bytes (it'll happily render them as plain text), but its PDF
    import filter reliably rejects anything that isn't a real PDF — a
    clean way to force a genuine (non-refundable) input error here."""
    user = _make_user(db_session, credit_balance=100)
    balance_before = user.credit_balance

    job = _make_async_job(db_session, local_storage, user, "pdf_to_word", b"not a real pdf file at all")
    assert user.credit_balance < balance_before  # sanity: spend_credits actually deducted

    run_processing_job(job.id)

    db_session.refresh(job)
    db_session.refresh(user)
    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert "not refunded" in job.error
    assert user.credit_balance < balance_before  # NOT refunded — this was the user's bad input
    assert local_storage.exists(job.input_storage_key) is False


def test_run_processing_job_missing_input_object_fails_cleanly(db_session, local_storage):
    user = _make_user(db_session)
    job = ProcessingJob(
        user_id=user.id,
        tool_name="html_to_pdf",
        is_async=True,
        credits_spent=5,
        input_storage_key="inputs/never-saved",
        options_json="{}",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    run_processing_job(job.id)

    db_session.refresh(job)
    assert job.status == JobStatus.FAILED
    assert "Could not load input" in job.error


def test_run_processing_job_unknown_job_id_is_a_noop(db_session, local_storage):
    # Should not raise even though nothing exists for this id — e.g. a
    # worker picking up a job whose row was somehow never committed.
    run_processing_job("00000000-0000-0000-0000-000000000000")


def test_run_processing_job_passes_extra_files_through(db_session, local_storage):
    """subtitle_burn (video category -> async) needs a video as the
    primary input and an .srt as extra_files[0] — this only succeeds if
    the worker actually unpickled the bundle's "extra" list and threaded
    it into options["extra_files"] for the engine, same as the sync path
    in routes/tools.py does inline."""
    from services.engines._util import run, scratch_dir

    with scratch_dir() as d:
        clip_path = d / "clip.mp4"
        run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:v", "libx264", "-c:a", "aac", "-shortest", str(clip_path),
            ]
        )
        video_bytes = clip_path.read_bytes()

    srt_bytes = b"1\n00:00:00,000 --> 00:00:01,000\nHello TweakHub\n"

    user = _make_user(db_session)
    job = _make_async_job(
        db_session, local_storage, user, "subtitle_burn", video_bytes, extra=[srt_bytes]
    )

    run_processing_job(job.id)

    db_session.refresh(job)
    assert job.status == JobStatus.SUCCEEDED, job.error
    assert job.output_storage_key is not None
    output_bytes = local_storage.load(job.output_storage_key)
    assert len(output_bytes) > 0
