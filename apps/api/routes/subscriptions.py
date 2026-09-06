"""
app/routes/subscriptions.py

Recurring monthly subscriptions (services/subscription_service.py),
billed through Paystack. Separate router from routes/credits.py (which
still only ever deals with DPO one-time credit purchases) and from
routes/payments.py (which owns the actual Paystack webhook -- see that
module for the POST /api/payments/paystack/webhook route this feature's
state changes actually flow through).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user
from models import User
from services import subscription_service
from services.payment_service import PaymentServiceError
from services.subscription_service import SUBSCRIPTION_PLANS, SubscriptionServiceError

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


@router.get("/plans")
def get_plans():
    return {"plans": SUBSCRIPTION_PLANS}


def _serialize(subscription) -> dict:
    return {
        "id": subscription.id,
        "plan_key": subscription.plan_key,
        "status": subscription.status.value,
        "current_period_end": subscription.current_period_end,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "created_at": subscription.created_at,
    }


@router.get("/me")
def get_my_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subscription = subscription_service.get_subscription_for_user(db, user)
    return _serialize(subscription) if subscription is not None else None


class SubscribeRequest(BaseModel):
    plan_key: str


@router.post("/subscribe")
def subscribe(
    payload: SubscribeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        subscription, authorization_url = subscription_service.initiate_subscription(db, user, payload.plan_key)
    except SubscriptionServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PaymentServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"subscription_id": subscription.id, "authorization_url": authorization_url}


@router.post("/cancel")
def cancel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        subscription = subscription_service.cancel_subscription(db, user)
    except SubscriptionServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PaymentServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return _serialize(subscription)
