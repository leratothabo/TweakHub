"""add bank transfer support

Revision ID: cc6affc07954
Revises: 535e0588aa31
Create Date: 2026-09-01 05:37:14.429237

Hand-adjusted after autogenerate: the raw output added users.is_admin as
NOT NULL with no default, which fails on Postgres against any table that
already has rows ("column contains null values"). Added
server_default='false' so existing users backfill to non-admin; left the
server default in place afterward (rather than the usual add-then-
drop-default two-step) since "defaults to non-admin" is the permanent
desired behavior, not just a one-time backfill convenience.

bank_reference_counters (models/bank_reference_counter.py) is a plain
table, not a Postgres SEQUENCE, specifically so this migration — and
services/payment_service.py's create_bank_transfer_attempt(), which reads
it with SELECT ... FOR UPDATE — both still work against the SQLite db the
test suite runs against. Verified upgrade -> downgrade -> upgrade against
both a real Postgres db and a throwaway sqlite db.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc6affc07954'
down_revision: Union[str, None] = '535e0588aa31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bank_reference_counters',
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('name'),
    )
    op.add_column('payment_attempts', sa.Column('bank_reference', sa.String(length=32), nullable=True))
    op.create_index(op.f('ix_payment_attempts_bank_reference'), 'payment_attempts', ['bank_reference'], unique=True)
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('users', 'is_admin')
    op.drop_index(op.f('ix_payment_attempts_bank_reference'), table_name='payment_attempts')
    op.drop_column('payment_attempts', 'bank_reference')
    op.drop_table('bank_reference_counters')
