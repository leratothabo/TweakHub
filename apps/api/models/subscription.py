"""
app/models/subscription.py

Recurring monthly subscriptions billed through Paystack's native Plan +
Subscription API (services/subscription_service.py, scripts/
setup_paystack_plans.py) -- Paystack itself handles the actual recurring
charge, retries, and dunning; this table just mirrors the state of one
subscription per user so the app can answer "what plan is this user on"
and "when does it renew" without calling out to Paystack on every request.

Known limitation (v1, matching the callouts in models/organization.py and
docs/TODO.md for similar simplifications elsewhere in this codebase): a
user has at most one subscription, enforced with a unique index on
user_id the same way 2a4f2a066ede's migration enforced one joined
Organization per user. There is no plan-switching or proration in this
first pass -- upgrading/downgrading means cancelling the existing
subscription (which stays CANCELLED, not deleted, once Paystack confirms
via subscription.disable/subscription.not_renew) and starting a new one
once the unique index no longer blocks it. A v2 that wants live
plan-switching would need to either lift the one-row-per-user constraint
into "at most one *non-cancelled* subscription" (a partial unique index,
same technique as organization_members' uq_org_members_one_org_per_user)
or add real proration logic against Paystack's /subscription API.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class SubscriptionStatus(str, enum.Enum):
    PENDING = "pending"      # created, waiting for the first Paystack charge to succeed
    ACTIVE = "active"        # subscription.create webhook confirmed it; user.plan_tier upgraded
    PAST_DUE = "past_due"    # invoice.payment_failed -- a renewal charge failed
    CANCELLED = "cancelled"  # subscription.disable / subscription.not_renew confirmed it


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Unique, not just indexed -- enforces "at most one subscription per
    # user" (see this module's docstring) at the database level, the same
    # defense-in-depth reason organization_members.
    # uq_org_members_one_org_per_user exists: subscription_service.
    # initiate_subscription()'s own check-then-act guard against a second
    # PENDING/ACTIVE row is a plain SELECT-then-INSERT, which two
    # concurrent "Subscribe" clicks could both slip past before either
    # commits. Unlike the org case this is a plain (non-partial) unique
    # index, since a user is allowed at most one row ever, cancelled or
    # not -- resubscribing after a CANCELLED row is a v2 gap noted above,
    # not something this first pass supports.
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True, nullable=False)
    # Key into subscription_service.SUBSCRIPTION_PLANS ("pro"/"business")
    # -- deliberately the same key names as credit_service.CREDIT_PACKAGES'
    # unrelated one-time-purchase dict; see SUBSCRIPTION_PLANS' own
    # docstring for why that overlap is intentional rather than confusing.
    plan_key: Mapped[str] = mapped_column(String(50), nullable=False)
    paystack_plan_code: Mapped[str] = mapped_column(String(50), nullable=False)
    # Filled in once Paystack's subscription.create webhook arrives --
    # null on the PENDING row created at initiate_subscription() time.
    paystack_subscription_code: Mapped[str] = mapped_column(String(50), nullable=True, index=True)
    # Needed alongside paystack_subscription_code to call
    # disable_paystack_subscription() -- Paystack requires both together.
    paystack_email_token: Mapped[str] = mapped_column(String(255), nullable=True)
    paystack_customer_code: Mapped[str] = mapped_column(String(50), nullable=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING, nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set immediately (optimistically) by cancel_subscription() so the UI
    # can show "cancelling" right away; `status` itself only flips to
    # CANCELLED once Paystack's own webhook confirms it -- see
    # subscription_service.cancel_subscription()'s docstring.
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # The current_period_end value monthly credits were most recently
    # granted for -- kept separate from current_period_end itself (which
    # just mirrors Paystack's next_payment_date for display) so
    # credit_service.grant_subscription_credits() has a dedicated
    # idempotency marker to guard on. Both subscription.create (the first
    # period) and charge.success (every renewal) can be delivered more
    # than once by Paystack; comparing this against the period end being
    # granted for is what lets grant_subscription_credits() tell "a new
    # period actually started" apart from "the same webhook fired twice"
    # -- mirrors credit_service.grant_purchased_credits()'s
    # credits_granted guard, just keyed by period instead of by a
    # one-shot attempt id.
    credits_granted_through: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Subscription {self.plan_key} user={self.user_id} status={self.status}>"
