"""
app/models/subscriber.py

A Subscriber represents one contactable email address, platform-wide —
deliberately separate from User rather than new columns on it, because a
pure newsletter signup (services/subscriber_service.py's
NEWSLETTER_FORM source) never gets a users row at all. When a User does
exist for the same email, user_id links to it (nullable + unique: at
most one Subscriber per User, but plenty of Subscribers have no User).

Suppression state (status/unsubscribed_at/bounced_at) lives here, not
per-list — see docs/tweakhub-master-plan.md-adjacent POPIA note in
services/subscriber_service.py: "never send to this address again" must
have exactly one source of truth, not one that could in principle
disagree list-by-list.
"""
import enum
import secrets
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class SubscriberSource(str, enum.Enum):
    SIGNUP = "signup"                      # auto-created at User signup, if marketing_consent was checked
    NEWSLETTER_FORM = "newsletter_form"    # public email-only opt-in (no account)
    IMPORT = "import"                      # admin bulk import
    MANUAL = "manual"                      # admin added by hand


class SubscriberStatus(str, enum.Enum):
    ACTIVE = "active"
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"


class Subscriber(Base):
    __tablename__ = "subscribers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Nullable + unique: at most one Subscriber row per User, but most
    # Subscribers (newsletter-only contacts) have none. Filled in
    # retroactively if a newsletter-only contact later creates an
    # account with the same email (services/subscriber_service.py).
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    source: Mapped[SubscriberSource] = mapped_column(Enum(SubscriberSource), nullable=False)
    status: Mapped[SubscriberStatus] = mapped_column(
        Enum(SubscriberStatus), default=SubscriberStatus.ACTIVE, nullable=False
    )

    # -- Consent (POPIA) -- opt-in only; never defaulted to true anywhere
    # in the codebase that creates a Subscriber. See
    # services/subscriber_service.py's create_or_update_subscriber().
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_source: Mapped[str] = mapped_column(String(100), nullable=True)  # e.g. "signup_checkbox"

    unsubscribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribe_reason: Mapped[str] = mapped_column(String(500), nullable=True)
    bounced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    bounce_type: Mapped[str] = mapped_column(String(20), nullable=True)  # "hard" | "soft" -- free text pending real Brevo payload shape (Phase 3)

    # The one thing a public, unauthenticated unsubscribe link can prove
    # without a login — long enough (32 random bytes, base64url) that
    # guessing another subscriber's token isn't a practical attack.
    unsubscribe_token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, default=lambda: secrets.token_urlsafe(32)
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Subscriber {self.email} status={self.status}>"
