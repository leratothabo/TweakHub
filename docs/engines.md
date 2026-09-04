# Engine integration status

`apps/api/services/engines/` implements five engines behind a common
`Engine.process()` interface (see `engines/base.py`). As of this pass,
four of them do real work — no more HTTP calls to an unverified
third-party microservice. The original plan named AVX, ConvertAgent, and
TerraPDF as the backend, but none of them were ever confirmed as real
maintained projects (see the "Open Risks" note in
`docs/tweakhub-master-plan.md`), so they were replaced with a verified,
properly-licensed open-source stack that runs in-process or via subprocess
— see `docs/licensing.md` for what each dependency actually is and its
license.

| Catalog engine key | File | Backing tools | Status |
|---|---|---|---|
| `manipulate` | `pdf_manipulate.py` | pypdf, pikepdf, reportlab | Real — merge, split, extract, watermark, rotate, crop, page numbers, protect, unlock, repair, compress, reorder |
| `generate` | `pdf_generate.py` | reportlab | Real — invoice, certificate, report generation from JSON |
| `convert` | `media_convert.py` | Pillow, ffmpeg, poppler-utils, pypdf/reportlab, openpyxl, rembg+onnxruntime | Real — image ops (including ML background removal), pdf↔image, pdf↔text, csv↔xlsx, video/audio |
| `document` | `document_convert.py` | LibreOffice headless, Playwright+Chromium, poppler-utils, tesseract | Real — office format pairs, html/markdown→pdf, pdf→html, OCR |
| `edit` | `pdf_editor_engine.py` | — | Still a stub — PDFEditor is a client-side React component (`apps/web`); this only needs a server-side flatten/persist endpoint once the frontend's annotation-layer contract is defined |

Every handler in the four real engines was verified against an actual
generated file (a real PDF from reportlab, a real PNG from Pillow, a real
WAV/MP4 from ffmpeg) before being wired up — see
`apps/api/tests/test_engines.py`, 174 tests, all exercising real input
through the real library or CLI tool. `image_bg_remove`'s test builds a
synthetic subject-on-plain-background image and asserts on the actual
alpha channel of the real model's output (background pixels transparent,
subject pixels opaque) — not just "the call didn't raise." Tests that need
a system binary (LibreOffice, ffmpeg, poppler, tesseract, Playwright's
Chromium) skip cleanly if that binary isn't installed, and
`image_bg_remove`'s test skips cleanly if rembg's model host
(github.com's release CDN) isn't reachable, since the model downloads on
first use rather than shipping in the repo. Both
`infrastructure/docker/Dockerfile.api` and `.github/workflows/test.yml`
install the full toolchain (and have working network egress to GitHub),
so in CI and in the built image none of these skip.

## Tools deliberately left as stubs — and why

A few tools return a clean `"Not implemented: <reason>"` instead of fake
output. Some are out of scope for this pass (need an ML model); a couple
were tried and empirically found not to work with what's installed rather
than just left un-investigated:

| Tool | Engine | Why it's a stub |
|---|---|---|
| `pdf_sign` | manipulate | Needs real PKI/certificate infrastructure, not just an object shaped like a signature |
| `pdf_redact` | manipulate | Overlay-based "redaction" leaves the original text extractable from the content stream — doing this correctly needs content-stream-level rewriting |
| `pdf_to_pdfa` | manipulate | The standard open tool is Ghostscript, which is **AGPL** — the same class of licensing risk flagged for iText (see docs/licensing.md). Needs a decision before wiring up. |
| `pdf_to_excel` | document | **Tried and confirmed broken**: LibreOffice has no real PDF-into-spreadsheet import path. Needs a table-extraction library (e.g. camelot) instead. |
| `pdf_to_ppt` | document | **Tried and confirmed broken**: routing a PDF through LibreOffice Draw and exporting to `.pptx` returns exit code 0 and a valid zip, but with zero slides inside — silently empty output. Left as a stub rather than shipped broken. |
| `epub_to_pdf` | document | **Tried and confirmed broken**: this LibreOffice install has no EPUB import filter — fails on a real, freshly-generated `.epub` with "source file could not be loaded". Needs a different tool (e.g. Calibre's `ebook-convert`). |
| `audio_to_text` | convert | Needs a speech-to-text model, e.g. Whisper or faster-whisper. **Investigated, not just skipped**: both projects' standard model hosts — `huggingface.co`/`cdn-lfs.huggingface.co` (Whisper via transformers/faster-whisper) and `openaipublic.azureedge.net` (OpenAI's own Whisper weights) — return 403/connection-refused from this dev sandbox's network egress allowlist, confirmed via direct HTTP HEAD checks, not assumed. `image_bg_remove` below hit the same class of question and turned out to be solvable (its model host, github.com's release CDN, is reachable) — this one isn't, without either a different network allowlist or a self-hosted mirror of the model weights. |

`image_bg_remove` (`convert` engine) is real now: `rembg` (MIT) running the
`u2netp` ONNX model (Apache-2.0, downloaded on first use from rembg's
GitHub release — see `docs/licensing.md`). `u2netp` (~4.5MB) rather than
rembg's default `u2net` (~176MB) because this tool resolves synchronously
inline in the HTTP request (image-category, not in `ASYNC_TOOL_NAMES`), so
bounded latency mattered more here than the small quality edge `u2net` has
on complex scenes.

## How request-time parameters work

Most tools need more than just the uploaded file — a rotation angle, a
watermark's text, a target format, which pages to extract, a password.
`POST /api/tools/{tool}/process` accepts an `options` form field (a JSON
object) alongside `file`, and an optional `extra_files` list for tools
that combine multiple inputs (`pdf_merge`, `video_merge`, `audio_merge`,
`pdf_compare`, `subtitle_burn`). Each engine handler documents what it
reads from `options` in its own docstring/code — there's no single shared
schema across all 207 tools because their parameters genuinely differ.

Internally, `ToolRouter.route_tool()` always injects `tool_name` into the
options dict before calling the engine — every engine dispatches on
`options["tool_name"]` via a `{tool_name: handler}` table rather than
parsing the catalog's `engine_op` string, since several tools legitimately
share the same operation name (e.g. `resize` means something different
for `image_resize` vs. `video_resize`) and only `tool_name` disambiguates
them unambiguously.

## Sync vs. async: how a tool run actually resolves

Every call to `POST /api/tools/{tool}/process` creates a `ProcessingJob`
row (`apps/api/models/processing_job.py`) and, either way, the output
lands in object storage (`apps/api/services/storage_service.py`) rather
than being inlined into the response — see `docs/TODO.md`'s object-storage
note for why. What differs is *when* the engine actually runs:

- **Most tools (sync)**: resolved inline, in the same request. The
  response is `200` with `status: "succeeded"` and a signed `download_url`
  already in it.
- **Video-category tools, and everything routed to the `document` engine**
  (`routes/tools.py`'s `ASYNC_TOOL_NAMES`, computed from the catalog, not
  hand-maintained — currently 80 tools: all 41 `video_*` tools (including
  the named-pair ones like `mp4_to_webm`/`mp4_to_avi`/`mp4_to_wmv`/
  `mp4_to_mp3`) plus 38 document-engine ones (e.g. `word_to_pdf`,
  `pdf_to_markdown`, `ods_to_pdf`, `rtf_to_txt`, `ods_to_csv`) plus
  `ocr_extract` — `csv_to_xlsx`/`xlsx_to_csv` are `document`-category but
  `convert`-engine, so they stay synchronous like the rest of that
  engine): the request returns `202` with `status: "pending"`
  and a `job_id` instead. An `rq worker` process (see
  `apps/workers/README.md`) picks the job off Redis, runs it, and updates
  the same row — poll `GET /api/jobs/{job_id}` until status leaves
  pending/processing.

Both paths share one response shape (`apps/api/services/job_presenter.py`
builds it from the `ProcessingJob` row either way), so a client doesn't
need two different response parsers — only a check on `is_async` /
`status` to know whether to poll.

## Known limitations worth knowing about before you rely on these

- **`pdf_to_markdown` is intentionally lossy** — it dumps extracted text
  per page under a heading; it does not reconstruct headings, tables, or
  layout from the PDF. A layout-aware conversion needs a heavier tool.
- **`html_to_pdf` has no external-resource resolution** — `page.set_content()`
  has no base URL, so relative image/CSS links in the submitted HTML won't
  load. Fine for self-contained HTML (which is what `markdown_to_pdf`
  always produces), a real limitation for arbitrary user HTML. It's also
  why `services/job_worker.py` runs it inside a plain `rq worker` process
  rather than any asyncio-based worker — Playwright's sync API (used
  here) refuses to run nested inside an already-running asyncio event
  loop, which a real `rq worker` process never has but an asyncio-based
  one (e.g. `arq`) would; keep that in mind if the job queue is ever
  swapped.
- **`video_trim` uses stream copy** (`-c copy`) for speed, which means cut
  points snap to the nearest keyframe rather than being frame-accurate.
- **`pdf_to_word` output loses everything past page 1 if later re-exported
  as plain text** (`docx_to_txt`, `odt_to_txt`, and any chain through
  them) — for a *multi-page* PDF. `pdf_to_word`'s `writer_pdf_import`
  filter represents each page as an absolutely-positioned
  `draw:custom-shape` text frame rather than a normal flowing paragraph
  (inherent to that LibreOffice filter, not something this code
  controls); its plain-text exporter only picks up the first such shape.
  Single-page PDFs are unaffected. `docx_to_txt`/`odt_to_txt` both work
  correctly on ordinary directly-authored documents — this is specific to
  chaining through `pdf_to_word`'s output. If you need reliable plain
  text from a PDF, use `pdf_to_text` or `pdf_to_markdown` instead — both
  read the PDF directly and don't go through this filter. See
  `document_convert.py`'s module docstring and
  `test_engines.py::test_odt_to_txt_loses_content_past_page_1_from_a_multipage_pdf_to_word_chain`.
