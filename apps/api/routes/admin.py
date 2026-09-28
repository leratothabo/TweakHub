"""
app/routes/admin.py

Minimal internal admin surface. Today it exists for exactly one job:
confirming a direct bank-transfer payment (services/payment_service.py's
create_bank_transfer_attempt()) once the deposit has actually landed in
TweakHub's Standard Bank account — a plain EFT has no webhook to tell us
that automatically, unlike the DPO-routed methods (routes/payments.py's
callback).

Gated by User.is_admin (deps.require_admin). There's no signup flow or
promotion endpoint for that flag on purpose — set it directly in the
database for whoever should have access to this.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import (
    MembershipStatus,
    PaymentAttempt,
    PaymentMethod,
    PaymentStatus,
    Subscriber,
    SubscriberList,
    SubscriberListMembership,
    SubscriberSource,
    User,
)
from services import credit_service, subscriber_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/bank-transfers/pending")
def list_pending_bank_transfers(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    attempts = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.method == PaymentMethod.BANK_TRANSFER)
        .filter(PaymentAttempt.status == PaymentStatus.PENDING)
        .order_by(PaymentAttempt.created_at.asc())
        .all()
    )
    results = []
    for attempt in attempts:
        user = db.get(User, attempt.user_id)
        results.append(
            {
                "id": attempt.id,
                "user_email": user.email if user else None,
                "package_key": attempt.package_key,
                "amount_usd": float(attempt.amount_usd),
                "credits": attempt.credits,
                "bank_reference": attempt.bank_reference,
                "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
            }
        )
    return {"pending": results}


@router.post("/bank-transfers/{attempt_id}/confirm")
def confirm_bank_transfer(
    attempt_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Marks the attempt SUCCEEDED and grants credits — idempotent, same
    "only grant once" guard as routes/payments.py's DPO callback
    (credit_service.grant_purchased_credits checks credits_granted), so a
    double-click or a retried request can't double-credit the account."""
    attempt = db.get(PaymentAttempt, attempt_id)
    if attempt is None or attempt.method != PaymentMethod.BANK_TRANSFER:
        raise HTTPException(status_code=404, detail="Unknown bank-transfer payment")

    if attempt.status == PaymentStatus.SUCCEEDED:
        return {"status": attempt.status.value, "credits_granted": attempt.credits_granted}

    attempt.status = PaymentStatus.SUCCEEDED
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    user = db.get(User, attempt.user_id)
    if user is not None and not attempt.credits_granted:
        try:
            credit_service.grant_purchased_credits(db, user, attempt)
        except ValueError:
            # Lost the race to a concurrent confirm for the same attempt
            # (a double-click, or two admins confirming at once) — the
            # other request already granted the credits; benign no-op.
            pass

    return {"status": attempt.status.value, "credits_granted": True}


# -- Subscriber lists (services/subscriber_service.py) -----------------------
# No dedicated admin UI yet (see docs/TODO.md-equivalent note in this
# session's plan) -- these are callable today via curl/Postman, wired up
# to a screen in a later pass.


class CreateSubscriberListRequest(BaseModel):
    name: str
    description: str | None = None


class AddSubscribersRequest(BaseModel):
    emails: list[str]


@router.get("/subscriber-lists")
def list_subscriber_lists(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    lists = db.query(SubscriberList).order_by(SubscriberList.created_at.asc()).all()
    return {
        "lists": [
            {
                "id": lst.id,
                "name": lst.name,
                "description": lst.description,
                "is_default": lst.is_default,
                "member_count": (
                    db.query(SubscriberListMembership)
                    .filter(
                        SubscriberListMembership.subscriber_list_id == lst.id,
                        SubscriberListMembership.status == MembershipStatus.ACTIVE,
                    )
                    .count()
                ),
            }
            for lst in lists
        ]
    }


@router.post("/subscriber-lists", status_code=201)
def create_subscriber_list(
    payload: CreateSubscriberListRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subscriber_list = SubscriberList(name=payload.name, description=payload.description)
    db.add(subscriber_list)
    db.commit()
    db.refresh(subscriber_list)
    return {"id": subscriber_list.id, "name": subscriber_list.name}


@router.get("/subscriber-lists/{list_id}/subscribers")
def list_subscribers_in_list(
    list_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subscriber_list = db.get(SubscriberList, list_id)
    if subscriber_list is None:
        raise HTTPException(status_code=404, detail="Unknown subscriber list")

    memberships = (
        db.query(SubscriberListMembership)
        .filter(
            SubscriberListMembership.subscriber_list_id == list_id,
            SubscriberListMembership.status == MembershipStatus.ACTIVE,
        )
        .all()
    )
    subscribers = []
    for membership in memberships:
        subscriber = db.get(Subscriber, membership.subscriber_id)
        if subscriber is None:
            continue
        subscribers.append(
            {
                "id": subscriber.id,
                "email": subscriber.email,
                "full_name": subscriber.full_name,
                "status": subscriber.status.value,
                "source": subscriber.source.value,
                "marketing_consent": subscriber.marketing_consent,
            }
        )
    return {"subscribers": subscribers}


@router.post("/subscriber-lists/{list_id}/subscribers", status_code=201)
def add_subscribers_to_list(
    list_id: str,
    payload: AddSubscribersRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Manual/bulk add by email (one-per-line on the frontend, once that
    screen exists) -- admin-added contacts are consented by construction
    (an admin adding a known contact to a list is the consent_source),
    same trust level as source=MANUAL/IMPORT elsewhere in this module's
    design."""
    subscriber_list = db.get(SubscriberList, list_id)
    if subscriber_list is None:
        raise HTTPException(status_code=404, detail="Unknown subscriber list")

    added = 0
    for email in payload.emails:
        email = email.strip()
        if not email:
            continue
        subscriber = subscriber_service.create_or_update_subscriber(
            db, email, source=SubscriberSource.MANUAL, marketing_consent=True,
            consent_source="admin_manual_add",
        )
        subscriber_service.add_to_list(db, subscriber_list, subscriber)
        added += 1
    return {"added": added}


@router.delete("/subscriber-lists/{list_id}/subscribers/{subscriber_id}")
def remove_subscriber_from_list(
    list_id: str,
    subscriber_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subscriber_list = db.get(SubscriberList, list_id)
    subscriber = db.get(Subscriber, subscriber_id)
    if subscriber_list is None or subscriber is None:
        raise HTTPException(status_code=404, detail="Unknown list or subscriber")
    subscriber_service.remove_from_list(db, subscriber_list, subscriber)
    return {"message": "Removed from list"}
