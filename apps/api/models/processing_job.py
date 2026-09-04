import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProcessingJob(Base):
    """
    One row per call to /api/tools/{tool_name}/process, whether it ran
    inline in the request (is_async=False — most tools) or was handed to
    the RQ worker (is_async=True — video-category and document-engine
    tools; see routes/tools.py's ASYNC_TOOL_NAMES). Sync and async share
    this one table and one status machine (PENDING -> PROCESSING ->
    SUCCEEDED|FAILED) rather than the async path getting its own model,
    so GET /api/jobs/{id} and GET /api/jobs work the same way for
    everything a user has ever run.

    input_storage_key is only ever set for async jobs (the worker runs in
    a separate process and needs somewhere to read the upload from) and
    is deleted once the job finishes, successfully or not — it's not part
    of what gets kept for the retention window. output_storage_key is
    what scripts/cleanup_expired_outputs.py deletes once expires_at
    passes.
    """

    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    is_async: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    input_storage_key: Mapped[str] = mapped_column(String(500), nullable=True)
    options_json: Mapped[str] = mapped_column(Text, nullable=True)

    output_storage_key: Mapped[str] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=True)
    meta_json: Mapped[str] = mapped_column(Text, nullable=True)

    error: Mapped[str] = mapped_column(Text, nullable=True)

    credit_transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("credit_transactions.id"), nullable=True
    )
    credits_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<ProcessingJob {self.id} tool={self.tool_name} status={self.status}>"
