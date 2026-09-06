"""
app/services/payment_service.py

DPO Group (https://docs.dpopay.com) integration. DPO's actual API is
XML-based (CreateToken / verifyToken over their PayGate endpoint) rather
than the simplified REST shape sketched in the original plan — this
service models that honestly: build the XML request, POST it, parse the
XML response. Wire DPO_COMPANY_TOKEN / DPO_SERVICE_TYPE in .env before
this will work against DPO's real sandbox or production endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import io
from xml.etree import ElementTree as ET

import httpx
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from config import get_settings
from models import BankReferenceCounter, PaymentAttempt, PaymentMethod, PaymentStatus, User


class PaymentServiceError(Exception):
    pass


# Real, fixed payee details for the direct-EFT flow (create_bank_transfer_
# attempt / generate_bank_transfer_invoice_pdf below) — not environment
# config, since they don't vary between dev/staging/prod like DPO_* does;
# this is the one bank account TweakHub actually gets paid into.
BANK_TRANSFER_DETAILS = {
    "payee_name": "TweakHub",
    "payee_description": "a subsidiary of OnPoint CRM",
    "bank_name": "Standard Bank",
    "account_number": "10275365741",
}


class PaymentService:
    def __init__(self) -> None:
        self.settings = get_settings()

    # -- DPO wire format -----------------------------------------------

    def _build_create_token_xml(self, amount_usd: float, description: str, reference: str) -> str:
        return (
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<API3G>"
            f"<CompanyToken>{self.settings.dpo_company_token}</CompanyToken>"
            "<Request>createToken</Request>"
            "<Transaction>"
            f"<PaymentAmount>{amount_usd:.2f}</PaymentAmount>"
            "<PaymentCurrency>USD</PaymentCurrency>"
            f"<CompanyRef>{reference}</CompanyRef>"
            f"<RedirectURL>{self.settings.base_url}/payment-callback</RedirectURL>"
            f"<BackURL>{self.settings.base_url}/credits</BackURL>"
            "</Transaction>"
            "<Services>"
            "<Service>"
            f"<ServiceType>{self.settings.dpo_service_type}</ServiceType>"
            f"<ServiceDescription>{description}</ServiceDescription>"
            "</Service>"
            "</Services>"
            "</API3G>"
        )

    def initiate_dpo_payment(self, amount_usd: float, description: str, reference: str) -> str:
        """Create a DPO payment token, return it (used to build the redirect URL)."""
        if not self.settings.dpo_company_token:
            raise PaymentServiceError("DPO_COMPANY_TOKEN is not configured")

        xml_body = self._build_create_token_xml(amount_usd, description, reference)
        try:
            response = httpx.post(
                f"{self.settings.dpo_api_base_url}/API/v6/",
                content=xml_body,
                headers={"Content-Type": "application/xml"},
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PaymentServiceError(f"DPO createToken request failed: {exc}") from exc

        root = ET.fromstring(response.text)
        result = root.findtext("Result")
        if result != "000":
            explanation = root.findtext("ResultExplanation", default="Unknown DPO error")
            raise PaymentServiceError(f"DPO createToken failed ({result}): {explanation}")

        token = root.findtext("TransToken")
        if not token:
            raise PaymentServiceError("DPO response missing TransToken")
        return token

    def verify_dpo_payment(self, transaction_token: str) -> bool:
        """Poll DPO for a token's status. Returns True only on a confirmed success."""
        if not self.settings.dpo_company_token:
            raise PaymentServiceError("DPO_COMPANY_TOKEN is not configured")

        xml_body = (
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<API3G>"
            f"<CompanyToken>{self.settings.dpo_company_token}</CompanyToken>"
            "<Request>verifyToken</Request>"
            f"<TransactionToken>{transaction_token}</TransactionToken>"
            "</API3G>"
        )
        try:
            response = httpx.post(
                f"{self.settings.dpo_api_base_url}/API/v6/",
                content=xml_body,
                headers={"Content-Type": "application/xml"},
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PaymentServiceError(f"DPO verifyToken request failed: {exc}") from exc

        root = ET.fromstring(response.text)
        return root.findtext("Result") == "000"

    # -- Application-level flow ------------------------------------------

    def create_payment_attempt(
        self,
        db: Session,
        user: User,
        package_key: str,
        amount_usd: float,
        credits: int,
        method: PaymentMethod,
    ) -> tuple[PaymentAttempt, str]:
        """
        Create a pending PaymentAttempt row, get a DPO token for it, and
        return (attempt, payment_url). The row is committed as PENDING
        before we ever redirect the user, so a webhook that arrives before
        our own commit finishes still has a row to update.
        """
        attempt = PaymentAttempt(
            user_id=user.id,
            package_key=package_key,
            amount_usd=amount_usd,
            credits=credits,
            method=method,
            status=PaymentStatus.PENDING,
        )
        db.add(attempt)
        db.flush()  # get attempt.id without committing yet

        token = self.initiate_dpo_payment(
            amount_usd=amount_usd,
            description=f"{credits} TweakHub credits ({package_key})",
            reference=attempt.id,
        )
        attempt.dpo_transaction_token = token
        db.commit()
        db.refresh(attempt)

        payment_url = f"{self.settings.dpo_api_base_url}/payv2.php?ID={token}"
        return attempt, payment_url

    # -- Paystack (https://paystack.com/docs/api) -------------------------
    # DPO remains the processor for one-time credit purchases (the
    # PaymentMethod enum, create_payment_attempt() above, and
    # credit_service.initiate_purchase()'s CREDIT_PACKAGES flow are all
    # DPO-only and untouched by this section). Paystack is instead used
    # exclusively for the *recurring subscription* flow --
    # services/subscription_service.py calls initialize_paystack_transaction
    # (with `plan` set, so Paystack auto-creates the Subscription once the
    # first charge succeeds) and disable_paystack_subscription; the
    # webhook handler in routes/payments.py verifies every inbound event
    # with verify_paystack_webhook_signature before trusting it. These two
    # processors deliberately don't share a code path: never wire Paystack
    # into the one-time CREDIT_PACKAGES purchase flow or vice versa.

    def initialize_paystack_transaction(
        self,
        email: str,
        amount_kobo: int,
        reference: str | None = None,
        callback_url: str | None = None,
        plan: str | None = None,
    ) -> dict:
        """
        POST /transaction/initialize. amount_kobo is the charge in the
        smallest unit of the transaction currency (kobo for NGN, cents
        for USD/GHS/ZAR/KES, etc.) -- Paystack's API takes an integer
        subunit amount, never a decimal major-unit amount, so convert
        before calling this (e.g. amount_kobo = round(amount_usd * 100)).

        `plan` is a Paystack Plan code (plan_XXXXXXXXXX, from
        scripts/setup_paystack_plans.py) -- when set, Paystack
        automatically creates a Subscription tied to this transaction's
        customer once it succeeds, and will keep charging that customer
        on the plan's interval from then on (see subscription_service.py).
        Leave unset for a one-time charge with no recurrence, which is
        what every non-subscription caller of this method wants.

        Returns the response's `data` object on success:
        {"authorization_url": ..., "access_code": ..., "reference": ...}
        -- authorization_url is where the browser should be sent to pay;
        access_code is what a client-side PaystackPop.resumeTransaction()
        would use instead, if a JS-popup flow gets built later.
        """
        if not self.settings.paystack_secret_key:
            raise PaymentServiceError("PAYSTACK_SECRET_KEY is not configured")
        if amount_kobo <= 0:
            raise PaymentServiceError("amount_kobo must be a positive integer")

        payload: dict = {"email": email, "amount": str(amount_kobo)}
        if reference:
            payload["reference"] = reference
        if callback_url:
            payload["callback_url"] = callback_url
        if plan:
            payload["plan"] = plan

        try:
            response = httpx.post(
                f"{self.settings.paystack_base_url}/transaction/initialize",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.settings.paystack_secret_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PaymentServiceError(f"Paystack initialize request failed: {exc}") from exc

        body = response.json()
        if not body.get("status"):
            raise PaymentServiceError(f"Paystack initialize failed: {body.get('message', 'Unknown error')}")

        data = body.get("data") or {}
        if not data.get("authorization_url") or not data.get("reference"):
            raise PaymentServiceError("Paystack initialize response missing authorization_url/reference")
        return data

    def verify_paystack_transaction(self, reference: str) -> dict:
        """
        GET /transaction/verify/:reference -- the server-to-server check
        that actually confirms a payment. Returns the response's `data`
        object; callers must check data["status"] == "success" themselves
        before granting anything (a "abandoned"/"failed"/"pending" status
        is a valid, non-error response here, not an exception).
        """
        if not self.settings.paystack_secret_key:
            raise PaymentServiceError("PAYSTACK_SECRET_KEY is not configured")
        if not reference:
            raise PaymentServiceError("reference is required")

        try:
            response = httpx.get(
                f"{self.settings.paystack_base_url}/transaction/verify/{reference}",
                headers={"Authorization": f"Bearer {self.settings.paystack_secret_key}"},
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PaymentServiceError(f"Paystack verify request failed: {exc}") from exc

        body = response.json()
        if not body.get("status"):
            raise PaymentServiceError(f"Paystack verify failed: {body.get('message', 'Unknown error')}")

        data = body.get("data") or {}
        if not data.get("status"):
            raise PaymentServiceError("Paystack verify response missing data.status")
        return data

    def disable_paystack_subscription(self, subscription_code: str, email_token: str) -> None:
        """
        POST /subscription/disable -- stops future charges on a
        subscription. Both arguments come off the Subscription row
        (paystack_subscription_code/paystack_email_token), filled in from
        the `subscription.create` webhook (see subscription_service.py);
        Paystack requires the subscription's own per-customer email_token
        alongside its code, not just the code, as a lightweight proof
        the caller actually has the subscription's details rather than
        just guessing a code. Does not itself flip anything in our DB --
        subscription_service.cancel_subscription() only sets
        cancel_at_period_end optimistically and waits for Paystack's own
        `subscription.disable` webhook to confirm before marking the row
        CANCELLED, same "webhook/verify is the source of truth" principle
        as DPO's callback (see routes/payments.py's docstring).
        """
        # get_settings() fresh here (not self.settings, which is a
        # snapshot taken once when the module-level `payment_service`
        # singleton was constructed) -- same reasoning as deps.py's
        # rate_limit() dependency reading settings at call time: this
        # method is brand new and has no existing callers depending on
        # the snapshot behavior, so there's no reason to inherit it, and
        # reading fresh is what lets tests flip PAYSTACK_SECRET_KEY via
        # the override_settings fixture and have it actually take effect.
        settings = get_settings()
        if not settings.paystack_secret_key:
            raise PaymentServiceError("PAYSTACK_SECRET_KEY is not configured")

        try:
            response = httpx.post(
                f"{settings.paystack_base_url}/subscription/disable",
                json={"code": subscription_code, "token": email_token},
                headers={
                    "Authorization": f"Bearer {settings.paystack_secret_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PaymentServiceError(f"Paystack subscription disable request failed: {exc}") from exc

        body = response.json()
        if not body.get("status"):
            raise PaymentServiceError(f"Paystack subscription disable failed: {body.get('message', 'Unknown error')}")

    def verify_paystack_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool:
        """
        Paystack signs every webhook POST with HMAC-SHA512 of the raw
        request body, keyed by the account's secret key, sent as the
        `x-paystack-signature` header (hex-encoded) -- see
        https://paystack.com/docs/payments/webhooks/#verifying-events.
        This is the *only* thing that makes routes/payments.py's public,
        unauthenticated webhook route trustworthy: unlike the DPO
        callback (which re-verifies against DPO's own API before trusting
        anything -- see that route's docstring), Paystack's webhook body
        is trusted directly once its signature checks out, so this check
        must run before any parsing of the body and reject anything that
        fails it. Uses hmac.compare_digest for the comparison, not `==`,
        so a wrong-length or wrong-value signature can't be distinguished
        by response-time side channel.
        """
        settings = get_settings()  # fresh, not self.settings -- see disable_paystack_subscription's comment above
        if not settings.paystack_secret_key or not signature_header:
            return False

        expected = hmac.new(
            settings.paystack_secret_key.encode("utf-8"),
            raw_body,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header.strip())

    # -- Direct bank transfer (no DPO involved) --------------------------

    def _next_bank_reference(self, db: Session) -> str:
        """Row-locked increment on BankReferenceCounter (models/
        bank_reference_counter.py) rather than a SELECT COUNT(*) — two
        purchases committing at the same instant still get distinct
        references, and it's portable to the SQLite db the test suite
        runs against (a real Postgres SEQUENCE isn't)."""
        counter = (
            db.query(BankReferenceCounter)
            .filter(BankReferenceCounter.name == "bank_transfer")
            .with_for_update()
            .first()
        )
        if counter is None:
            counter = BankReferenceCounter(name="bank_transfer", value=0)
            db.add(counter)
            db.flush()
        counter.value += 1
        db.add(counter)
        db.flush()
        return f"TweakHub{counter.value:06d}"

    def create_bank_transfer_attempt(
        self,
        db: Session,
        user: User,
        package_key: str,
        amount_usd: float,
        credits: int,
    ) -> PaymentAttempt:
        """A plain EFT into TweakHub's own account — there's no gateway to
        redirect to and no webhook, so this just books a PENDING row with
        a reference number the customer puts in their transfer, and
        returns."""
        reference = self._next_bank_reference(db)

        attempt = PaymentAttempt(
            user_id=user.id,
            package_key=package_key,
            amount_usd=amount_usd,
            credits=credits,
            method=PaymentMethod.BANK_TRANSFER,
            status=PaymentStatus.PENDING,
            bank_reference=reference,
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
        return attempt

    def generate_bank_transfer_invoice_pdf(self, attempt: PaymentAttempt, user: User) -> bytes:
        """A standalone payment-instructions PDF for a BANK_TRANSFER
        attempt — deliberately not routed through the invoice_generator
        tool (services/engines/pdf_generate.py), since that's a paid,
        user-facing tool that charges credits for arbitrary invoices; this
        is TweakHub's own billing document and must never cost the
        customer credits to obtain."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter

        # -- logo placeholder ------------------------------------------
        # Swap this block for `c.drawImage("path/to/logo.png", inch, height
        # - 1.15 * inch, width=1.6 * inch, height=0.55 * inch,
        # preserveAspectRatio=True, mask="auto")` once a real logo file
        # exists — see docs/TODO.md's branding note.
        c.setDash(3, 2)
        c.setStrokeColor(colors.HexColor("#9aa0ac"))
        c.rect(inch, height - 1.15 * inch, 1.6 * inch, 0.55 * inch)
        c.setDash()
        c.setFillColor(colors.HexColor("#9aa0ac"))
        c.setFont("Helvetica", 9)
        c.drawCentredString(inch + 0.8 * inch, height - 0.9 * inch, "LOGO")
        c.setFillColor(colors.black)

        c.setFont("Helvetica-Bold", 18)
        c.drawRightString(width - inch, height - 0.85 * inch, "Payment instructions")
        c.setFont("Helvetica", 10)
        c.drawRightString(width - inch, height - 1.1 * inch, f"Reference: {attempt.bank_reference}")

        y = height - 1.7 * inch
        c.line(inch, y, width - inch, y)
        y -= 0.35 * inch

        c.setFont("Helvetica-Bold", 11)
        c.drawString(inch, y, "Pay to")
        y -= 0.24 * inch
        c.setFont("Helvetica", 10)
        details = BANK_TRANSFER_DETAILS
        for line in (
            f"{details['payee_name']} ({details['payee_description']})",
            f"Bank: {details['bank_name']}",
            f"Account number: {details['account_number']}",
        ):
            c.drawString(inch, y, line)
            y -= 0.22 * inch

        y -= 0.2 * inch
        c.setFont("Helvetica-Bold", 11)
        c.drawString(inch, y, "For")
        y -= 0.24 * inch
        c.setFont("Helvetica", 10)
        for line in (
            f"Billed to: {user.email}",
            f"Package: {attempt.package_key} ({attempt.credits:,} credits)",
            f"Amount due: {float(attempt.amount_usd):.2f} USD",
        ):
            c.drawString(inch, y, line)
            y -= 0.22 * inch

        y -= 0.3 * inch
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#ff7a3d"))
        c.drawString(inch, y, f"Use reference \"{attempt.bank_reference}\" on your transfer")
        c.setFillColor(colors.black)
        y -= 0.35 * inch

        c.setFont("Helvetica", 9)
        for line in (
            "Without this reference we can't automatically match your payment to your",
            "account. Credits are added once TweakHub confirms the deposit — usually",
            "within one business day of it clearing.",
        ):
            c.drawString(inch, y, line)
            y -= 0.18 * inch

        c.save()
        return buf.getvalue()


payment_service = PaymentService()
