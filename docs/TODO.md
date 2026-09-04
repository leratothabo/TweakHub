# What this scaffold does NOT include yet

This repo is a working skeleton: the credit/payment/tool-routing logic is
real and tested, the frontend talks to the real API shape, and the
infra/CI files will actually deploy something. What's still missing before
this is a launchable product:

## Done

- **Real authentication.** `apps/api/routes/auth.py` now has signup, login
  (bcrypt password hashing), email verification, and password reset, all
  backed by `services/auth_service.py` and covered by
  `apps/api/tests/test_auth_service.py` (9 tests, end-to-end flow also
  verified manually against a running server). Login enforces email
  verification everywhere except `NODE_ENV=development`. Frontend has a
  real signup/login form (`components/AuthPanel.tsx`) plus
  `/verify-email` and `/reset-password` pages.
  **Still open** (as of when this section was first written): no social
  OAuth, no rate limiting on login/signup, and email only logged rather
  than delivered — all three landed since; see "Social OAuth login
  (Google)", "Rate limiting", and "Real SMTP email delivery" below.
- **Database migrations.** Alembic is set up (`apps/api/alembic.ini`,
  `apps/api/migrations/`), with an initial migration covering the full
  schema including the new auth fields on `User`. `Dockerfile.api` now
  runs `alembic upgrade head` via `docker-entrypoint.sh` before starting
  uvicorn, so deploys never run against a stale schema. Generate new
  migrations with `alembic revision --autogenerate -m "..."` after any
  model change, and check the generated file before committing —
  autogenerate doesn't catch everything (renames, some constraint
  changes).

- **Real engine wiring.** All five engines were rewritten to do real work
  with a verified, properly-licensed open-source stack (pypdf, pikepdf,
  reportlab, Pillow, LibreOffice headless, ffmpeg, poppler-utils,
  tesseract, Playwright+Chromium) instead of calling out to AVX/
  ConvertAgent/TerraPDF, none of which were ever confirmed as real
  projects. 200 of the 207 catalog tools do real processing now (up from
  ~55/~70 when this section was first written — the 137 tools added since
  across six passes, see "Catalog expansion" entries below, all reuse
  this same verified engine code); see `docs/engines.md` for the full
  status table and the 7 tools left as documented stubs (three of them —
  `pdf_to_excel`, `pdf_to_ppt`, `epub_to_pdf` — were actually tried
  against LibreOffice and found broken, not just unimplemented).
  `apps/api/tests/test_engines.py` (174 tests, up from the original 46) runs
  real files through the real
  library/CLI tool (not mocks); `/api/tools/{tool}/process` now returns
  the actual processed file in the response body (with correct
  Content-Type/Content-Disposition) instead of a JSON stub, and accepts
  an `options` JSON field plus `extra_files` for multi-input tools —
  verified end-to-end over real HTTP (signup → login → upload → real
  output file), not just via direct engine calls.
  **Still open**: `audio_to_text` remains a documented stub — both
  Whisper/faster-whisper's standard model hosts (`huggingface.co` and
  `openaipublic.azureedge.net`) are unreachable from this dev sandbox's
  network egress allowlist, confirmed via direct HTTP checks rather than
  assumed; see `docs/engines.md`.

- **Per-tool timeout tuning.** `services/tool_timeouts.py` replaces the
  single blanket timeout that used to apply to every ffmpeg call
  (`media_convert.py`'s `_run_ffmpeg()`, previously always 180s) and every
  async job (`job_queue.enqueue_processing_job()`, previously always
  `JOB_TIMEOUT_SECONDS`=900s) with a lookup keyed by tool name, falling
  back through category → engine → a global default. A stream-copy op
  like `video_mute` now times out at 90s instead of sharing a re-encode
  op's 180s+ ceiling; a genuinely slow multi-input concat like
  `video_merge` gets more headroom (420s subprocess / 600s job) than the
  old blanket value gave it. 10 new tests in `test_tool_timeouts.py`,
  including one that checks every per-tool subprocess override has a
  corresponding job-level ceiling above it (so a legitimately slow-but-
  successful ffmpeg run can't get killed by RQ before it finishes).

- **image_bg_remove is real now.** `rembg` (MIT) running the `u2netp`
  ONNX model (Apache-2.0, downloaded on first use — see
  `docs/licensing.md`) replaces the old stub in
  `services/engines/media_convert.py`. Verified against a real synthetic
  test image with the actual output alpha channel checked (background
  transparent, subject opaque), not just "didn't crash" —
  `test_engines.py`'s `test_image_bg_remove_makes_the_background_transparent`,
  which skips cleanly (rather than failing) if rembg's GitHub-hosted model
  isn't reachable from wherever the suite is running.

- **Rate limiting.** `services/rate_limiter.py` is a Redis-backed
  fixed-window limiter (fails open if Redis is unreachable, rather than
  blocking every request on an infra hiccup), wired into every place that
  needed it: `/api/auth/signup`, `/api/auth/login`, and
  `/api/auth/request-password-reset` (all keyed by client IP, via
  `deps.rate_limit`), and `/api/tools/{tool}/process` (keyed by user id,
  limit chosen by `PlanTier` — `RATE_LIMIT_FREE_PER_HOUR` /
  `RATE_LIMIT_PRO_PER_HOUR` / `RATE_LIMIT_BUSINESS_PER_HOUR`;
  `ENTERPRISE` stays unmetered). Exceeding a limit returns 429 with a
  `Retry-After` header. 14 new tests in `test_rate_limiter.py` (the
  algorithm, via fakeredis) and `test_rate_limiting_routes.py` (the HTTP
  wiring, via FastAPI's TestClient) — none need a real Redis or Postgres.
- **DPO webhook hardening.** `routes/payments.py`'s re-verification
  against DPO directly (not trusting the callback payload) was already
  the primary defense and is unchanged. Added on top: a per-IP rate limit
  on `/api/payments/callback` (`RATE_LIMIT_PAYMENTS_CALLBACK_PER_HOUR`,
  same mechanism as above — the endpoint is public and every hit makes an
  outbound call to DPO, so it's worth throttling even though forged
  tokens can't grant credits), and an optional source-IP allowlist
  (`DPO_WEBHOOK_IP_ALLOWLIST`). The allowlist ships **disabled** (empty)
  by default — DPO doesn't publish a fixed IP range this codebase could
  verify and hardcode, and after the AVX/ConvertAgent/TerraPDF episode
  (three "integrations" that turned out to name projects nobody could
  confirm were real) guessing one and shipping it as fact isn't a mistake
  worth repeating. **Still open**: get DPO's actual webhook source IPs
  from their support team and set `DPO_WEBHOOK_IP_ALLOWLIST` in
  production before launch.

- **Object storage + background job queue.** Both landed together since
  they share one data model (`ProcessingJob`,
  `apps/api/models/processing_job.py`) and one response shape
  (`services/job_presenter.py`).
  `POST /api/tools/{tool}/process` no longer inlines the output into the
  response at all — every tool's result goes to object storage
  (`services/storage_service.py`: `STORAGE_BACKEND=local`, the default,
  needs nothing else configured; `STORAGE_BACKEND=s3` talks to real AWS S3
  or self-hosted MinIO via boto3 — `docker-compose` now brings up a minio
  service for this) and the response carries a signed `download_url`
  instead (a real presigned S3 URL on the s3 backend, an HMAC-token URL
  served by the new `GET /api/files/{key}` route on the local backend).
  Most tools still resolve inline, in the same request — only
  `routes/tools.py`'s `ASYNC_TOOL_NAMES` (computed from the catalog: every
  video-category tool, and everything the `document` engine handles —
  LibreOffice/Playwright/OCR, 35 tools total right now) return `202` with
  a `job_id` and get picked up by an `rq worker` process
  (`services/job_queue.py`, `services/job_worker.py`,
  `apps/workers/README.md`) instead — poll `GET /api/jobs/{job_id}`
  (`routes/jobs.py`). `docker-compose` gets a `worker` service (same image
  as `api`, different command) scalable independently.
  Retention (the 24-48h policy, `FILE_RETENTION_HOURS`) is enforced by
  `apps/api/scripts/cleanup_expired_outputs.py` — neither storage backend
  does this on its own; see that file for why and how it's meant to be
  cron-scheduled. Frontend (`lib/api.ts`, `ToolRouter.tsx`) updated to
  match: `processTool()` now returns a `JobResult` (not a `Blob`), and
  `pollJob()` handles the async case.
  Verified: 31 new tests (`test_storage_service.py` — including a real S3
  API exercised via moto, not just the local backend;
  `test_job_worker.py`; `test_job_queue.py`, which needs real Redis
  because RQ's registries aren't reliably emulated by fakeredis, and skips
  cleanly without one — CI now runs a redis service so it never skips
  there; `test_tools_process_routes.py`; `test_cleanup_expired_outputs.py`
  — 110/110 total). Also verified live against real Postgres + Redis +
  a genuine standalone `rq worker` process (not the in-process test
  shortcut) end to end: signup → login → a sync tool
  (`image_convert`) returning a working signed download link, and an
  async tool (`html_to_pdf`) going `pending` → `processing` → `succeeded`
  while a separate worker process did the actual conversion, its
  download link also verified.
  **Still open**: per-tool timeout tuning now exists (see below) but S3
  bucket lifecycle rules as a second, redundant enforcement layer for
  retention are still not configured (the app-level script is
  authoritative either way — see that file); local-backend storage
  assumes a single API/worker deployment sharing one disk (documented in
  `storage_service.py` — S3 removes that constraint).

- **Real SMTP email delivery.** `services/email_service.py` now has a
  pluggable `EmailBackend`: `console` (default, unchanged from before —
  logs "sent" emails) or `smtp` (real `smtplib` + STARTTLS, works with
  any SMTP relay — SendGrid/Postmark/SES's SMTP endpoints, or a plain
  Gmail/Workspace account). The backend is chosen fresh from settings on
  every send, not cached, so `EMAIL_BACKEND=smtp` takes effect without
  restarting anything mid-test. Verified against a real local SMTP server
  (`aiosmtpd`) in `test_email_service.py` — the smtp backend really opens
  a socket and does STARTTLS, not mocked.

- **Security headers + structured request logging.** `middleware.py`
  adds `SecurityHeadersMiddleware` (HSTS, `X-Content-Type-Options`,
  `X-Frame-Options`, a conservative `Content-Security-Policy`, etc. on
  every response) and `RequestLoggingMiddleware` (method/path/status/
  duration/best-effort user id to a dedicated `tweakhub.access` logger —
  deliberately excludes bodies, query strings, and the raw
  `Authorization` header). 8 tests in `test_middleware.py`.

- **File encryption at rest.** `storage_service.py`'s local backend now
  encrypts every file with Fernet (AES128-CBC+HMAC) before it touches
  disk, keyed from `STORAGE_ENCRYPTION_KEY` (falls back to `JWT_SECRET`
  so encryption is on by default with zero extra config). The S3 backend
  passes `ServerSideEncryption` through to `boto3` (`AES256` by default —
  verified against real AWS S3's `head_object` via `moto`).
  **Still open**: SSE against self-hosted MinIO specifically wasn't
  verified — this sandbox's network egress blocks `dl.min.io`, so that
  path is real code, not a real test; set `S3_SERVER_SIDE_ENCRYPTION=""`
  if a MinIO deployment hasn't configured its own KMS/encryption yet.

- **Referral / bonus credit flow.** `auth_service.py` generates each user
  a unique `referral_code` at signup; signing up with `?ref=CODE` links
  the two accounts (an unrecognized code is silently ignored, never
  rejects the signup). Bonus credits (25 to the invitee, 50 to the
  referrer — `REFERRAL_BONUS_CREDITS_*`) are granted once the *invitee
  verifies their email*, not at signup, so a burst of throwaway
  unverified signups can't farm credits; replay-safety comes for free
  from `verify_email()`'s existing one-time-token design. `GET
  /api/auth/referral` returns a user's own code + shareable link;
  frontend has `components/ReferralCard.tsx` and `AuthPanel.tsx` picks up
  `?ref=` automatically. 12 new tests across `test_auth_service.py` and
  `test_referral_routes.py`.

- **PWA: manifest + offline-capable service worker.**
  `apps/web/public/manifest.json` + `sw.js` (network-first with cache
  fallback for page navigations, cache-first for Next's fingerprinted
  `/_next/static/` assets, stale-while-revalidate for the app shell).
  Deliberately does *not* pretend tool processing works offline — only
  the app shell is cached. Verified with a real headless Chromium session
  (Playwright, `context.set_offline(true)`), not just "the build
  succeeded and the files exist."

- **Catalog expansion: 70 → 98 tools.** 27 new "named format pair" tools
  (`png_to_jpg`, `mp4_to_webm`, `wav_to_mp3`, `docx_to_txt`, etc. — see
  `services/tools_catalog.py`) added as pure data (a `ToolSpec` + one
  `{tool_name: handler}` entry each), every one reusing an already-real,
  already-tested generic handler (`_image_convert`/`_video_convert`/
  `_audio_convert`/`_libreoffice_convert`) rather than new engine code.
  Each pair was independently verified against a real generated/seed file
  before being catalogued — not assumed to work just because the generic
  version does. Catalog was 98 tools after this pass (pdf 28, document 20,
  image 20, video 16, audio 14) — see the next entry for the pass after
  this one, and `README.md`'s "Before you add tool #99."

- **Catalog expansion: 98 → 145 tools.** A second, larger pass of the same
  discipline as the first: 47 more tools, all pure data (`ToolSpec` +
  `{tool_name: handler}` entries), all reusing already-verified generic
  handlers — no new engine logic. Breakdown: 21 image pairs filling out
  the remaining ordered pairs among jpg/png/webp/gif/bmp/tiff (e.g.
  `jpg_to_gif`, `tiff_to_bmp` — `image_convert`'s six formats were already
  fully supported, these just cover the directions the first pass skipped);
  12 audio pairs filling out mp3/wav/flac/ogg/m4a the same way; 10 video
  pairs — 6 filling out mp4/webm/mkv/mov, plus 4 for two new containers
  (avi, flv) bidirectional with mp4 (`_video_convert`'s ffmpeg backend
  needed no changes — same content-sniffing behavior verified for the
  first batch); and 4 new LibreOffice-backed document pairs
  (`pptx_to_odp`, `odp_to_pptx`, `odp_to_pdf`, `txt_to_docx`) added as new
  entries in `document_convert.py`'s `_LIBREOFFICE_JOBS` dict (data-only —
  same generic `_libreoffice_convert` handler) plus two new mime-type
  entries (`pptx`, `odp`). The pptx pair needed a real `.pptx` seed file to
  test against, which needed `python-pptx` — added to `requirements.txt`
  as a test-fixture-only dependency (not imported by any engine/route
  code; LibreOffice does the actual conversion, same as every other pair).
  Every one of the 47 tools was independently run against a real
  generated/seed file before being catalogued (see the parametrized tests
  added to `test_engines.py`), not assumed to work from the generic
  version or a same-format-family pair already working. Current catalog:
  145 tools (image 41, pdf 28, video 26, audio 26, document 24).

- **Catalog expansion: 145 → 171 tools.** Third pass, same discipline,
  this time reaching for new *formats* rather than just filling out
  existing-format grids: 26 new tools, all pure data, all independently
  verified against a real file before being added.
  - **7 image**: ICO (favicons — `png_to_ico`, `ico_to_png`,
    `jpg_to_ico`) and AVIF (`png_to_avif`/`avif_to_png`/`jpg_to_avif`/
    `avif_to_jpg`) — both work with zero new dependencies in this
    Pillow build (12.3.0 bundles libavif; ICO is core Pillow), confirmed
    with `PIL.features.check("avif")` before relying on it, not assumed
    from the Pillow version number.
  - **1 image→pdf**: `png_to_pdf` (an obvious catalog gap — `jpg_to_pdf`
    existed, `png_to_pdf` didn't — reusing the same `_image_to_pdf`
    handler, format-agnostic).
  - **6 video**: two new containers bidirectional with mp4 — WMV
    (`mp4_to_wmv`/`wmv_to_mp4`), MPEG-TS (`mp4_to_ts`/`ts_to_mp4`), M4V
    (`mp4_to_m4v`/`m4v_to_mp4`). **3GP was tried and dropped** — ffmpeg's
    3gp muxer needs explicit `-c:v`/`-c:a` codec args the generic
    `_video_convert` handler doesn't pass (plain `-i in -o out.3gp`
    exits with an error), so it's not a same-handler fit; adding it
    would mean new per-format engine logic, which this pass's discipline
    explicitly avoids — left out rather than half-implemented.
  - **8 audio**: Opus, AAC, WMA, AIFF, each bidirectional with mp3.
  - **4 document**: `html_to_docx`, `docx_to_html`, `odt_to_txt`,
    `rtf_to_docx` — new `_LIBREOFFICE_JOBS` entries, same generic
    `_libreoffice_convert` handler, plus a new `html` mime-type entry.

  **A genuine bug found and fixed along the way, not just a test
  workaround**: `pdf_to_word`'s LibreOffice import filter recreates each
  PDF page as an absolutely-positioned text frame (`draw:custom-shape`)
  rather than a normal flowing paragraph — inherent to how that filter
  works, not something this code controls. For a single-page PDF that
  round-trips fine through `docx_to_txt`/`odt_to_txt`; for a
  *multi-page* PDF, LibreOffice's plain-text exporter silently drops
  every page but the first — exits 0, produces a valid but near-empty
  `.txt`, no error anywhere. Found while verifying the new `odt_to_txt`
  pair against `test_engines.py`'s existing 2-page `sample_pdf_bytes`
  fixture. This is a real, narrow limitation of that specific chain
  (pdf_to_word → docx_to_txt/odt_to_txt on a multi-page source) —
  `odt_to_txt`/`docx_to_txt` both work correctly on ordinary
  directly-authored documents (verified separately) and ship as working
  tools, not stubs. Documented in `document_convert.py`'s module
  docstring with the recommended alternative (`pdf_to_text`/
  `pdf_to_markdown`, which read the PDF directly and are unaffected), and
  covered by two tests — one proving `odt_to_txt` works, one pinning down
  exactly what it loses on this specific chain, so a future LibreOffice
  upgrade that fixes it shows up as a test failure to update, not a
  silent behavior change. Also hardened every `soffice` invocation with
  its own `-env:UserInstallation` scratch profile (defensive — shared
  profiles under concurrent/rapid invocations are a known general source
  of LibreOffice flakiness) while investigating this.

  Current catalog: 171 tools (image 48, audio 34, video 32, pdf 29,
  document 28); `ASYNC_TOOL_NAMES` (video + document-engine tools) is now
  59.

- **Catalog expansion: 171 → 193 tools.** Fourth pass, same discipline —
  22 new tools, all pure data, all independently verified against a real
  file with content actually checked (not just "produced a file").
  - **4 image→pdf**: `webp_to_pdf`, `gif_to_pdf`, `bmp_to_pdf`,
    `tiff_to_pdf` (jpg and png already had one; these were the missing
    common formats) — reuses the format-agnostic `_image_to_pdf` handler.
  - **5 video→mp3**: `mp4_to_mp3`, `mov_to_mp3`, `webm_to_mp3`,
    `mkv_to_mp3`, `avi_to_mp3` — named extraction pairs for one of the
    most-searched conversions in this space, reusing the existing
    `_video_extract_audio` handler (source container doesn't matter, same
    content-sniffing reasoning as every other named pair).
  - **8 audio**: connects Opus/AAC/WMA/AIFF to the wav hub, not just mp3
    (flac/ogg/m4a already had both) — same `_audio_convert` handler.
  - **5 document**: `doc_to_pdf`, `doc_to_docx`, `xls_to_xlsx`,
    `xls_to_pdf`, `csv_to_pdf` — legacy Word 97-2003/Excel 97-2003 and
    CSV, new `_LIBREOFFICE_JOBS` entries. Verified with actual content
    checked end-to-end (real `.doc`/`.xls` seed files generated by
    LibreOffice itself, imported back, text/cell values confirmed
    present) rather than just "produced a valid file" — the previous
    pass found that distinction matters (pdf_to_word's custom-shape
    quirk).

  20 new tests added to `test_engines.py`; full suite (322 tests) passed,
  re-run twice to confirm no flakiness. Current catalog: 193 tools (image
  48, audio 42, video 37, pdf 33, document 33) — 7 short of 200.
  Committed as `ea75215`.

- **Catalog expansion: 193 → 200 tools — the 200-tool goal reached.**
  Fifth and final pass of this series: 7 new tools closing out the
  catalog to the exact stated product goal, same discipline as every
  prior pass — pure data, every tool independently verified against a
  real file with content checked end-to-end before being catalogued, no
  new engine logic anywhere.
  - **2 image**: `webp_to_avif`, `avif_to_webp` — the one remaining
    ungapped pair between the two newest image formats; verified via a
    direct Pillow round trip (encode → decode → re-encode), same
    `_image_convert` handler.
  - **5 document**: `ods_to_pdf` (ODF spreadsheet → PDF, cell values
    confirmed in extracted PDF text), `rtf_to_txt` and `rtf_to_odt`
    (RTF seed generated by LibreOffice itself exporting a normal docx,
    full paragraph text confirmed present in the plain-text output and
    in `content.xml` respectively), `doc_to_txt` (legacy Word → plain
    text, full text confirmed), `xls_to_csv` (legacy Excel → CSV —
    routed through LibreOffice's own `"Text - txt - csv (StarCalc)"`
    export filter rather than `openpyxl`, which can't read the legacy
    binary `.xls` format, so no new Python dependency was needed; header
    row and data row confirmed present in the output). All five are new
    `_LIBREOFFICE_JOBS` entries plus one new `csv` mime-type entry, same
    generic `_libreoffice_convert` handler used by every prior document
    pass.

  Every one of the 7 was run through the actual engine's `.process()`
  dispatch (not just the underlying library/CLI call) before being wired
  into `tools_catalog.py`, and content-preservation was checked all the
  way through (PDF text extraction via `pypdf`, `content.xml` inspected
  via `zipfile`, plain-text `in bytes` checks) — the same elevated bar
  established after the pdf_to_word bug in the third pass. 6 new tests
  added to `test_engines.py` (168 total, up from 162); full suite (328
  tests) passed, re-run twice to confirm no LibreOffice-related
  flakiness. `services/tools_catalog.py` confirmed to have exactly 200
  unique tool names, zero duplicates: **the 200-tool catalog goal from
  the master plan has been reached** — see the "Explicitly deferred by
  design" section below for what "200 tools" means in terms of real vs.
  stubbed processing.

  Current catalog: 200 tools (image 50, audio 42, video 37, pdf 33,
  document 38); `ASYNC_TOOL_NAMES` (video + document-engine tools, plus
  `ocr_extract`) is now 74.

- **Catalog expansion: 200 → 207 tools.** Sixth pass, past the original
  200-tool goal — three genuine, specific gaps found while reviewing the
  full catalog for what was still missing, not padding for its own sake.
  All pure data, all independently verified against a real file through
  the actual engine dispatch before being catalogued.
  - **1 pdf→image**: `pdf_to_tiff` — `pdftoppm` (poppler) natively
    supports a third output format (`-tiff`) alongside the `-jpeg`/`-png`
    the existing `_pdf_to_image` handler already picked from; confirmed
    with `pdftoppm -h` rather than assumed, then the handler's
    format→flag lookup was widened from an if/else to a small dict with
    one more entry — not new conversion logic, the same poppler call
    just given one more legitimate flag to choose from.
  - **4 video→mp3**: `flv_to_mp3`, `wmv_to_mp3`, `ts_to_mp3`, `m4v_to_mp3`
    — completes the "extract audio to mp3" set for every video container
    this catalog supports (mp4/mov/webm/mkv/avi already had it), same
    `_video_extract_audio` handler.
  - **2 document**: `ods_to_csv`, `csv_to_ods` — ODF spreadsheet <-> CSV,
    reusing the same LibreOffice CSV export filter already verified for
    `xls_to_csv` (re-verified here against a real `.ods` seed rather than
    assumed to carry over) plus the reverse import direction, new
    `_LIBREOFFICE_JOBS` entries.

  Deliberately **not** added in this pass: further ICO/AVIF combinations
  (e.g. `gif_to_ico`, `avif_to_bmp`) — every one of those would work
  mechanically (Pillow is fully generic), but that's exactly the
  combinatorial-padding pattern this catalog's discipline has
  consistently avoided since the first "Catalog expansion" entry; ICO
  and AVIF already have real, justified coverage (favicons, and mp3-hub-
  style bidirectional pairing with png/jpg) and don't need every cross
  pair filled in to be useful.

  Verified: 6 new tests added to `test_engines.py` (174 total, up from
  168); full suite (334 tests) passed, re-run twice to confirm no
  LibreOffice/ffmpeg-related flakiness. `services/tools_catalog.py`
  confirmed to have exactly 207 unique tool names, zero duplicates.
  Current catalog: 207 tools (image 50, audio 42, video 41, pdf 34,
  document 40); `ASYNC_TOOL_NAMES` is now 80. 200 of 207 do real
  processing — the same 7 documented stubs as every prior pass.

- **Social OAuth login (Google).** `services/oauth_service.py` — real
  Authorization Code flow via `httpx` against Google's actual token/
  userinfo endpoints (the URLs are configurable specifically so tests can
  point them at a local stand-in HTTP server instead of the real Google,
  whose consent screen inherently needs a real browser + real user and
  can't be exercised by an automated suite). CSRF `state` is an
  HMAC-signed, time-boxed token — no server-side session storage added,
  matching this API's otherwise fully-stateless JWT auth. Identity model
  is email-as-identity: a Google sign-in either creates a new
  `password_hash=None` account or logs into an existing password-based
  account sharing the same email — no separate linked-accounts table.
  Gracefully disabled (not a 500) when `GOOGLE_CLIENT_ID`/
  `GOOGLE_CLIENT_SECRET` aren't set — `GET /api/auth/google/status` lets
  the frontend decide whether to show the "Sign in with Google" button at
  all (`AuthPanel.tsx`); `page.tsx` handles the `?oauth_token=`/
  `?oauth_error=` redirect back from `GET /api/auth/google/callback`. 27
  new tests (`test_oauth_service.py`, `test_oauth_routes.py`), including a
  full browser-shaped round trip through `/login` → fake Google →
  `/callback`.

- **Team/business-tier multi-seat accounts — first cut.**
  `models/organization.py`: `Organization` (a shared `credit_balance`
  pool) + `OrganizationMember` (role: owner/admin/member; invite-by-email
  with a signed, expiring token). `services/organization_service.py`
  owns the lifecycle (create → invite → accept → remove);
  `services/credit_service.py`'s `_billing_target()` is the one place
  that decides whether a tool run bills the user's own `credit_balance`
  or their org's shared pool, so `spend_credits`/`refund_credits` and
  every balance shown in an API response (`GET /api/credits/balance`,
  the `credit_balance` field on a job result) stay consistent about which
  account is authoritative. Referral bonuses always land on the
  individual, not the pool — earned by the person, not the team.
  `routes/organizations.py` (`POST /api/organizations`,
  `GET /api/organizations/me`, `POST /api/organizations/invite`,
  `POST /api/organizations/accept-invite`,
  `DELETE /api/organizations/members/{id}`); frontend has
  `components/OrganizationCard.tsx` and `page.tsx` picks up a team invite
  link's `?invite_token=` the same way it does `?ref=`/`?oauth_token=`.
  28 new tests across `test_organization_service.py`,
  `test_organization_routes.py`, and the shared-pool billing cases added
  to `test_credit_service.py`.
  **v1 simplification, stated rather than glossed over**: a user belongs
  to at most one organization — there's no "switch active team" concept.
  A real limitation for anyone who'd need to be on two teams, and the
  natural place a v2 would extend `OrganizationMember`.
  **Still open**: `POST /api/credits/purchase` only ever tops up a
  User's own balance — there's no "buy credits for the org" flow yet,
  so an org's shared pool can currently only be funded by manually
  setting `Organization.credit_balance` (e.g. via an admin script) until
  that purchase path is extended.

- **Deployment hardening — the docker-compose/nginx path had never
  actually been run against a real deploy, and it showed.** Found while
  preparing a step-by-step "what to do outside the code" launch guide and
  double-checking the infra it pointed at, rather than assuming the
  scaffold's own deploy instructions were correct:
  - `Dockerfile.web` built the frontend with no `NEXT_PUBLIC_API_URL` —
    Next.js only inlines `NEXT_PUBLIC_*` vars at `next build` time, so
    setting it as a *runtime* `environment:` on the `web` service (as
    docker-compose.yml did) had no effect at all; every real deploy would
    have silently shipped a frontend permanently pointed at
    `http://localhost:3001`. Fixed with a build `ARG`, threaded through
    `docker-compose.yml`'s `build.args`.
  - `.github/workflows/deploy.yml` ran `docker compose build`/`up -d`
    with no `--env-file ../../.env.production` — unlike the documented
    first manual deploy. Every CI-triggered redeploy after that first one
    would have silently dropped every production secret
    (`JWT_SECRET`, `DPO_COMPANY_TOKEN`, etc.) back to blank/default. Now
    passed consistently, with a loud failure if `.env.production` is
    missing rather than deploying with blank secrets.
  - `docker-compose.yml` defaulted `API_URL`/`NEXT_PUBLIC_API_URL` to
    `https://api.tweakhub.com`, a subdomain `nginx.conf` never actually
    sets up a server block for (it proxies `/api/` by path on the same
    domain as the frontend) — the shipped defaults would have pointed the
    app at a host with no DNS record, no TLS cert, and nothing listening.
    Defaults now match `nginx.conf`'s real single-domain routing.
  - Postgres/Redis/MinIO's S3 API were published to `0.0.0.0` with
    default credentials (`tweakhub`/`tweakhub`) — reachable from the
    public internet on a real VPS. Removed; nothing needs them published
    (containers reach each other by service name on the internal Compose
    network) — only MinIO's admin console stays published, bound to
    `127.0.0.1` for an SSH-tunnel-only reach.
  - `DATABASE_URL`/`REDIS_URL`/`POSTGRES_PASSWORD` were hardcoded
    literals in the `api`/`worker` services, ignoring whatever
    `.env.production` said — so the documented "fill in real secrets"
    step couldn't actually change the database password. Now properly
    interpolated, with a new `POSTGRES_PASSWORD` var; `DATABASE_URL`/
    `REDIS_URL` can still be set directly to point at an external managed
    instance instead of the bundled containers.
  - `minio:latest` was unpinned, so `docker compose pull` on every push
    could silently change what's running — pinned to a specific release.
  Verified with `docker compose config` (interpolation resolves
  correctly, including the nested `POSTGRES_PASSWORD` → `DATABASE_URL`
  and `BASE_URL` → `API_URL`/`NEXT_PUBLIC_API_URL` fallback chains, and
  an explicit override at any level takes priority as expected) — no
  Docker daemon in this sandbox to run a real `docker compose up`, so
  a real deploy against an actual VPS is still the first true end-to-end
  test of this path.

- **Direct bank transfer + logo placeholders.** `PaymentMethod.BANK_TRANSFER`
  already existed as an enum value but, before this, was silently routed
  through the same DPO `createToken` flow as every other method — DPO
  never actually surfaces TweakHub's own bank account, so in practice it
  did nothing useful. `services/credit_service.py`'s `initiate_purchase`
  now branches on it: no DPO call at all, just a `PENDING`
  `PaymentAttempt` and a human reference — `"TweakHub" + a zero-padded
  6-digit number` (e.g. `TweakHub000001`) — from a new
  `BankReferenceCounter` table (`models/bank_reference_counter.py`),
  incremented under a row lock rather than a Postgres `SEQUENCE` so the
  same migration and service code work against the SQLite db the test
  suite runs on. `services/payment_service.py`'s
  `generate_bank_transfer_invoice_pdf` renders the payee details — pay to
  **TweakHub (a subsidiary of OnPoint CRM)**, Standard Bank, account
  `10275365741` — and the reference as a standalone reportlab PDF, not
  routed through the `invoice_generator` tool (that's a paid, user-facing
  tool; this must never cost the customer credits). Since a plain EFT has
  no webhook, crediting the purchase needs a human: `User.is_admin` (no
  self-service grant path — set directly in the database on purpose) gates
  new `routes/admin.py` endpoints (`GET /api/admin/bank-transfers/pending`,
  `POST .../{id}/confirm`) and a new, unlinked `/admin` page
  (`app/admin/page.tsx`, reusing `AuthPanel` for sign-in since it's a
  separate page load with no access to the main page's in-memory token).
  Frontend: `CreditPackages.tsx` renders the new
  `BankTransferInstructions.tsx` panel instead of redirecting when
  `purchaseCredits()` comes back `payment_method: "bank_transfer"`
  (`lib/api.ts`'s `PurchaseResult` union), with a "Download as PDF" button
  that fetches the invoice as a `Blob` (the route needs the bearer token,
  which a plain `<a href>`/`window.open()` navigation can't attach — see
  the docstring on `api.getBankTransferInvoicePdf`). Separately, a
  `components/Logo.tsx` placeholder (dashed box, swap instructions in its
  own docstring) now sits in the main header, `/reset-password`,
  `/verify-email`, and on the bank-transfer invoice PDF itself, wherever
  the brand appears but no real logo asset exists yet.
  Verified: 10 new backend tests (`test_bank_transfer.py` — reference
  generation/uniqueness, the PDF's rendered text actually contains the
  reference/bank details, the full purchase → admin-list → confirm →
  credits-granted HTTP round trip, confirm is idempotent, 403 for a
  non-admin, 404 for another user's invoice or an unknown attempt id);
  full suite 344/344 passing. Migration (`cc6affc07954`) verified
  upgrade → downgrade → upgrade against both a real Postgres db and a
  throwaway SQLite one, and a zero-diff autogenerate check confirms the
  models match it exactly. Frontend: `next build` and `eslint .` both
  clean.
  **Still open**: no notification when a new bank-transfer purchase comes
  in — an admin has to check `/admin` themselves rather than being told;
  and, same pre-existing gap as the org-billing note above, a bank
  transfer (like every other method) can only ever top up a User's own
  balance, not an organization's shared pool.

## Should-have

- WhatsApp bot, SEO content pipeline — growth-strategy items from the
  master plan needing external accounts (Meta Business API) or
  content/marketing work respectively, not engineering; not started.

## Explicitly deferred by design

- ~~200 individual tool implementations.~~ **Done, and grown past it.**
  `services/tools_catalog.py` now has exactly 207 `ToolSpec` entries
  across all five categories (image 50, audio 42, video 41, pdf 34,
  document 40), reached across six data-only "Catalog expansion" passes
  (27, then 47, then 26, then 22, then 7, then 7 tools — see the entries
  above) — every single one independently verified against a real file
  before being catalogued, none of them new engine logic, all of them
  reusing the same handful of already-verified generic handlers. 200 of
  the 207 do real processing; the remaining 7 are documented stubs with
  a specific, investigated reason each (see `docs/engines.md`'s "Tools
  deliberately left as stubs" table — three of them were actually tried
  against LibreOffice/the available network egress and found broken or
  unreachable, not just left un-investigated). This catalog remains a
  valid growth surface for genuine new formats or use cases, but hitting
  a round number stopped being the point once 200 was reached — the
  sixth pass added three specific, justified gaps rather than
  combinatorial padding, and explicitly declined several padding-only
  options along the way (see that entry above).
