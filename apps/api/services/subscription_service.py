"""
app/services/subscription_service.py

Recurring monthly subscriptions, billed through Paystack's native Plan +
Subscription API rather than a hand-rolled renewal cron -- Paystack itself
retries failed renewal charges and handles dunning; this module just
reacts to the webhook events Paystack sends as a subscription's state
changes (see handle_paystack_event() below), the same "verify/webhook is
the source of truth, never trust an unconfirmed client-side signal" model
DPO's callback already follows (routes/payments.py's docstring).

DPO remains untouched and still processes every one-time credit purchase
(services/credit_service.py's CREDIT_PACKAGES / initiate_purchase()) --
this module and Paystack are unrelated to that flow.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config import get_settings
from models import PlanTier, Subscription, SubscriptionStatus, User
from .credit_service import credit_service
from .payment_service import PaymentServiceError, payment_service

logger = logging.getLogger("tweakhub.subscriptions")

# What each subscription tier costs and grants -- a monthly, recurring
# credit allowance, separate from credit_service.CREDIT_PACKAGES' one-time
# top-up packages. The "pro"/"business" key names deliberately match two
# of CREDIT_PACKAGES' keys: here they name *which PlanTier a subscription
# grants* (PlanTier.PRO / PlanTier.BUSINESS), which is exactly what a
# subscription tier is "for" -- it isn't a coincidence or a copy-paste,
# but it IS a different dict for a different purpose than
# CREDIT_PACKAGES["pro"]/["business"] (2,000/10,000 one-time credits for
# $29.99/$99.99). A future reader grepping for "pro" should check which of
# these two dicts they landed in before assuming anything about price or
# what it grants.
#
# Pricing below is a placeholder for the business owner to review before
# launch, same spirit as the legal docs' [amount] placeholders -- pick
# whatever numbers make sense once real unit economics are worked out.
SUBSCRIPTION_PLANS = {
    "pro": {"plan_tier": PlanTier.PRO, "price_usd": 19.99, "monthly_credits": 1000},
    "business": {"plan_tier": PlanTier.BUSINESS, "price_usd": 59.99, "monthly_credits": 5000},
}


class SubscriptionServiceError(Exception):
    pass


def _plan_code_for(plan_key: str) -> str:
    settings = get_settings()
    code = {
        "pro": settings.paystack_plan_code_pro,
        "business": settings.paystack_plan_code_business,
    }.get(plan_key, "")
    if not code:
        raise SubscriptionServiceError(
            f"No Paystack plan code configured for '{plan_key}' -- run "
            f"`python -m scripts.setup_paystack_plans` and set "
            f"PAYSTACK_PLAN_CODE_{plan_key.upper()} in .env"
        )
    return code


def _parse_paystack_datetime(value) -> datetime | None:
    """Paystack sends ISO-8601 timestamps (e.g. "2026-05-19T07:00:00.000Z")
    for next_payment_date and similar fields. Returns None for anything
    missing or unparseable rather than raising -- a malformed/absent date
    from Paystack shouldn't crash webhook processing, it should just leave
    current_period_end unset for this event (a later event usually fills
    it in)."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Could not parse Paystack datetime %r", value)
        return None


def _as_aware_utc(dt: datetime | None) -> datetime | None:
    """SQLite (the test suite's DB -- see tests/conftest.py) doesn't
    actually persist tzinfo through a DateTime(timezone=True) column the
    way Postgres does: a value written aware comes back naive on the next
    read. Comparing that naive value against the timezone-aware datetimes
    _parse_paystack_datetime() produces raises TypeError, so every
    Python-side comparison in this module normalizes through this first
    -- treating a naive value as already UTC, which is the only timezone
    anything in this module ever writes."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def get_subscription_for_user(db: Session, user: User) -> Subscription | None:
    return db.query(Subscription).filter(Subscription.user_id == user.id).first()


def initiate_subscription(db: Session, user: User, plan_key: str) -> tuple[Subscription, str]:
    """Start a new subscription: validate the plan, book a PENDING row,
    kick off a Paystack transaction with `plan` set so Paystack
    auto-creates the recurring Subscription once that first charge
    succeeds (see payment_service.initialize_paystack_transaction's
    docstring), and return the row plus the URL to redirect the browser
    to. No credits or plan_tier upgrade happen here -- those only happen
    once the subscription.create webhook confirms the charge actually
    went through (handle_paystack_event below)."""
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if plan is None:
        raise SubscriptionServiceError(f"Unknown subscription plan: {plan_key}")

    existing = get_subscription_for_user(db, user)
    if existing is not None and existing.status != SubscriptionStatus.CANCELLED:
        raise SubscriptionServiceError(
            f"User already has a {existing.status.value} subscription ({existing.plan_key}) -- "
            "cancel it before subscribing to a different plan (no plan-switching in this first pass)"
        )
    if existing is not None and existing.status == SubscriptionStatus.CANCELLED:
        # The one-subscription-per-user unique index (see models/
        # subscription.py's docstring) means a user can't resubscribe at
        # all once their one row is CANCELLED -- a known v1 limitation,
        # not silently worked around here. Surface it clearly rather than
        # hitting an opaque IntegrityError from the INSERT below.
        raise SubscriptionServiceError(
            "This account already has a cancelled subscription on record. Resubscribing after "
            "cancellation isn't supported yet -- contact support."
        )

    plan_code = _plan_code_for(plan_key)

    subscription = Subscription(
        user_id=user.id,
        plan_key=plan_key,
        paystack_plan_code=plan_code,
        status=SubscriptionStatus.PENDING,
    )
    db.add(subscription)
    db.flush()  # get subscription.id without committing yet, to use as the Paystack reference

    amount_kobo = round(plan["price_usd"] * 100)
    try:
        data = payment_service.initialize_paystack_transaction(
            email=user.email,
            amount_kobo=amount_kobo,
            reference=subscription.id,
            callback_url=f"{get_settings().base_url}/payment-callback",
            plan=plan_code,
        )
    except PaymentServiceError:
        db.rollback()
        raise

    db.commit()
    db.refresh(subscription)
    return subscription, data["authorization_url"]


def cancel_subscription(db: Session, user: User) -> Subscription:
    """Ask Paystack to stop future charges on the user's subscription.
    Sets cancel_at_period_end=True immediately so the UI can reflect
    "cancelling" right away, but deliberately does NOT flip `status` to
    CANCELLED here -- that only happens once Paystack's own
    subscription.disable webhook confirms it (handle_paystack_event
    below), the same "webhook/verify is the source of truth" principle
    DPO's callback already follows (see routes/payments.py's module
    docstring for why it re-verifies rather than trusting the callback
    payload directly)."""
    subscription = get_subscription_for_user(db, user)
    if subscription is None:
        raise SubscriptionServiceError("No subscription found for this user")
    if subscription.status == SubscriptionStatus.CANCELLED:
        return subscription
    if not subscription.paystack_subscription_code or not subscription.paystack_email_token:
        # Still PENDING -- the first charge never went through, so
        # Paystack never created a Subscription object to disable. Cancel
        # locally; there's nothing on Paystack's side to call.
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancel_at_period_end = True
        db.add(subscription)
        db.commit()
        db.refresh(subscription)
        return subscription

    payment_service.disable_paystack_subscription(
        subscription.paystack_subscription_code, subscription.paystack_email_token
    )

    subscription.cancel_at_period_end = True
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


# -- Webhook event handling ---------------------------------------------


def _find_subscription_for_create_event(db: Session, data: dict) -> Subscription | None:
    """subscription.create's payload doesn't always echo back the
    `reference` we passed to initialize_paystack_transaction() (that was
    the *transaction* reference; this event is about the *subscription*
    Paystack derived from it) -- so try the reference/metadata Paystack
    does provide first, and fall back to matching on the customer's email
    plus the most recent PENDING row for that user, per this module's
    task brief."""
    reference = data.get("reference") or (data.get("metadata") or {}).get("reference")
    if reference:
        row = db.get(Subscription, reference)
        if row is not None:
            return row

    customer = data.get("customer") or {}
    email = customer.get("email")
    if email:
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            return (
                db.query(Subscription)
                .filter(Subscription.user_id == user.id, Subscription.status == SubscriptionStatus.PENDING)
                .order_by(Subscription.created_at.desc())
                .first()
            )
    return None


def _handle_subscription_create(db: Session, data: dict) -> None:
    subscription_code = data.get("subscription_code")
    email_token = data.get("email_token")
    customer = data.get("customer") or {}
    customer_code = customer.get("customer_code")
    period_end = _parse_paystack_datetime(data.get("next_payment_date"))

    row = _find_subscription_for_create_event(db, data)
    if row is None:
        logger.warning(
            "subscription.create: no matching PENDING Subscription (subscription_code=%s, email=%s)",
            subscription_code, customer.get("email"),
        )
        return

    # Idempotency: atomic conditional UPDATE guarded on
    # paystack_subscription_code still being unset, mirroring
    # credit_service.grant_purchased_credits()'s guard (see that
    # method's docstring for why a plain Python check-then-act isn't
    # enough under duplicate webhook delivery). A second delivery of the
    # same event for an already-activated row is a no-op here.
    updated = (
        db.query(Subscription)
        .filter(Subscription.id == row.id, Subscription.paystack_subscription_code.is_(None))
        .update(
            {
                "paystack_subscription_code": subscription_code,
                "paystack_email_token": email_token,
                "paystack_customer_code": customer_code,
                "status": SubscriptionStatus.ACTIVE,
                "current_period_end": period_end,
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        db.rollback()
        return
    db.commit()
    db.refresh(row)

    user = db.get(User, row.user_id)
    if user is None:
        return
    plan = SUBSCRIPTION_PLANS.get(row.plan_key)
    if plan is None:
        return

    user.plan_tier = plan["plan_tier"]
    db.add(user)
    db.commit()

    if period_end is not None:
        credit_service.grant_subscription_credits(
            db, user, row, note=f"Subscription activated: {row.plan_key}"
        )


def _handle_charge_success(db: Session, data: dict) -> None:
    """A successful charge -- either the subscription's very first charge
    (whose period subscription.create already grants credits for) or a
    renewal. Only grants credits and advances current_period_end when the
    charge's own reported next_payment_date is actually later than what
    we already have on file, so this never double-grants the period
    subscription.create just handled."""
    subscription_data = data.get("subscription") or {}
    subscription_code = subscription_data.get("subscription_code") or data.get("subscription_code")
    if not subscription_code:
        return  # a one-time (non-subscription) charge -- not this module's concern

    row = db.query(Subscription).filter(Subscription.paystack_subscription_code == subscription_code).first()
    if row is None:
        return
    if row.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE):
        # Not yet activated (subscription.create hasn't landed for this
        # row yet -- webhooks aren't guaranteed to arrive in order) or
        # already cancelled. Nothing to advance.
        return

    new_period_end = _parse_paystack_datetime(
        subscription_data.get("next_payment_date") or data.get("next_payment_date")
    )
    if new_period_end is None:
        return
    if row.current_period_end is not None and _as_aware_utc(new_period_end) <= _as_aware_utc(row.current_period_end):
        # Same period we already have on file -- the initial charge.success
        # for a brand-new subscription (subscription.create already
        # recorded this same next_payment_date) or a redelivered event.
        return

    # Optimistic-concurrency guard: only advance if current_period_end is
    # still what we last read. Two concurrent deliveries of the same
    # renewal event would both read the same old value; only one wins the
    # UPDATE, so credits below are only granted by the caller that did.
    updated = (
        db.query(Subscription)
        .filter(Subscription.id == row.id, Subscription.current_period_end == row.current_period_end)
        .update(
            {"current_period_end": new_period_end, "status": SubscriptionStatus.ACTIVE},
            synchronize_session=False,
        )
    )
    if updated == 0:
        db.rollback()
        return
    db.commit()
    db.refresh(row)

    user = db.get(User, row.user_id)
    if user is None:
        return
    credit_service.grant_subscription_credits(
        db, user, row, note=f"Subscription renewal: {row.plan_key}"
    )


def _handle_invoice_payment_failed(db: Session, data: dict) -> None:
    subscription_data = data.get("subscription") or {}
    subscription_code = subscription_data.get("subscription_code") or data.get("subscription_code")
    if not subscription_code:
        return

    row = db.query(Subscription).filter(Subscription.paystack_subscription_code == subscription_code).first()
    if row is None or row.status == SubscriptionStatus.CANCELLED:
        return

    row.status = SubscriptionStatus.PAST_DUE
    db.add(row)
    db.commit()


def _handle_subscription_disable(db: Session, data: dict) -> None:
    subscription_code = data.get("subscription_code")
    if not subscription_code:
        return

    row = db.query(Subscription).filter(Subscription.paystack_subscription_code == subscription_code).first()
    if row is None:
        return

    row.status = SubscriptionStatus.CANCELLED
    row.cancel_at_period_end = True
    db.add(row)
    db.commit()


def handle_paystack_event(db: Session, event: dict) -> None:
    """Dispatch a verified Paystack webhook event (routes/payments.py's
    webhook route calls this only *after*
    payment_service.verify_paystack_webhook_signature() has passed) to
    the right handler. Every handler here is written to be safe to run
    twice -- Paystack redelivers webhooks on timeout/non-2xx, so "arrived
    once" is never a safe assumption. Unknown/irrelevant event types
    (Paystack sends many more than these) are silently ignored."""
    event_type = event.get("event")
    data = event.get("data") or {}

    if event_type == "subscription.create":
        _handle_subscription_create(db, data)
    elif event_type == "charge.success":
        _handle_charge_success(db, data)
    elif event_type == "invoice.payment_failed":
        _handle_invoice_payment_failed(db, data)
    elif event_type in ("subscription.disable", "subscription.not_renew"):
        _handle_subscription_disable(db, data)
    else:
        logger.info("Ignoring unhandled Paystack webhook event type: %s", event_type)
