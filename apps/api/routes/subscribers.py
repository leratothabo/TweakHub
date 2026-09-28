"""
app/routes/subscribers.py

Public endpoints only: newsletter opt-in (no account required) and
unsubscribe. Admin-facing subscriber-list management lives in
routes/admin.py instead, gated by require_admin.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from db import get_db
from deps import rate_limit
from models import Subscriber, SubscriberSource
from services import subscriber_service

router = APIRouter(prefix="/api/subscribers", tags=["subscribers"])


class NewsletterSignupRequest(BaseModel):
    email: EmailStr
    consent: bool


class UnsubscribeRequest(BaseModel):
    token: str


@router.post(
    "/newsletter-signup",
    status_code=201,
    dependencies=[Depends(rate_limit("newsletter_signup", "rate_limit_newsletter_signup_per_hour"))],
)
def newsletter_signup(payload: NewsletterSignupRequest, db: Session = Depends(get_db)):
    # The one thing the server can actually enforce -- it can't verify the
    # frontend really rendered an unchecked box, but it can refuse to
    # create any list membership without an explicit true here.
    if not payload.consent:
        raise HTTPException(status_code=400, detail="Marketing consent is required to subscribe.")

    subscriber = subscriber_service.create_or_update_subscriber(
        db, payload.email, source=SubscriberSource.NEWSLETTER_FORM,
        marketing_consent=True, consent_source="newsletter_form",
    )
    default_list = subscriber_service.get_or_create_default_list(db)
    subscriber_service.add_to_list(db, default_list, subscriber)
    return {"message": "Subscribed. You can unsubscribe at any time from any email we send."}


@router.post("/unsubscribe")
def unsubscribe(payload: UnsubscribeRequest, db: Session = Depends(get_db)):
    """Idempotent by design -- an already-unsubscribed or unknown token
    both return success rather than a 404, so this can't be used to probe
    which tokens are valid, and a double-click never errors."""
    subscriber = db.query(Subscriber).filter(Subscriber.unsubscribe_token == payload.token).first()
    if subscriber is None:
        return {"message": "You are unsubscribed."}

    subscriber_service.unsubscribe_globally(db, subscriber, reason="unsubscribe_link")
    return {"message": "You are unsubscribed."}
