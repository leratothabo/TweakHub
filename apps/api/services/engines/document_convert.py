"""
app/services/engines/document_convert.py

Real document-pair conversions. Replaces the earlier ConvertAgent stub:
ConvertAgent was never confirmed as a real maintained project (see
docs/engines.md), so this uses a verified, properly-licensed stack
instead — LibreOffice headless (MPL-2.0/LGPL) for office format
conversions, Playwright + the pre-installed Chromium for HTML/Markdown to
PDF, poppler-utils' pdftohtml (subprocess; GPL-2.0) for PDF to HTML,
pypdf for a basic PDF-to-Markdown text dump, and tesseract (Apache-2.0)
for OCR.

Every conversion in here was verified by hand against a real file before
being wired up — see the empirical notes below for the two that turned
out NOT to work and were left as stubs instead of shipped broken:

- pdf_to_excel / pdf_to_ppt: LibreOffice has no real "PDF into a
  spreadsheet/presentation" import path. The only PDF import filter that
  produces usable content is `writer_pdf_import` (into a Writer/text
  document — what pdf_to_word uses). Routing a PDF through Draw and
  exporting to .pptx *appeared* to succeed (exit code 0, valid zip) but
  produced a presentation with zero slides — silently broken, worse than
  an error. Left as a documented stub rather than shipping that.
- epub_to_pdf: this LibreOffice install has no EPUB import filter
  ("source file could not be loaded" on a valid, freshly-generated EPUB).
  Left as a stub — a real EPUB conversion needs a different tool
  (e.g. Calibre's ebook-convert) not currently installed.

Known limitation, not a stub (odt_to_txt/docx_to_txt ship working, this
just documents where they can lose content): `pdf_to_word`'s
`writer_pdf_import` filter recreates each PDF page as an absolutely
positioned `draw:custom-shape` text frame rather than normal flowing
paragraphs (this is inherent to how LibreOffice's PDF import works, not
something this code controls). For a *single-page* PDF that round-trips
through docx_to_txt/docx_to_odt/odt_to_txt fine. For a *multi-page* PDF,
found empirically while testing odt_to_txt this pass: LibreOffice's plain
-text exporter only picks up the first page's shape text and silently
drops the rest — exits 0, produces a valid but near-empty .txt, no error
anywhere. A normal .odt/.docx authored directly (not derived from a
multi-page pdf_to_word chain) has ordinary paragraphs and doesn't hit
this — verified separately. If a `pdf_to_word` output needs reliable
plain-text extraction, use `pdf_to_text` (media_convert.py's
pypdf-based handler, unaffected — reads the original PDF directly) or
`pdf_to_markdown`, not a pdf_to_word → docx_to_txt/odt_to_txt chain.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, BinaryIO

import markdown as md
from pypdf import PdfReader

from ._util import run, scratch_dir
from .base import Engine, EngineResult

# soffice needs the right *source* extension to pick the right import
# filter (it sniffs content too, but a correct extension avoids ambiguity)
# and an explicit target filter name for anything it can't disambiguate
# from the target extension alone.
_LIBREOFFICE_JOBS = {
    "word_to_pdf": ("docx", "pdf", None),
    "excel_to_pdf": ("xlsx", "pdf", None),
    "ppt_to_pdf": ("pptx", "pdf", None),
    "odt_to_pdf": ("odt", "pdf", None),
    "docx_to_odt": ("docx", "odt", None),
    "rtf_to_pdf": ("rtf", "pdf", None),
    # Verified against real seed files (a docx produced by pdf_to_word, an
    # odt produced by docx_to_odt, an xlsx produced by openpyxl) before
    # being added — see test_engines.py. Each export filter name below
    # came back with rc=0 and real, readable output, not just "soffice
    # didn't error" (that alone wasn't enough to trust for pdf_to_ppt —
    # see the module docstring).
    "docx_to_txt": ("docx", "txt", "Text"),
    "odt_to_docx": ("odt", "docx", "MS Word 2007 XML"),
    "xlsx_to_ods": ("xlsx", "ods", None),
    "ods_to_xlsx": ("ods", "xlsx", "Calc MS Excel 2007 XML"),
    # Verified the same way as the four above — real generated seed files
    # (a pptx produced by ppt_to_pdf's own docx-style round trip isn't
    # applicable here, so these were checked against a python-pptx-free
    # LibreOffice-generated pptx/odp pair and a plain .txt file — see
    # test_engines.py) before being added.
    "pptx_to_odp": ("pptx", "odp", None),
    "odp_to_pptx": ("odp", "pptx", "Impress MS PowerPoint 2007 XML"),
    "odp_to_pdf": ("odp", "pdf", None),
    "txt_to_docx": ("txt", "docx", "MS Word 2007 XML"),
    # Verified by hand against a real generated docx (html_to_docx and
    # odt_to_txt/rtf_to_docx chained off it) before being added — see
    # test_engines.py for the automated version of the same chain.
    "html_to_docx": ("html", "docx", "MS Word 2007 XML"),
    "docx_to_html": ("docx", "html", None),
    "odt_to_txt": ("odt", "txt", "Text"),
    "rtf_to_docx": ("rtf", "docx", "MS Word 2007 XML"),
    # Legacy Word 97-2003 (.doc) / Excel 97-2003 (.xls) and CSV. Verified
    # against real seed files this time round-tripped through content
    # extraction, not just "produced a valid zip/file" — burned once
    # already this pass by pdf_to_word's custom-shape quirk, so these were
    # checked for actual preserved text/cell values before being added
    # (a real .doc/.xls seed generated by LibreOffice itself exporting a
    # normal docx/xlsx — same bootstrap pattern as odt_to_docx etc. — then
    # imported back and the content confirmed present).
    "doc_to_pdf": ("doc", "pdf", None),
    "doc_to_docx": ("doc", "docx", "MS Word 2007 XML"),
    "xls_to_xlsx": ("xls", "xlsx", "Calc MS Excel 2007 XML"),
    "xls_to_pdf": ("xls", "pdf", None),
    "csv_to_pdf": ("csv", "pdf", None),
    # Closing the remaining natural gaps: ODF spreadsheet -> pdf
    # (odt_to_pdf/odp_to_pdf already existed, ods_to_pdf didn't), rtf's
    # missing plain-text/ODF-text pairs (docx_to_txt/odt_to_txt already
    # existed, rtf didn't have either), legacy .doc -> plain text, and
    # legacy .xls -> csv (openpyxl, used elsewhere in this codebase for
    # csv_to_xlsx/xlsx_to_csv, can't read the legacy binary xls format —
    # this one has to go through LibreOffice). Same verification
    # discipline as every entry above.
    "ods_to_pdf": ("ods", "pdf", None),
    "rtf_to_txt": ("rtf", "txt", "Text"),
    "rtf_to_odt": ("rtf", "odt", None),
    "doc_to_txt": ("doc", "txt", "Text"),
    "xls_to_csv": ("xls", "csv", "Text - txt - csv (StarCalc)"),
    # ODF spreadsheet <-> CSV — same CSV export filter that already works
    # for xls_to_csv (verified against a real ODS this time, not assumed
    # to carry over from the xls case), plus the reverse: LibreOffice's
    # default CSV import on a plain comma-separated file, verified end to
    # end with real header/data values checked, not just "produced a
    # file."
    "ods_to_csv": ("ods", "csv", "Text - txt - csv (StarCalc)"),
    "csv_to_ods": ("csv", "ods", None),
}


class DocumentConvertEngine(Engine):
    name = "document_convert"

    def __init__(self) -> None:
        self._handlers = {
            "pdf_to_word": self._pdf_to_word,
            "html_to_pdf": self._html_to_pdf,
            "pdf_to_html": self._pdf_to_html,
            "markdown_to_pdf": self._markdown_to_pdf,
            "pdf_to_markdown": self._pdf_to_markdown,
            "ocr_extract": self._ocr_extract,
            "pdf_to_excel": self._not_implemented(
                "LibreOffice has no working PDF-to-spreadsheet import path — verified empirically, "
                "not just unimplemented. Needs a table-extraction library (e.g. camelot) instead."
            ),
            "pdf_to_ppt": self._not_implemented(
                "LibreOffice's PDF-to-Draw-to-pptx path produces an empty deck (verified empirically) — "
                "silently broken, so left as a stub rather than shipped."
            ),
            "epub_to_pdf": self._not_implemented(
                "This LibreOffice install has no EPUB import filter (verified against a real .epub) — "
                "needs a different tool, e.g. Calibre's ebook-convert."
            ),
        }
        for tool_name in _LIBREOFFICE_JOBS:
            self._handlers[tool_name] = self._libreoffice_convert

    def process(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        tool_name = options.get("tool_name")
        handler = self._handlers.get(tool_name)
        if handler is None:
            return EngineResult(ok=False, error=f"DocumentConvertEngine has no handler for '{tool_name}'")
        try:
            return handler(input_data, options)
        except Exception as exc:  # noqa: BLE001
            return EngineResult(ok=False, error=f"{tool_name} failed: {exc}")

    def _not_implemented(self, reason: str):
        def handler(_input_data, _options):
            return EngineResult(ok=False, error=f"Not implemented: {reason}")

        return handler

    # -- LibreOffice-backed office conversions --------------------------------

    def _libreoffice_convert(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        tool_name = options["tool_name"]
        src_ext, out_ext, export_filter = _LIBREOFFICE_JOBS[tool_name]
        target = f"{out_ext}:{export_filter}" if export_filter else out_ext

        with scratch_dir() as d:
            src = d / f"in.{src_ext}"
            src.write_bytes(input_data.read())
            out_dir = d / "out"
            out_dir.mkdir()
            # -env:UserInstallation gives this invocation its own scratch
            # profile dir instead of the shared default one — defensive
            # hardening added this pass (not chasing a confirmed bug: two
            # soffice invocations sharing a profile is a known general
            # source of flakiness under concurrent use, e.g. multiple
            # simultaneous tool requests hitting this container). Every
            # _LIBREOFFICE_JOBS pair and _pdf_to_word below now gets one.
            run([
                "soffice", f"-env:UserInstallation=file://{d}/lo_profile",
                "--headless", "--convert-to", target, "--outdir", str(out_dir), str(src),
            ], timeout=90)

            produced = list(out_dir.glob(f"*.{out_ext}"))
            if not produced:
                return EngineResult(ok=False, error="LibreOffice produced no output file")

            mime = {
                "pdf": "application/pdf",
                "odt": "application/vnd.oasis.opendocument.text",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "ods": "application/vnd.oasis.opendocument.spreadsheet",
                "txt": "text/plain",
                "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "odp": "application/vnd.oasis.opendocument.presentation",
                "html": "text/html",
                "csv": "text/csv",
            }.get(out_ext, "application/octet-stream")
            return EngineResult(ok=True, output_bytes=produced[0].read_bytes(), content_type=mime)

    def _pdf_to_word(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        # PDF's only usable LibreOffice import path is `writer_pdf_import`
        # (verified — the default PDF import goes into Draw, which can't
        # export to a sane .docx). See the module docstring.
        with scratch_dir() as d:
            src = d / "in.pdf"
            src.write_bytes(input_data.read())
            out_dir = d / "out"
            out_dir.mkdir()
            run([
                "soffice", f"-env:UserInstallation=file://{d}/lo_profile",
                "--headless", "--infilter=writer_pdf_import",
                "--convert-to", "docx:MS Word 2007 XML", "--outdir", str(out_dir), str(src),
            ], timeout=90)

            produced = list(out_dir.glob("*.docx"))
            if not produced:
                return EngineResult(ok=False, error="LibreOffice produced no .docx output")
            return EngineResult(
                ok=True, output_bytes=produced[0].read_bytes(),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

    # -- HTML / Markdown <-> PDF (Playwright + Chromium) -----------------------

    def _render_html_to_pdf(self, html: str) -> bytes:
        from playwright.sync_api import sync_playwright

        chromium_path = _find_chromium()
        with sync_playwright() as p:
            launch_kwargs = {"executable_path": chromium_path} if chromium_path else {}
            browser = p.chromium.launch(**launch_kwargs)
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                return page.pdf(format="Letter", margin={"top": "0.75in", "bottom": "0.75in",
                                                           "left": "0.75in", "right": "0.75in"})
            finally:
                browser.close()

    def _html_to_pdf(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        html = input_data.read().decode("utf-8", errors="replace")
        pdf_bytes = self._render_html_to_pdf(html)
        return EngineResult(ok=True, output_bytes=pdf_bytes, content_type="application/pdf")

    def _markdown_to_pdf(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        text = input_data.read().decode("utf-8", errors="replace")
        body = md.markdown(text, extensions=["tables", "fenced_code"])
        html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
            body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; line-height: 1.5; padding: 2em; }}
            code, pre {{ background: #f4f4f4; padding: 2px 4px; border-radius: 3px; }}
            table {{ border-collapse: collapse; }} td, th {{ border: 1px solid #ccc; padding: 4px 8px; }}
        </style></head><body>{body}</body></html>"""
        pdf_bytes = self._render_html_to_pdf(html)
        return EngineResult(ok=True, output_bytes=pdf_bytes, content_type="application/pdf")

    # -- PDF -> HTML / Markdown ------------------------------------------------

    def _pdf_to_html(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        with scratch_dir() as d:
            src = d / "in.pdf"
            src.write_bytes(input_data.read())
            out = d / "out"
            run(["pdftohtml", "-noframes", str(src), str(out)], timeout=60)
            html_file = out.with_suffix(".html")
            if not html_file.exists():
                return EngineResult(ok=False, error="pdftohtml produced no output")
            return EngineResult(ok=True, output_bytes=html_file.read_bytes(), content_type="text/html")

    def _pdf_to_markdown(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        # Basic and lossy by design: this dumps extracted text per page under a
        # heading, it does not reconstruct headings/tables/formatting from PDF
        # layout. A layout-aware conversion needs a heavier tool — flagged as a
        # known limitation rather than a TODO, since "PDF to Markdown" is
        # inherently lossy without one.
        reader = PdfReader(input_data)
        parts = [f"## Page {i}\n\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages, start=1)]
        markdown_text = "\n\n".join(parts)
        return EngineResult(ok=True, output_bytes=markdown_text.encode("utf-8"), content_type="text/markdown",
                             meta={"pages": len(reader.pages), "lossy": True})

    # -- OCR: scanned PDF -> searchable PDF ------------------------------------

    def _ocr_extract(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        import pikepdf

        with scratch_dir() as d:
            src = d / "in.pdf"
            src.write_bytes(input_data.read())
            run(["pdftoppm", "-png", "-r", "300", str(src), str(d / "page")], timeout=120)

            page_images = sorted(d.glob("page-*.png"))
            if not page_images:
                return EngineResult(ok=False, error="Could not rasterize PDF for OCR")

            page_pdfs = []
            for img in page_images:
                out_base = img.with_suffix("")
                run(["tesseract", str(img), str(out_base), "pdf"], timeout=120)
                page_pdf = out_base.with_suffix(".pdf")
                if page_pdf.exists():
                    page_pdfs.append(page_pdf)

            if not page_pdfs:
                return EngineResult(ok=False, error="tesseract produced no searchable pages")

            merged = pikepdf.new()
            for p in page_pdfs:
                with pikepdf.open(p) as part:
                    merged.pages.extend(part.pages)

            buf = io.BytesIO()
            merged.save(buf)
            return EngineResult(ok=True, output_bytes=buf.getvalue(), content_type="application/pdf",
                                 meta={"pages_ocred": len(page_pdfs)})


_chromium_path_cache: list[str] = []


def _find_chromium() -> str | None:
    """Prefer the pre-installed Chromium at PLAYWRIGHT_BROWSERS_PATH over
    letting Playwright try to download its own (which the deploy environment
    may not have network access for)."""
    if _chromium_path_cache:
        return _chromium_path_cache[0] or None

    import os

    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    matches = sorted(base.glob("chromium-*/chrome-linux/chrome"))
    path = str(matches[0]) if matches else ""
    _chromium_path_cache.append(path)
    return path or None
