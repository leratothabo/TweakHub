"""
app/services/engines/pdf_generate.py

Generates PDFs from structured JSON input — invoices, certificates,
reports. Replaces the earlier TerraPDF stub: TerraPDF was never confirmed
as a real maintained project (see docs/engines.md), so this uses reportlab
(BSD-licensed, a long-established real project) instead. Input is JSON
bytes (not a file upload) — matches packages/terra-pdf's
`buildInvoicePayload` helper on the frontend, which is exactly this
engine's counterpart.
"""
from __future__ import annotations

import io
import json
from typing import Any, BinaryIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from .base import Engine, EngineResult


class PdfGenerateEngine(Engine):
    name = "pdf_generate"

    def __init__(self) -> None:
        self._handlers = {
            "invoice_generator": self._invoice,
            "certificate_generator": self._certificate,
            "report_generator": self._report,
        }

    def process(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        tool_name = options.get("tool_name")
        handler = self._handlers.get(tool_name)
        if handler is None:
            return EngineResult(ok=False, error=f"PdfGenerateEngine has no handler for '{tool_name}'")

        try:
            payload = json.loads(input_data.read() or b"{}")
        except json.JSONDecodeError as exc:
            return EngineResult(ok=False, error=f"Invalid JSON template data: {exc}", refundable=False)

        try:
            return handler(payload)
        except Exception as exc:  # noqa: BLE001
            return EngineResult(ok=False, error=f"{tool_name} failed: {exc}")

    # -- handlers ---------------------------------------------------------

    def _invoice(self, data: dict[str, Any]) -> EngineResult:
        line_items = data.get("lineItems", [])
        currency = data.get("currency", "USD")
        total = sum(item["quantity"] * item["unitPrice"] for item in line_items)

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter

        c.setFont("Helvetica-Bold", 20)
        c.drawString(inch, height - inch, "INVOICE")
        c.setFont("Helvetica", 10)
        c.drawString(inch, height - 1.3 * inch, f"Invoice #: {data.get('invoiceNumber', '—')}")
        c.drawString(inch, height - 1.5 * inch, f"Issue date: {data.get('issueDate', '—')}")
        c.drawString(inch, height - 1.7 * inch, f"Due date: {data.get('dueDate', '—')}")

        y = height - 2.3 * inch
        c.setFont("Helvetica-Bold", 10)
        c.drawString(inch, y, "Description")
        c.drawString(4.5 * inch, y, "Qty")
        c.drawString(5.2 * inch, y, "Unit price")
        c.drawString(6.3 * inch, y, "Amount")
        c.line(inch, y - 4, width - inch, y - 4)

        c.setFont("Helvetica", 10)
        y -= 0.3 * inch
        for item in line_items:
            amount = item["quantity"] * item["unitPrice"]
            c.drawString(inch, y, str(item["description"])[:60])
            c.drawRightString(4.9 * inch, y, str(item["quantity"]))
            c.drawRightString(6.0 * inch, y, f"{item['unitPrice']:.2f}")
            c.drawRightString(width - inch, y, f"{amount:.2f}")
            y -= 0.25 * inch

        c.line(inch, y - 4, width - inch, y - 4)
        y -= 0.3 * inch
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(width - inch, y, f"Total: {total:.2f} {currency}")

        c.save()
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf",
                             meta={"total": total, "currency": currency})

    def _certificate(self, data: dict[str, Any]) -> EngineResult:
        recipient = data.get("recipientName", "—")
        title = data.get("title", "Certificate of Completion")
        body = data.get("body", "has successfully completed the requirements.")
        issued_by = data.get("issuedBy", "TweakHub")
        date = data.get("date", "")

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter

        c.setStrokeColor(colors.HexColor("#ff7a3d"))
        c.setLineWidth(4)
        c.rect(0.5 * inch, 0.5 * inch, width - inch, height - inch)

        c.setFont("Helvetica-Bold", 26)
        c.drawCentredString(width / 2, height - 2 * inch, title)

        c.setFont("Helvetica", 14)
        c.drawCentredString(width / 2, height - 2.8 * inch, "This certifies that")

        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(width / 2, height - 3.4 * inch, recipient)

        c.setFont("Helvetica", 14)
        c.drawCentredString(width / 2, height - 4 * inch, body)

        c.setFont("Helvetica", 11)
        c.drawCentredString(width / 2, 1.5 * inch, f"Issued by {issued_by} — {date}")

        c.save()
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf")

    def _report(self, data: dict[str, Any]) -> EngineResult:
        title = data.get("title", "Report")
        sections = data.get("sections", [])

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter

        c.setFont("Helvetica-Bold", 22)
        c.drawString(inch, height - inch, title)
        if data.get("subtitle"):
            c.setFont("Helvetica", 12)
            c.setFillGray(0.4)
            c.drawString(inch, height - 1.3 * inch, data["subtitle"])
            c.setFillGray(0)

        y = height - 1.9 * inch
        for section in sections:
            if y < 1.2 * inch:
                c.showPage()
                y = height - inch
            c.setFont("Helvetica-Bold", 13)
            c.drawString(inch, y, str(section.get("heading", "")))
            y -= 0.28 * inch
            c.setFont("Helvetica", 10)
            for line in _wrap_text(str(section.get("body", "")), 95):
                if y < 1.0 * inch:
                    c.showPage()
                    y = height - inch
                c.drawString(inch, y, line)
                y -= 0.2 * inch
            y -= 0.15 * inch

        c.save()
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf",
                             meta={"sections": len(sections)})


def _wrap_text(text: str, width: int) -> list[str]:
    import textwrap

    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, width) or [""])
    return lines
