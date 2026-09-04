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
from . import ozow_service


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

    # -- Ozow (South African instant EFT, its own gateway) ---------------

    def create_ozow_attempt(
        self,
        db: Session,
        user: User,
        package_key: str,
        amount_usd: float,
        amount_zar: float,
        credits: int,
        bank_reference: str,
    ) -> tuple[PaymentAttempt, str]:
        """Same shape as create_payment_attempt() above, but against Ozow
        instead of DPO: create a PENDING row first (so a fast notify can't
        race ahead of our own commit), then call Ozow with the row's own
        id as TransactionReference — the same "our id is the thing we look
        the row up by" pattern DPO's CompanyRef already uses. amount_usd
        is stored on the row for display consistency with every other
        method; Ozow itself is only ever charged amount_zar."""
        attempt = PaymentAttempt(
            user_id=user.id,
            package_key=package_key,
            amount_usd=amount_usd,
            credits=credits,
            method=PaymentMethod.OZOW,
            status=PaymentStatus.PENDING,
        )
        db.add(attempt)
        db.flush()  # get attempt.id without committing yet

        payment_url, ozow_transaction_id = ozow_service.initiate_ozow_payment(
            amount_zar=amount_zar,
            transaction_reference=attempt.id,
            bank_reference=bank_reference,
        )
        attempt.ozow_transaction_id = ozow_transaction_id
        db.commit()
        db.refresh(attempt)

        return attempt, payment_url

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
