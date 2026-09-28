"""
app/services/subscriber_service.py

The single place that creates/updates Subscriber rows and manages list
membership -- routes/subscribers.py (public newsletter signup +
unsubscribe), services/auth_service.py (signup consent capture), and
services/oauth_service.py (Google signup) all go through this module
rather than touching Subscriber/SubscriberList directly, so "who is
this platform allowed to email" always goes through the same rules.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import (
    Campaign,
    MembershipStatus,
    Subscriber,
    SubscriberList,
    SubscriberListMembership,
    SubscriberSource,
    SubscriberStatus,
)

DEFAULT_LIST_NAME = "All Subscribers"


def create_or_update_subscriber(
    db: Session,
    email: str,
    *,
    user_id: str | None = None,
    full_name: str | None = None,
    source: SubscriberSource,
    marketing_consent: bool,
    consent_source: str,
) -> Subscriber:
    """Get-or-create by email. If a newsletter-only contact later signs
    up for a real account, this links user_id onto their existing row
    rather than creating a second one.

    Deliberately does NOT clear an existing UNSUBSCRIBED status just
    because a new consent event comes in (e.g. someone who unsubscribed
    as a newsletter-only contact, then later creates an account with the
    same email) -- an implicit re-subscribe on signup would undercut the
    point of letting them unsubscribe in the first place. Re-consent
    after an explicit unsubscribe is a deliberately separate, explicit
    action this module doesn't perform on its own.
    """
    subscriber = db.query(Subscriber).filter(Subscriber.email == email).first()
    now = datetime.now(timezone.utc)

    if subscriber is None:
        subscriber = Subscriber(
            email=email,
            user_id=user_id,
            full_name=full_name,
            source=source,
            marketing_consent=marketing_consent,
            consent_given_at=now if marketing_consent else None,
            consent_source=consent_source if marketing_consent else None,
        )
        db.add(subscriber)
        db.commit()
        db.refresh(subscriber)
        return subscriber

    changed = False
    if user_id and not subscriber.user_id:
        subscriber.user_id = user_id
        changed = True
    if full_name and not subscriber.full_name:
        subscriber.full_name = full_name
        changed = True
    # Recording a *new* consent event only strengthens consent (false ->
    # true); it never flips true -> false -- withdrawing consent goes
    # through unsubscribe_globally(), a distinct, explicit action.
    if marketing_consent and not subscriber.marketing_consent and subscriber.status != SubscriberStatus.UNSUBSCRIBED:
        subscriber.marketing_consent = True
        subscriber.consent_given_at = now
        subscriber.consent_source = consent_source
        changed = True

    if changed:
        db.add(subscriber)
        db.commit()
        db.refresh(subscriber)
    return subscriber


def get_or_create_default_list(db: Session) -> SubscriberList:
    existing = db.query(SubscriberList).filter(SubscriberList.is_default.is_(True)).first()
    if existing is not None:
        return existing
    default_list = SubscriberList(name=DEFAULT_LIST_NAME, is_default=True)
    db.add(default_list)
    db.commit()
    db.refresh(default_list)
    return default_list


def add_to_list(db: Session, subscriber_list: SubscriberList, subscriber: Subscriber) -> SubscriberListMembership:
    """Idempotent: re-adding an already-active member is a no-op, and a
    previously-removed member is re-activated rather than getting a
    second membership row (the unique(list, subscriber) constraint would
    reject that anyway)."""
    membership = (
        db.query(SubscriberListMembership)
        .filter(
            SubscriberListMembership.subscriber_list_id == subscriber_list.id,
            SubscriberListMembership.subscriber_id == subscriber.id,
        )
        .first()
    )
    if membership is None:
        membership = SubscriberListMembership(subscriber_list_id=subscriber_list.id, subscriber_id=subscriber.id)
        db.add(membership)
        db.commit()
        db.refresh(membership)
        return membership

    if membership.status != MembershipStatus.ACTIVE:
        membership.status = MembershipStatus.ACTIVE
        membership.removed_at = None
        db.add(membership)
        db.commit()
        db.refresh(membership)
    return membership


def remove_from_list(db: Session, subscriber_list: SubscriberList, subscriber: Subscriber) -> None:
    membership = (
        db.query(SubscriberListMembership)
        .filter(
            SubscriberListMembership.subscriber_list_id == subscriber_list.id,
            SubscriberListMembership.subscriber_id == subscriber.id,
        )
        .first()
    )
    if membership is None or membership.status == MembershipStatus.REMOVED:
        return
    membership.status = MembershipStatus.REMOVED
    membership.removed_at = datetime.now(timezone.utc)
    db.add(membership)
    db.commit()


def unsubscribe_globally(db: Session, subscriber: Subscriber, reason: str | None = None) -> Subscriber:
    """Idempotent -- an already-unsubscribed token still "succeeds"
    (routes/subscribers.py relies on this: a double-click on an
    unsubscribe link, or a redelivered webhook event later, must never
    error)."""
    if subscriber.status == SubscriberStatus.UNSUBSCRIBED:
        return subscriber
    subscriber.status = SubscriberStatus.UNSUBSCRIBED
    subscriber.unsubscribed_at = datetime.now(timezone.utc)
    if reason:
        subscriber.unsubscribe_reason = reason
    db.add(subscriber)
    db.commit()
    db.refresh(subscriber)
    return subscriber


def mark_bounced(db: Session, subscriber: Subscriber, bounce_type: str) -> Subscriber:
    """Unused until Phase 3's Brevo webhook lands -- kept here now so
    that pass is purely wiring, not a new suppression rule."""
    subscriber.status = SubscriberStatus.BOUNCED
    subscriber.bounced_at = datetime.now(timezone.utc)
    subscriber.bounce_type = bounce_type
    db.add(subscriber)
    db.commit()
    db.refresh(subscriber)
    return subscriber


def eligible_recipients_for_campaign(db: Session, campaign: Campaign) -> list[Subscriber]:
    """The one choke point for "who can this campaign actually be sent
    to": active membership in the campaign's target list, joined to an
    active (not unsubscribed/bounced) Subscriber. Used both when
    routes/campaigns.py's send endpoint builds CampaignRecipient rows and
    conceptually re-checked (see services/campaign_worker.py) per
    recipient at send time, since a campaign can run for minutes across
    thousands of rows and a subscriber could unsubscribe mid-batch."""
    return (
        db.query(Subscriber)
        .join(SubscriberListMembership, SubscriberListMembership.subscriber_id == Subscriber.id)
        .filter(
            SubscriberListMembership.subscriber_list_id == campaign.subscriber_list_id,
            SubscriberListMembership.status == MembershipStatus.ACTIVE,
            Subscriber.status == SubscriberStatus.ACTIVE,
        )
        .all()
    )
