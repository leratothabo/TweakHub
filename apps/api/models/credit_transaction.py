import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class CreditTransactionType(str, enum.Enum):
    PURCHASE = "purchase"       # credits bought via a payment
    SPEND = "spend"             # credits consumed by running a tool
    REFUND = "refund"           # credits returned (failed job, etc.)
    BONUS = "bonus"             # referral / promo credits
    ADJUSTMENT = "adjustment"   # manual admin correction


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Always the acting user — who ran the tool / triggered the change —
    # even when the balance actually debited was an organization's (see
    # organization_id below and credit_service.py's _billing_target()).
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    # Set only when this transaction was billed against a shared org pool
    # rather than the user's own credit_balance (services/
    # organization_service.py). Null for every personal-account
    # transaction — which is all of them, until an org exists.
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )
    type: Mapped[CreditTransactionType] = mapped_column(Enum(CreditTransactionType), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # positive=credit, negative=debit
    # The resulting balance of whichever account was actually debited/
    # credited — the org's credit_balance when organization_id is set,
    # otherwise the user's.
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=True)  # set for SPEND/REFUND
    payment_attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payment_attempts.id"), nullable=True
    )
    note: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CreditTransaction {self.type} {self.amount:+d} user={self.user_id}>"
