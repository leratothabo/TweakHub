"""
app/routes/payments.py

DPO redirects the browser back to BASE_URL/payment-callback, and (in a
production DPO setup) also calls a server-to-server webhook. This handler
covers both: it re-verifies the token against DPO directly rather than
trusting the callback payload, then grants credits exactly once.

That re-verification is the primary defense (a forged callback with a
token an attacker doesn't own just gets told the truth by DPO, and
credits_granted makes replay a no-op), but the endpoint is still public
and every hit makes an outbound call to DPO, so two more layers sit in
front of it: an optional source-IP allowlist (DPO_WEBHOOK_IP_ALLOWLIST —
see config.py for why it defaults to disabled rather than a hardcoded
list) and a per-IP rate limit, same mechanism as the auth endpoints.
"""
from __future__ import annotations

import ipaddress
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from deps import get_client_ip, get_current_user, rate_limit
from models import PaymentAttempt, PaymentMethod, PaymentStatus, User
from services import credit_service, payment_service
from services.payment_service import PaymentServiceError

router = APIRouter(prefix="/api/payments", tags=["payments"])
logger = logging.getLogger("tweakhub.payments")


def _enforce_dpo_source_allowlist(request: Request) -> None:
    """No-op when DPO_WEBHOOK_IP_ALLOWLIST is unset (the default) — see the
    settings field's docstring for why this ships disabled rather than
    with a guessed IP list baked in. Once an operator sets it, reject
    anything outside the configured ranges before we do anything else with
    the request."""
    allowlist_raw = get_settings().dpo_webhook_ip_allowlist.strip()
    if not allowlist_raw:
        return

    try:
        networks = [ipaddress.ip_network(entry.strip(), strict=False) for entry in allowlist_raw.split(",") if entry.strip()]
        client_ip = ipaddress.ip_address(get_client_ip(request))
    except ValueError as exc:
        logger.error("Malformed DPO_WEBHOOK_IP_ALLOWLIST or client IP (%s) — rejecting", exc)
        raise HTTPException(status_code=403, detail="Source not allowed")

    if not any(client_ip in network for network in networks):
        logger.warning("Rejected DPO callback from disallowed IP %s", client_ip)
        raise HTTPException(status_code=403, detail="Source not allowed")


@router.post(
    "/callback",
    dependencies=[
        Depends(rate_limit("payments_callback", "rate_limit_payments_callback_per_hour")),
        Depends(_enforce_dpo_source_allowlist),
    ],
)
def payment_callback(transaction_token: str, db: Session = Depends(get_db)):
    attempt = (
        db.query(PaymentAttempt)
        .filter(PaymentAttempt.dpo_transaction_token == transaction_token)
        .first()
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Unknown payment attempt")

    if attempt.status == PaymentStatus.SUCCEEDED:
        return {"status": attempt.status.value, "credits_granted": attempt.credits_granted}

    try:
        verified = payment_service.verify_dpo_payment(transaction_token)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DPO verification failed: {exc}")

    if not verified:
        attempt.status = PaymentStatus.FAILED
        db.add(attempt)
        db.commit()
        return {"status": attempt.status.value, "credits_granted": False}

    attempt.status = PaymentStatus.SUCCEEDED
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    user = db.get(User, attempt.user_id)
    if user is not None and not attempt.credits_granted:
        try:
            credit_service.grant_purchased_credits(db, user, attempt)
        except ValueError:
            # Lost the race to a concurrent call for the same attempt —
            # DPO's browser-redirect callback and its server-to-server
            # webhook can both land here for the same payment at nearly
            # the same moment (see this module's docstring). The other
            # caller already granted the credits; this is a benign no-op,
            # not an error.
            pass

    return {"status": attempt.status.value, "credits_granted": True}


class PaystackInitializeRequest(BaseModel):
    # Smallest-unit amount (kobo for NGN, cents for USD/ZAR/KES/GHS...),
    # matching Paystack's own API shape -- callers are responsible for
    # converting from a decimal major-unit amount before sending this.
    amount_kobo: int
    reference: str | None = None


@router.post("/paystack/initialize")
def paystack_initialize(
    payload: PaystackInitializeRequest,
    user: User = Depends(get_current_user),
):
    """
    Standalone Paystack plumbing (services/payment_service.py's
    initialize_paystack_transaction) -- not yet wired into
    credit_service.initiate_purchase() or the PaymentMethod enum
    alongside DPO above; see payment_service.py's Paystack section for
    why. Charges the signed-in user's own account email; the browser
    should be redirected to the returned authorization_url to complete
    payment, then poll/land on paystack_verify below.
    """
    try:
        data = payment_service.initialize_paystack_transaction(
            email=user.email,
            amount_kobo=payload.amount_kobo,
            reference=payload.reference,
            callback_url=f"{get_settings().base_url}/payment-callback",
        )
    except PaymentServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return data


@router.get("/paystack/verify/{reference}")
def paystack_verify(
    reference: str,
    user: User = Depends(get_current_user),
):
    """
    Server-to-server verification (services/payment_service.py's
    verify_paystack_transaction) -- the source of truth for whether a
    Paystack payment actually succeeded. Returns Paystack's own `data`
    object as-is (status/amount/currency/...); this route does not grant
    credits or touch PaymentAttempt yet -- see the module-level note on
    paystack_initialize above.
    """
    try:
        data = payment_service.verify_paystack_transaction(reference)
    except PaymentServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return data


@router.get("/bank-transfer/{attempt_id}/invoice")
def bank_transfer_invoice(
    attempt_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """A downloadable PDF with the bank details + reference for one of the
    signed-in user's own BANK_TRANSFER attempts (services/payment_service.
    py's generate_bank_transfer_invoice_pdf) — shown by CreditPackages.tsx
    right after credit_service.initiate_purchase() books the attempt, and
    re-fetchable any time from the attempt id."""
    attempt = db.get(PaymentAttempt, attempt_id)
    if attempt is None or attempt.user_id != user.id or attempt.method != PaymentMethod.BANK_TRANSFER:
        raise HTTPException(status_code=404, detail="Unknown bank-transfer payment")

    pdf_bytes = payment_service.generate_bank_transfer_invoice_pdf(attempt, user)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{attempt.bank_reference}.pdf"'},
    )
