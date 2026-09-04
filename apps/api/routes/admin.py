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
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import PaymentAttempt, PaymentMethod, PaymentStatus, User
from services import credit_service

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
        credit_service.grant_purchased_credits(db, user, attempt)

    return {"status": attempt.status.value, "credits_granted": True}
