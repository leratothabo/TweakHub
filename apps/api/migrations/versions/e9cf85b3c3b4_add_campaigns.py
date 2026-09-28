"""add campaigns and campaign recipients

Revision ID: e9cf85b3c3b4
Revises: 38fe9250720d
Create Date: 2026-09-27 18:15:00.000000

Pure op.create_table for two new tables (campaigns, campaign_recipients)
-- no ALTER on any existing table. Hand-written (no local Postgres/full
Python toolchain available in this pass) against models/campaign.py.
Verified upgrade -> downgrade -> upgrade against a throwaway SQLite db.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9cf85b3c3b4'
down_revision: Union[str, None] = '38fe9250720d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'campaigns',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('subscriber_list_id', sa.String(length=36), nullable=False),
        sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.Enum('DRAFT', 'QUEUED', 'SENDING', 'SENT', 'FAILED', name='campaignstatus'), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['subscriber_list_id'], ['subscriber_lists.id'], name='fk_campaigns_subscriber_list_id_subscriber_lists'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_campaigns_created_by_user_id_users'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_campaigns_subscriber_list_id'), 'campaigns', ['subscriber_list_id'], unique=False)
    op.create_index(op.f('ix_campaigns_created_by_user_id'), 'campaigns', ['created_by_user_id'], unique=False)
    op.create_index(op.f('ix_campaigns_status'), 'campaigns', ['status'], unique=False)

    op.create_table(
        'campaign_recipients',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('subscriber_id', sa.String(length=36), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'SENT', 'DELIVERED', 'OPENED', 'CLICKED', 'BOUNCED', 'FAILED', 'UNSUBSCRIBED', name='campaignrecipientstatus'),
            nullable=False,
        ),
        sa.Column('brevo_message_id', sa.String(length=255), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('clicked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('bounced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unsubscribed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], name='fk_campaign_recipients_campaign_id_campaigns'),
        sa.ForeignKeyConstraint(['subscriber_id'], ['subscribers.id'], name='fk_campaign_recipients_subscriber_id_subscribers'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'subscriber_id', name='uq_campaign_recipients_campaign_subscriber'),
    )
    op.create_index(op.f('ix_campaign_recipients_campaign_id'), 'campaign_recipients', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_campaign_recipients_subscriber_id'), 'campaign_recipients', ['subscriber_id'], unique=False)
    op.create_index(op.f('ix_campaign_recipients_status'), 'campaign_recipients', ['status'], unique=False)
    op.create_index(op.f('ix_campaign_recipients_brevo_message_id'), 'campaign_recipients', ['brevo_message_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_campaign_recipients_brevo_message_id'), table_name='campaign_recipients')
    op.drop_index(op.f('ix_campaign_recipients_status'), table_name='campaign_recipients')
    op.drop_index(op.f('ix_campaign_recipients_subscriber_id'), table_name='campaign_recipients')
    op.drop_index(op.f('ix_campaign_recipients_campaign_id'), table_name='campaign_recipients')
    op.drop_table('campaign_recipients')

    op.drop_index(op.f('ix_campaigns_status'), table_name='campaigns')
    op.drop_index(op.f('ix_campaigns_created_by_user_id'), table_name='campaigns')
    op.drop_index(op.f('ix_campaigns_subscriber_list_id'), table_name='campaigns')
    op.drop_table('campaigns')
