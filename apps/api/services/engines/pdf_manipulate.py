"""
app/services/engines/pdf_manipulate.py

Real PDF manipulation — merge, split, extract, watermark, rotate, crop,
page numbers, password protect/unlock, repair, compress, reorder. This
replaces the earlier php-pdf stub: php-pdf was never confirmed as a real
maintained project (see docs/engines.md), so this uses a verified,
properly-licensed Python stack instead — pypdf (BSD-3-Clause) for page
operations and encryption, pikepdf (MPL-2.0, wraps qpdf/Apache-2.0) for
repair and compression, reportlab (BSD) for generating overlay content
(watermarks, page numbers).

Deliberately NOT implemented here: digital signing (needs a real cert /
PKI setup, not just "add a signature-shaped object"), true redaction
(covering content with a black box is not redaction — the underlying
text is still in the content stream and extractable; doing this correctly
means rewriting the content stream, which needs more care than this pass
budgeted for), and PDF/A conversion (the standard open tool is Ghostscript,
which is AGPL — same category of licensing risk as iText; see
docs/licensing.md). All three return a clear "not implemented" error
rather than silently doing the wrong thing.
"""
from __future__ import annotations

import io
from typing import Any, BinaryIO

import pikepdf
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .base import Engine, EngineResult


def _parse_page_spec(spec: str, page_count: int) -> list[int]:
    """Parse '1,3,5-7' (1-based, inclusive) into a 0-based index list, in order given."""
    indices: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_s, end_s = chunk.split("-", 1)
            start, end = int(start_s), int(end_s)
        else:
            start = end = int(chunk)
        for p in range(start, end + 1):
            if 1 <= p <= page_count:
                indices.append(p - 1)
    return indices


class PdfManipulateEngine(Engine):
    name = "pdf_manipulate"

    def __init__(self) -> None:
        self._handlers = {
            "pdf_merge": self._merge,
            "pdf_split": self._split,
            "pdf_extract_pages": self._extract_pages,
            "pdf_watermark": self._watermark,
            "pdf_rotate": self._rotate,
            "pdf_crop": self._crop,
            "pdf_add_page_numbers": self._add_page_numbers,
            "pdf_protect": self._protect,
            "pdf_unlock": self._unlock,
            "pdf_repair": self._repair,
            "pdf_compress": self._compress,
            "pdf_organize": self._organize,
            "pdf_sign": self._not_implemented("Digital signing needs real PKI/certificate infrastructure"),
            "pdf_redact": self._not_implemented(
                "Overlay-based redaction leaves the original text extractable — "
                "not implemented until content-stream-level redaction is built"
            ),
            "pdf_to_pdfa": self._not_implemented(
                "PDF/A conversion needs Ghostscript, which is AGPL — see docs/licensing.md for the "
                "same class of licensing risk flagged for iText. Needs a decision before wiring this up."
            ),
        }

    def process(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        tool_name = options.get("tool_name")
        handler = self._handlers.get(tool_name)
        if handler is None:
            return EngineResult(ok=False, error=f"PdfManipulateEngine has no handler for '{tool_name}'")
        try:
            return handler(input_data, options)
        except Exception as exc:  # noqa: BLE001 — surface as a clean engine error, not a 500
            return EngineResult(ok=False, error=f"{tool_name} failed: {exc}")

    def _not_implemented(self, reason: str):
        def handler(_input_data, _options):
            return EngineResult(ok=False, error=f"Not implemented: {reason}")

        return handler

    # -- handlers ---------------------------------------------------------

    def _merge(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        extra_files: list[bytes] = options.get("extra_files") or []
        if not extra_files:
            return EngineResult(ok=False, error="pdf_merge needs at least one file in options['extra_files']")

        writer = pikepdf.new()
        for raw in [input_data.read(), *extra_files]:
            with pikepdf.open(io.BytesIO(raw)) as src:
                writer.pages.extend(src.pages)

        buf = io.BytesIO()
        writer.save(buf)
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf",
                             meta={"page_count": len(writer.pages)})

    def _split(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        import zipfile

        reader = PdfReader(input_data)
        page_ranges = options.get("page_ranges")  # e.g. "1-2,3-4"; default: one PDF per page

        groups: list[list[int]]
        if page_ranges:
            groups = [_parse_page_spec(g, len(reader.pages)) for g in page_ranges.split(";")]
        else:
            groups = [[i] for i in range(len(reader.pages))]

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, group in enumerate(groups, start=1):
                writer = PdfWriter()
                for idx in group:
                    writer.add_page(reader.pages[idx])
                part_buf = io.BytesIO()
                writer.write(part_buf)
                zf.writestr(f"part_{i:02d}.pdf", part_buf.getvalue())

        return EngineResult(
            ok=True, output_bytes=zip_buf.getvalue(), content_type="application/zip",
            meta={"parts": len(groups)},
        )

    def _extract_pages(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        pages_spec = options.get("pages")
        if not pages_spec:
            return EngineResult(ok=False, error="pdf_extract_pages needs options['pages'], e.g. '1,3,5-7'")

        reader = PdfReader(input_data)
        indices = _parse_page_spec(pages_spec, len(reader.pages))
        if not indices:
            return EngineResult(ok=False, error=f"No valid pages matched '{pages_spec}'")

        writer = PdfWriter()
        for idx in indices:
            writer.add_page(reader.pages[idx])

        buf = io.BytesIO()
        writer.write(buf)
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf",
                             meta={"extracted": len(indices)})

    def _watermark(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        text = options.get("text", "TweakHub")
        reader = PdfReader(input_data)

        overlay_buf = io.BytesIO()
        c = canvas.Canvas(overlay_buf, pagesize=letter)
        c.saveState()
        c.setFont("Helvetica-Bold", 60)
        c.setFillGray(0.5, 0.3)
        c.translate(letter[0] / 2, letter[1] / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        c.save()
        overlay_page = PdfReader(overlay_buf).pages[0]

        writer = PdfWriter()
        for page in reader.pages:
            page.merge_page(overlay_page)
            writer.add_page(page)

        buf = io.BytesIO()
        writer.write(buf)
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf")

    def _rotate(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        angle = int(options.get("angle", 90))
        if angle % 90 != 0:
            return EngineResult(ok=False, error="angle must be a multiple of 90")

        reader = PdfReader(input_data)
        writer = PdfWriter()
        for page in reader.pages:
            page.rotate(angle)
            writer.add_page(page)

        buf = io.BytesIO()
        writer.write(buf)
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf")

    def _crop(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        margin_percent = float(options.get("margin_percent", 10))
        reader = PdfReader(input_data)
        writer = PdfWriter()
        for page in reader.pages:
            box = page.mediabox
            dx = float(box.width) * margin_percent / 100
            dy = float(box.height) * margin_percent / 100
            page.mediabox.lower_left = (float(box.left) + dx, float(box.bottom) + dy)
            page.mediabox.upper_right = (float(box.right) - dx, float(box.top) - dy)
            writer.add_page(page)

        buf = io.BytesIO()
        writer.write(buf)
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf")

    def _add_page_numbers(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        start = int(options.get("start", 1))
        reader = PdfReader(input_data)
        writer = PdfWriter()

        for i, page in enumerate(reader.pages):
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            overlay_buf = io.BytesIO()
            c = canvas.Canvas(overlay_buf, pagesize=(width, height))
            c.setFont("Helvetica", 10)
            c.drawCentredString(width / 2, 20, str(start + i))
            c.save()
            overlay_page = PdfReader(overlay_buf).pages[0]
            page.merge_page(overlay_page)
            writer.add_page(page)

        buf = io.BytesIO()
        writer.write(buf)
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf")

    def _protect(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        password = options.get("password")
        if not password:
            return EngineResult(ok=False, error="pdf_protect needs options['password']")

        reader = PdfReader(input_data)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(user_password=password)

        buf = io.BytesIO()
        writer.write(buf)
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf")

    def _unlock(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        password = options.get("password")
        if not password:
            return EngineResult(ok=False, error="pdf_unlock needs options['password']")

        reader = PdfReader(input_data)
        if reader.is_encrypted:
            result = reader.decrypt(password)
            if result == 0:
                return EngineResult(ok=False, error="Incorrect password")

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        buf = io.BytesIO()
        writer.write(buf)
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf")

    def _repair(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        raw = input_data.read()
        try:
            with pikepdf.open(io.BytesIO(raw)) as pdf:
                buf = io.BytesIO()
                pdf.save(buf)
                return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf",
                                     meta={"repaired_with": "pikepdf/qpdf"})
        except pikepdf.PdfError as exc:
            return EngineResult(ok=False, error=f"Could not repair PDF: {exc}")

    def _compress(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        raw = input_data.read()
        with pikepdf.open(io.BytesIO(raw)) as pdf:
            buf = io.BytesIO()
            pdf.save(
                buf,
                compress_streams=True,
                recompress_flate=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
            )
        before, after = len(raw), buf.tell()
        return EngineResult(
            ok=True, output_bytes=buf.getvalue(), content_type="application/pdf",
            meta={"bytes_before": before, "bytes_after": after},
        )

    def _organize(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        order = options.get("order")  # 1-based list, e.g. [3, 1, 2]
        if not order:
            return EngineResult(ok=False, error="pdf_organize needs options['order'], e.g. [3, 1, 2]")

        reader = PdfReader(input_data)
        writer = PdfWriter()
        for p in order:
            idx = int(p) - 1
            if not (0 <= idx < len(reader.pages)):
                return EngineResult(ok=False, error=f"Page {p} out of range")
            writer.add_page(reader.pages[idx])

        buf = io.BytesIO()
        writer.write(buf)
        return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf")
