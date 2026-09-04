"""add ozow payment method

Revision ID: 247aef7e9ab0
Revises: cc6affc07954
Create Date: 2026-09-01 18:40:00.000000

Adds OZOW to the payment_method enum's member set and an
ozow_transaction_id column on payment_attempts (parallel to the existing
dpo_transaction_token — Ozow's own paymentRequestId for an attempt, kept
for audit/debugging; the notify webhook actually looks the row up by
TransactionReference, which is attempt.id, same as the DPO flow uses
CompanyRef).

Postgres stores this native enum by member NAME, not by the lowercase
`.value` the API/JSON layer uses — the existing rows in this same column
are 'CARD', 'BANK_TRANSFER', etc. (see 9e1ac24415a7_initial_schema.py),
so the new label added here is 'OZOW', matching PaymentMethod.OZOW.name.

The ALTER TYPE statement only runs against Postgres (guarded below): the
test suite builds its SQLite schema fresh from the current models via
Base.metadata.create_all() rather than replaying migrations (see
tests/conftest.py), so SQLite never executes this file and needs no
equivalent statement. A real Postgres deploy does go through it via
`alembic upgrade head`, and ADD VALUE is safe inside Alembic's normal
transactional migration on Postgres 12+ (this project's stated minimum,
RUNNING_LOCALLY.md, is 14+) — the pre-12 "can't run in a transaction
block" restriction doesn't apply here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '247aef7e9ab0'
down_revision: Union[str, None] = 'cc6affc07954'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'OZOW'")
    op.add_column('payment_attempts', sa.Column('ozow_transaction_id', sa.String(length=255), nullable=True))
    op.create_index(
        op.f('ix_payment_attempts_ozow_transaction_id'),
        'payment_attempts',
        ['ozow_transaction_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_payment_attempts_ozow_transaction_id'), table_name='payment_attempts')
    op.drop_column('payment_attempts', 'ozow_transaction_id')
    # Postgres has no "ALTER TYPE ... DROP VALUE" — removing an enum
    # label means rebuilding the type and remapping every row, which is
    # out of proportion for a rollback path. Any existing 'OZOW' rows
    # would need to be moved to another method by hand first; documented
    # here rather than silently omitted.
