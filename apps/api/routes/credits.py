"""
app/routes/credits.py

Credit package listing, balance lookup, and purchase initiation. Purchase
only creates a PENDING PaymentAttempt + DPO redirect URL — credits are
granted exclusively by the DPO webhook handler in routes/payments.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user
from models import PaymentMethod, User
from services import CREDIT_PACKAGES, credit_service

router = APIRouter(prefix="/api/credits", tags=["credits"])


@router.get("/packages")
def get_packages():
    return {"packages": CREDIT_PACKAGES}


@router.get("/balance")
def get_balance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # get_effective_balance() reports the org's shared pool for a member
    # of one (services/organization_service.py), the user's own balance
    # otherwise — see credit_service.py's _billing_target().
    return {"user_id": user.id, "credit_balance": credit_service.get_effective_balance(db, user)}


class PurchaseRequest(BaseModel):
    package_key: str
    method: PaymentMethod


@router.post("/purchase")
def purchase(
    payload: PurchaseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.package_key not in CREDIT_PACKAGES:
        raise HTTPException(status_code=400, detail=f"Unknown package: {payload.package_key}")

    try:
        result = credit_service.initiate_purchase(db, user, payload.package_key, payload.method)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not start payment: {exc}")

    return result
