import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentMethod(str, enum.Enum):
    CARD = "card"
    MTN_MOMO = "mtn_momo"
    AIRTEL_MONEY = "airtel_money"
    ORANGE_MONEY = "orange_money"
    MPESA = "mpesa"
    WAVE = "wave"
    BANK_TRANSFER = "bank_transfer"


class PaymentAttempt(Base):
    """
    One row per payment attempt. For every method except BANK_TRANSFER
    this is a DPO payment session — created on initiation, updated by the
    DPO webhook callback (or a verify-on-return poll) once the payment
    settles. BANK_TRANSFER rows never touch DPO: they're created PENDING
    with a bank_reference and confirmed by an admin (routes/admin.py)
    once the deposit is seen on TweakHub's bank statement. Either way,
    `credits_granted` is only set after a SUCCEEDED verification/
    confirmation, never optimistically, so a crashed callback (or a
    double-click on "confirm") can't grant free credits.
    """

    __tablename__ = "payment_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    package_key: Mapped[str] = mapped_column(String(50), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    credits: Mapped[int] = mapped_column(nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    dpo_transaction_token: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    # Only set for method=BANK_TRANSFER — a direct EFT never touches DPO,
    # so it has no dpo_transaction_token. "TweakHub" + a zero-padded
    # number pulled from the bank_transfer_ref_seq Postgres sequence (see
    # the migration that adds this column), for the customer to put in
    # their transfer's own reference field so routes/admin.py's confirm
    # step — and TweakHub's own bank statement reconciliation — can match
    # a deposit back to this row.
    bank_reference: Mapped[str] = mapped_column(String(32), nullable=True, unique=True, index=True)
    credits_granted: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<PaymentAttempt {self.id} status={self.status} credits={self.credits}>"
