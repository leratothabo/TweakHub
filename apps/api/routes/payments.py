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
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from deps import get_client_ip, get_current_user, rate_limit
from models import PaymentAttempt, PaymentMethod, PaymentStatus, User
from services import credit_service, ozow_service, payment_service

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
        credit_service.grant_purchased_credits(db, user, attempt)

    return {"status": attempt.status.value, "credits_granted": True}


@router.post(
    "/ozow/notify",
    dependencies=[Depends(rate_limit("payments_callback", "rate_limit_payments_callback_per_hour"))],
)
async def ozow_notify(request: Request, db: Session = Depends(get_db)):
    """
    Ozow's notify webhook (services/ozow_service.py's NotifyUrl). Ozow
    POSTs form-encoded fields, not JSON — read via request.form() rather
    than assuming a Pydantic body model the way most other routes here
    do.

    Trust model, deliberately different from the DPO callback above: a
    verified HashCheck is itself a signature only someone holding
    OZOW_PRIVATE_KEY could produce, so (unlike DPO, whose callback this
    codebase never trusts on its own) a *matching* hash is credited
    directly with no extra round trip. A *mismatched* hash is NOT treated
    as proof of a forged callback, though — see verify_notify_hash's
    docstring for why the notify hash's exact field set is a genuine open
    question, not a confirmed one the way the request-side hash is — so a
    mismatch here just logs loudly and leaves the row PENDING for manual
    reconciliation instead of either crediting or hard-rejecting.
    """
    form = await request.form()
    payload = dict(form)

    transaction_reference = payload.get("TransactionReference")
    if not transaction_reference:
        raise HTTPException(status_code=400, detail="Missing TransactionReference")

    attempt = db.get(PaymentAttempt, transaction_reference)
    if attempt is None or attempt.method != PaymentMethod.OZOW:
        raise HTTPException(status_code=404, detail="Unknown payment attempt")

    if attempt.status == PaymentStatus.SUCCEEDED:
        return {"status": attempt.status.value, "credits_granted": attempt.credits_granted}

    if not ozow_service.verify_notify_hash(payload):
        logger.error(
            "Ozow notify HashCheck did not match for attempt %s — leaving PENDING for manual "
            "review rather than crediting or hard-rejecting (see ozow_service.verify_notify_hash's "
            "docstring)",
            attempt.id,
        )
        return {"status": attempt.status.value, "credits_granted": False}

    status = str(payload.get("Status", ""))
    if status != "Complete":
        attempt.status = PaymentStatus.FAILED if status in ("Cancelled", "Error") else attempt.status
        db.add(attempt)
        db.commit()
        return {"status": attempt.status.value, "credits_granted": False}

    attempt.status = PaymentStatus.SUCCEEDED
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    user = db.get(User, attempt.user_id)
    if user is not None and not attempt.credits_granted:
        credit_service.grant_purchased_credits(db, user, attempt)

    return {"status": attempt.status.value, "credits_granted": True}


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
