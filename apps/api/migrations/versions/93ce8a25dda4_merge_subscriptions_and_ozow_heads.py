"""merge subscriptions and ozow heads

Revision ID: 93ce8a25dda4
Revises: a4bb2d2f6407, 247aef7e9ab0
Create Date: 2026-09-06 16:30:00.000000

Pure merge point -- no schema change of its own. a4bb2d2f6407 (subscriptions)
and 247aef7e9ab0 (Ozow payment method) were both authored against the same
parent (cc6affc07954) independently and ended up as two divergent heads once
merged into main, which made `alembic upgrade head` refuse to run (it won't
guess which head you meant). This file just tells Alembic the two branches
converge here so there is one linear head again; each parent migration's own
upgrade()/downgrade() already did its real schema work.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '93ce8a25dda4'
down_revision: Union[str, Sequence[str], None] = ('a4bb2d2f6407', '247aef7e9ab0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
