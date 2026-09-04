# Third-party licensing notes

TweakHub's processing engines (`apps/api/services/engines/`) wrap real
third-party tools now, not a placeholder. Their licenses aren't uniform.
Read this before adding a new tool that reaches for something not already
listed here.

## What's actually in use, and its license

| Dependency | License | How it's used |
|---|---|---|
| pypdf | BSD-3-Clause | Python library — PDF page ops, encryption |
| pikepdf (wraps qpdf) | MPL-2.0 (qpdf: Apache-2.0) | Python library — PDF repair/compression |
| reportlab | BSD (open-source edition on PyPI) | Python library — PDF generation, overlays |
| Pillow | HPND (permissive, MIT-like) | Python library — all image operations |
| pillow-heif | LGPL-3.0 | Python library — HEIC decoding. LGPL is fine to *import* (unlike GPL/AGPL) as long as it isn't statically linked in a way that prevents users from relinking a different version — using it as a normal pip dependency is the standard case LGPL is designed to permit. |
| cairosvg | LGPL-3.0 | Python library — SVG rendering. Same LGPL reasoning as pillow-heif. |
| openpyxl | MIT | Python library — xlsx read/write |
| markdown (Python-Markdown) | BSD-3-Clause | Python library — markdown→HTML |
| Playwright | Apache-2.0 | Python library — drives Chromium for HTML/Markdown→PDF |
| Chromium | BSD-style (Google) | Rendering engine Playwright drives |
| LibreOffice (headless) | MPL-2.0 / LGPL-3.0 | **Subprocess only** (`soffice --headless`) — office format conversions |
| ffmpeg | LGPL or GPL, depending on build flags — Ubuntu's package is built with `--enable-gpl` | **Subprocess only** — video/audio |
| poppler-utils (`pdftoppm`, `pdftohtml`) | GPL-2.0 | **Subprocess only** — PDF rasterization, PDF→HTML |
| tesseract-ocr | Apache-2.0 | **Subprocess only** — OCR |
| qpdf (CLI) | Apache-2.0 | Available if needed standalone; pikepdf already wraps it as a library |
| rembg | MIT | Python library — `image_bg_remove` |
| onnxruntime | MIT | Python library — rembg's inference backend |
| u2netp model weights (via rembg) | Apache-2.0 (U^2-Net, github.com/xuebinqin/U-2-Net) | Downloaded on first use from rembg's own GitHub release, not vendored in this repo |

## The subprocess boundary, and why it matters

Several of the tools above (LibreOffice, ffmpeg, poppler-utils) are
GPL or LGPL. TweakHub only ever invokes them as **separate external
processes** (`subprocess.run([...])`) — never links their code into the
Python process. This is the same pattern virtually every SaaS product
that touches PDFs, office documents, or video relies on, and it's the
mainstream, FSF-acknowledged reading of the GPL: the copyleft applies to
distributing or linking a derivative work, not to invoking an unmodified
program through its normal command-line interface. It's a well-trodden
path, not a novel interpretation — but it's still worth stating plainly
rather than assuming, the same way the iText call below is stated
plainly.

One nuance specific to ffmpeg: Ubuntu's package is typically built with
`--enable-gpl` (pulls in x264 and similar), which affects the *copyright*
license story above. Separately, some of the codecs ffmpeg can produce
(H.264, AAC) have historically carried **patent** licensing
considerations independent of ffmpeg's own copyright license — a
different legal question than "is this GPL." Worth a look before
commercial video processing at scale, but not blocking for development.

## Deliberately NOT used, and why

- **iText** (AGPL/Commercial) — not used anywhere. Under AGPL, offering
  it as part of a network service (exactly what a SaaS is) would very
  likely obligate TweakHub to make its complete corresponding source
  available to users of the service. That's incompatible with running
  TweakHub closed-source unless a commercial iText license is purchased.
  PDFBox-equivalent needs are covered by pypdf/pikepdf instead.
- **Ghostscript** (AGPL) — not used, for the same reason as iText. This
  is specifically why `pdf_to_pdfa` is a stub (see `docs/engines.md`)
  rather than wired up with `gs`, even though `gs` is the standard tool
  for PDF/A conversion. If PDF/A support becomes a priority, the decision
  is the same shape as iText: buy a commercial license, or find/build an
  Apache/MIT-licensed alternative.
- **JPedal** (Commercial) — not used. Budget for a license only if
  pixel-accurate rendering or an embedded viewer turns out to be a hard
  requirement; pdf.js (BSD) or the Playwright/Chromium path already in
  use cover most viewer needs for free.

## Action items

- [ ] If `pillow-heif` or `cairosvg`'s LGPL terms matter for your specific
      distribution model (e.g. static-linking Python into a single
      binary), get that confirmed — the reasoning above assumes normal
      pip-installed-dependency usage, which is the common case.
- [ ] Decide on Ghostscript (commercial license vs. alternative) before
      promising PDF/A conversion to users.
- [ ] Once ready to ship, generate a NOTICE file (e.g. `pip-licenses` for
      the Python dependencies) listing every license above.
