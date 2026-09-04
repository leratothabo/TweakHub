"""add user referral fields

Revision ID: 15ef3231e77f
Revises: 6c50b3e86c28
Create Date: 2026-08-31 18:38:36.943647

Hand-adjusted after autogenerate: the raw output used a bare
op.create_foreign_key(None, ...)/op.drop_constraint(None, ...), which
fails outright on SQLite ("No support for ALTER of constraints in SQLite
dialect... refer to the batch mode feature") and would have left an
unnamed constraint on Postgres. Wrapped in batch_alter_table with an
explicit constraint name instead, verified upgrade -> downgrade -> upgrade
against a throwaway sqlite db (same process this repo's other migrations
were checked with — see docs/TODO.md's migration-adding instructions).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15ef3231e77f'
down_revision: Union[str, None] = '6c50b3e86c28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('referral_code', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('referred_by_user_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_referral_code'), ['referral_code'], unique=True)
        batch_op.create_foreign_key(
            'fk_users_referred_by_user_id_users', 'users', ['referred_by_user_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_referred_by_user_id_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_users_referral_code'))
        batch_op.drop_column('referred_by_user_id')
        batch_op.drop_column('referral_code')
