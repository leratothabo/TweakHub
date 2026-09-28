"""
app/services/brevo_service.py

Brevo (https://www.brevo.com) transactional email HTTP API -- used only
for campaign sends (services/campaign_worker.py), one call per
recipient. Deliberately built on Brevo's transactional `/smtp/email`
endpoint, not Brevo's own Campaigns/Contacts product: using Brevo's own
list/campaign machinery would create a second, competing source of
truth for consent/unsubscribe state outside this app's database, which
directly conflicts with services/subscriber_service.py being the single
place that decides who TweakHub is allowed to email. TweakHub's own DB
stays authoritative; Brevo is just the wire that carries the message.

The `api-key` header name is confirmed from Brevo's own public API
docs. The exact JSON field names below (sender/to/subject/htmlContent)
match Brevo's documented request shape as of this writing, but -- same
discipline this repo already applies to Ozow/DPO (see
services/ozow_service.py's docstring, and the AVX/ConvertAgent/TerraPDF
postmortem in docs/engines.md) -- this should be spot-checked against a
real sandbox call once the user's Brevo account exists, rather than
trusted purely from training-data recall.

Separate from services/email_service.py on purpose: that module is
SMTP/console-backed, single-recipient transactional mail (verification,
password reset), and is the fix for EMAIL_BACKEND=console -- a pure
.env change, not a code path this module touches.
"""
from __future__ import annotations

import httpx

from config import get_settings


class BrevoServiceError(Exception):
    pass


def send_transactional_email(
    *,
    to_email: str,
    to_name: str | None,
    subject: str,
    html_content: str,
) -> str:
    """POSTs one email via Brevo's /smtp/email endpoint, returns Brevo's
    messageId (recorded on CampaignRecipient.brevo_message_id so a future
    webhook pass can correlate delivery/open/click/bounce events back to
    this specific send)."""
    settings = get_settings()
    if not settings.brevo_api_key or not settings.brevo_sender_email:
        raise BrevoServiceError("BREVO_API_KEY / BREVO_SENDER_EMAIL are not configured")

    payload = {
        "sender": {"email": settings.brevo_sender_email, "name": settings.brevo_sender_name},
        "to": [{"email": to_email, "name": to_name} if to_name else {"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }

    try:
        response = httpx.post(
            f"{settings.brevo_base_url}/smtp/email",
            json=payload,
            headers={
                "api-key": settings.brevo_api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise BrevoServiceError(f"Brevo /smtp/email failed: {exc}") from exc

    data = response.json()
    message_id = data.get("messageId")
    if not message_id:
        raise BrevoServiceError(f"Brevo /smtp/email response missing messageId: {data}")
    return message_id
