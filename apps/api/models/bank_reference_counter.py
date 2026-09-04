"""
app/models/bank_reference_counter.py

A single-row-per-name counter table backing services/payment_service.py's
bank-transfer reference numbers (create_bank_transfer_attempt()), read
with a row-level lock (SELECT ... FOR UPDATE) rather than a plain Postgres
SEQUENCE — this repo's migrations are kept applying cleanly against
SQLite too (see the referral/organizations migrations' docstrings for why),
and CREATE SEQUENCE has no SQLite equivalent. FOR UPDATE itself compiles
to a no-op on SQLite (nothing to lock against, since SQLite only ever has
one writer at a time), so the same calling code stays correct there
without any dialect branching.
"""
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class BankReferenceCounter(Base):
    __tablename__ = "bank_reference_counters"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<BankReferenceCounter {self.name}={self.value}>"
