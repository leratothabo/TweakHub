"""
app/services/ozow_service.py

Ozow (https://ozow.com) — South African instant EFT: the customer
authorizes the payment through their own online banking, and Ozow
redirects back / calls a notify webhook once it settles. This is a
different gateway from DPO (services/payment_service.py) with its own
wire format, not something DPO routes on TweakHub's behalf.

The request-hash algorithm and endpoint below were cross-checked against
two independent, code-level sources rather than assumed from a training-
data recollection of "how these South African EFT gateways usually work"
— see the docstrings on _hash_check() and initiate_ozow_payment() for
what was actually confirmed and where the honest uncertainty still is.
After the AVX/ConvertAgent/TerraPDF episode earlier in this project
(three "integrations" that turned out to name projects nobody could
confirm were real), guessing a wire format and shipping it as fact isn't
a mistake worth repeating — so where this module isn't confident, it says
so in a comment rather than filling the gap with a plausible-looking
guess.

Needs OZOW_SITE_CODE / OZOW_PRIVATE_KEY / OZOW_API_KEY from the Ozow
merchant dashboard in .env before this will work — see config.py.
"""
from __future__ import annotations

import hashlib

import httpx

from config import get_settings


class OzowServiceError(Exception):
    pass


def _hash_check(fields: list[str], private_key: str) -> str:
    """Ozow's HashCheck: every field value concatenated in a fixed order,
    the private key appended, the whole string lowercased, then SHA-512
    hex-digested. Confirmed identical across two independent, code-level
    sources (a public reference implementation's payment.php and a
    walkthrough of the same flow in Laravel) rather than assumed — both
    agree on lowercase-before-hash and SHA-512, not e.g. HMAC-SHA512."""
    raw = "".join(fields) + private_key
    return hashlib.sha512(raw.lower().encode("utf-8")).hexdigest()


def initiate_ozow_payment(
    *,
    amount_zar: float,
    transaction_reference: str,
    bank_reference: str,
) -> tuple[str, str]:
    """
    POST a payment request to Ozow's postpaymentrequest API, return
    (payment_url, ozow_transaction_id) to redirect the customer to.

    Endpoint (https://api.ozow.com/postpaymentrequest) and the request
    field list (SiteCode, CountryCode, CurrencyCode, Amount,
    TransactionReference, BankReference, CancelUrl, ErrorUrl, SuccessUrl,
    NotifyUrl, IsTest, HashCheck) are confirmed by the same two sources as
    _hash_check() above. The response is expected to carry a `url` to
    redirect to and a `paymentRequestId` — kept as ozow_transaction_id for
    audit/debugging, not as the notify webhook's lookup key (that's
    transaction_reference, which routes/payments.py sets to the
    PaymentAttempt's own id, the same pattern payment_service.py already
    uses for DPO's CompanyRef).

    Ozow settles in ZAR only — `amount_zar` should be the package's own
    `price_zar` (CREDIT_PACKAGES already prices every package in both
    currencies; no live USD/ZAR conversion needed or attempted here).
    """
    settings = get_settings()
    if not settings.ozow_site_code or not settings.ozow_private_key:
        raise OzowServiceError("OZOW_SITE_CODE / OZOW_PRIVATE_KEY are not configured")

    amount = f"{amount_zar:.2f}"
    is_test = "true" if settings.ozow_is_test else "false"
    cancel_url = f"{settings.base_url}/payment-callback?method=ozow&status=cancelled"
    error_url = f"{settings.base_url}/payment-callback?method=ozow&status=error"
    success_url = f"{settings.base_url}/payment-callback?method=ozow&status=success"
    notify_url = f"{settings.api_url}/api/payments/ozow/notify"

    # Field order here is the order both source implementations hash in —
    # changing it changes the HashCheck Ozow computes on their side too,
    # so it isn't just cosmetic.
    hash_fields = [
        settings.ozow_site_code,
        settings.ozow_country_code,
        settings.ozow_currency_code,
        amount,
        transaction_reference,
        bank_reference,
        cancel_url,
        error_url,
        success_url,
        notify_url,
        is_test,
    ]
    hash_check = _hash_check(hash_fields, settings.ozow_private_key)

    payload = {
        "SiteCode": settings.ozow_site_code,
        "CountryCode": settings.ozow_country_code,
        "CurrencyCode": settings.ozow_currency_code,
        "Amount": amount,
        "TransactionReference": transaction_reference,
        "BankReference": bank_reference,
        "CancelUrl": cancel_url,
        "ErrorUrl": error_url,
        "SuccessUrl": success_url,
        "NotifyUrl": notify_url,
        "IsTest": is_test,
        "HashCheck": hash_check,
    }

    try:
        response = httpx.post(
            f"{settings.ozow_api_base_url}/postpaymentrequest",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json", "ApiKey": settings.ozow_api_key},
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OzowServiceError(f"Ozow postpaymentrequest failed: {exc}") from exc

    data = response.json()
    if not data.get("success", data.get("Success", True)) and "url" not in data and "Url" not in data:
        raise OzowServiceError(f"Ozow postpaymentrequest returned no redirect url: {data}")

    url = data.get("url") or data.get("Url")
    if not url:
        raise OzowServiceError(f"Ozow postpaymentrequest response missing url: {data}")

    transaction_id = data.get("paymentRequestId") or data.get("PaymentRequestId") or ""
    return url, transaction_id


def verify_notify_hash(payload: dict) -> bool:
    """
    Verify the HashCheck Ozow sends on the notify webhook, using the five
    fields (SiteCode, TransactionId, TransactionReference, Amount,
    Status) both sources agree the notify payload carries, hashed the
    same way as the request (lowercase, concatenate, append the private
    key, SHA-512).

    Honest gap, flagged rather than papered over: unlike the request-side
    hash in initiate_ozow_payment() — confirmed field-for-field by two
    independent code-level sources — neither source shows the notify
    payload's *complete* field set or proves nothing else is folded into
    its hash. If Ozow's real notify hash includes more fields than these
    five, every genuine notification will fail this check (a false
    negative, not a false positive) — the opposite failure mode from a
    forged callback getting through. That's why routes/payments.py's
    ozow_notify does NOT hard-fail a purchase on a hash mismatch the way
    the DPO callback hard-fails on a bad token: it logs loudly and leaves
    the attempt PENDING for manual reconciliation instead of either
    silently crediting or silently dropping the notification. Test this
    against Ozow's real sandbox once real OZOW_* credentials exist, and
    adjust the field list here from Ozow's actual merchant-dashboard docs
    if a genuine notification's hash doesn't match — the same "verify
    against the real thing before trusting it in production" step this
    project already calls out for DPO_WEBHOOK_IP_ALLOWLIST.
    """
    settings = get_settings()
    if not settings.ozow_private_key:
        return False

    received_hash = str(payload.get("HashCheck", ""))
    if not received_hash:
        return False

    fields = [
        str(payload.get("SiteCode", "")),
        str(payload.get("TransactionId", "")),
        str(payload.get("TransactionReference", "")),
        str(payload.get("Amount", "")),
        str(payload.get("Status", "")),
    ]
    expected = _hash_check(fields, settings.ozow_private_key)
    return expected == received_hash.lower()
