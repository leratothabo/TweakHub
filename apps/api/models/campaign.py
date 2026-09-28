"""
app/models/campaign.py

A Campaign is a bulk email (name/subject/body_html) targeting one
SubscriberList; CampaignRecipient is the per-address send/track row
(the CreditTransaction-style append-only audit pattern -- one row per
recipient, never mutated except its own status/timestamp fields).

CampaignRecipientStatus already includes the post-send tracking states
(delivered/opened/clicked/bounced/unsubscribed) even though nothing
writes them yet -- services/campaign_worker.py (this pass) only ever
sets pending/sent/failed/unsubscribed. The richer states exist now so
a later Brevo-webhook pass is purely additive (new code writing to
already-existing columns), not a schema change.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    subscriber_list_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subscriber_lists.id"), index=True, nullable=False
    )
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(Enum(CampaignStatus), default=CampaignStatus.DRAFT, nullable=False, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Campaign {self.name} status={self.status}>"


class CampaignRecipientStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    FAILED = "failed"
    UNSUBSCRIBED = "unsubscribed"


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"
    __table_args__ = (
        UniqueConstraint("campaign_id", "subscriber_id", name="uq_campaign_recipients_campaign_subscriber"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id"), index=True, nullable=False)
    subscriber_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscribers.id"), index=True, nullable=False)
    status: Mapped[CampaignRecipientStatus] = mapped_column(
        Enum(CampaignRecipientStatus), default=CampaignRecipientStatus.PENDING, nullable=False, index=True
    )
    # Correlates a future Brevo webhook event back to this row (Phase 3) --
    # unused for lookups until then, but recorded on every successful send.
    brevo_message_id: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)

    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CampaignRecipient campaign={self.campaign_id} subscriber={self.subscriber_id} {self.status}>"
