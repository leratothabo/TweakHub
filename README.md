# TweakHub

200+ file processing tools (PDF, image, video, audio, document) for the
African market, with subscription and pay-as-you-go credit pricing via DPO
Group (card, mobile money, bank transfer across 21+ African countries).

The full architecture/business plan is in
[`docs/tweakhub-master-plan.md`](docs/tweakhub-master-plan.md) (also saved
to the TweakHub project doc). Start with [`docs/TODO.md`](docs/TODO.md) to
see what's real here versus what's still a stub.

## Repo layout

```
apps/
  web/            Next.js 16 + TypeScript frontend (App Router)
  api/             FastAPI (Python) backend — tools, credits, payments,
                   object storage, background job queue
  workers/         docs only — the real worker code lives in apps/api
                   (services/job_worker.py) since it needs the same
                   models/engines the API does; this is just where an
                   `rq worker` process's operational docs live
packages/
  avx-client/      vestigial — see the note at the top of each file. The
  convert-agent/   engines these were meant to front turned out not to be
  terra-pdf/       real projects and were replaced with local processing
                   (apps/api/services/engines/). There is a real job/
                   polling system now (apps/api/services/job_queue.py,
                   routes/jobs.py) — it just doesn't look anything like
                   avx-client's AvxJobStatus shape, so these stay purely
                   historical rather than "kept in case."
infrastructure/
  docker/          Dockerfile.api, Dockerfile.web, docker-compose.yml
  nginx/           reverse proxy config (HTTP; certbot upgrades it to HTTPS)
scripts/
  setup-truehost.sh   one-time VPS bootstrap
  deploy.sh           manual redeploy (mirrors the CI deploy job)
docs/
  tweakhub-master-plan.md   the original architecture/business plan
  licensing.md              MIT/Apache/AGPL/commercial notes per engine
  engines.md                integration status of each processing engine
  TODO.md                   what's stubbed vs. real
```

## Quick start (local dev)

**Backend:**

```bash
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # needed for html_to_pdf / markdown_to_pdf
cp ../../.env.example ../../.env   # then fill in DATABASE_URL etc.
uvicorn main:app --reload --port 3001
```

Visit `http://localhost:3001/docs` for the interactive API docs.

Most tools also need system binaries the Python deps don't bring with
them — LibreOffice, ffmpeg, poppler-utils, tesseract-ocr, qpdf (see
`docs/engines.md` for which tool needs which). `infrastructure/docker/
Dockerfile.api` installs all of them, so if you're not running the API
directly on your machine, Docker Compose (below) gets you the full set
with no extra steps. Running `apps/api` directly without them isn't
broken — tools that need a missing binary fail with a clear error from
that specific handler, everything else still works.

The API needs Postgres reachable at `DATABASE_URL` — easiest local option:

```bash
docker run -d --name tweakhub-pg -e POSTGRES_USER=tweakhub \
  -e POSTGRES_PASSWORD=tweakhub -e POSTGRES_DB=tweakhub -p 5432:5432 postgres:16-alpine
```

Then apply migrations (Alembic — see `apps/api/migrations/`):

```bash
alembic upgrade head
```

**Frontend:**

```bash
npm install        # installs the whole workspace (apps/web + packages/*)
npm run dev:web     # http://localhost:3000
```

The frontend reads `NEXT_PUBLIC_API_URL` (defaults to
`http://localhost:3001`). Sign up with a real email/password on the home
page — the API logs the verification email instead of sending it (no
provider is configured yet, see `docs/TODO.md`), so in dev, copy the
verification link out of the `uvicorn` server log and open it, or just set
`NODE_ENV=development` on the API to skip the verification requirement on
login entirely.

**Tests:**

```bash
npm run test:api    # pytest, 231 tests: credit pricing, tool routing, auth flow, real engine output, rate limiting, object storage, background jobs, Google OAuth, team/business accounts
npm run build:web   # verifies the frontend still compiles
```

Auth tests run against a throwaway SQLite file DB (see
`apps/api/tests/conftest.py`) so they don't need Postgres running. Engine
tests in `apps/api/tests/test_engines.py` run real generated files through
the real library/CLI tool for each handler — the ones that need a system
binary (LibreOffice, ffmpeg, poppler, tesseract, Playwright's Chromium)
skip cleanly if that binary isn't installed locally, rather than failing;
`.github/workflows/test.yml` installs the full toolchain so none of them
skip in CI. Rate-limiting tests (`test_rate_limiter.py`,
`test_rate_limiting_routes.py`) run against `fakeredis` instead of a real
Redis server, so they don't skip or need Redis running locally either.
Job-queue tests (`test_job_queue.py`) need a *real* Redis (RQ's registries
aren't reliably emulated by fakeredis) and skip cleanly without one — CI
runs a redis service so they never skip there; storage tests
(`test_storage_service.py`) exercise the S3 backend against a mocked S3
API (`moto`), not just the local one.

## Running a tool

`POST /api/tools/{tool_name}/process` (multipart form):

- `file` — the primary input
- `extra_files` (optional, repeatable) — for tools that combine multiple
  inputs: `pdf_merge`, `video_merge`, `audio_merge`, `pdf_compare`,
  `subtitle_burn`
- `options` (optional, JSON string) — tool-specific parameters, e.g.
  `{"angle": 180}` for `pdf_rotate`, `{"password": "..."}` for
  `pdf_protect`, `{"target_format": "webp"}` for `image_convert`. See
  `docs/engines.md` for what each tool reads.

Most tools resolve inline and respond `200` with a JSON body:
`status: "succeeded"`, a signed `download_url` good for
`SIGNED_URL_EXPIRES_SECONDS` (an hour by default), `credits_spent` /
`credit_balance`, and a `meta` object with any tool-specific metadata
(page counts, compression ratios, etc.). Video-category tools and
everything routed through the `document` engine (LibreOffice/Playwright/
OCR — see `docs/engines.md`'s `ASYNC_TOOL_NAMES`) instead respond `202`
with `status: "pending"` and a `job_id` — poll `GET /api/jobs/{job_id}`
(same response shape) until status leaves pending/processing.
`GET /api/jobs` lists your own recent runs. The frontend's `api.processTool()`
+ `api.pollJob()` (`apps/web/lib/api.ts`) do this automatically.

## Rate limiting

Redis-backed, via `apps/api/services/rate_limiter.py` (fixed window,
fails open if Redis is down rather than blocking every request). Covers:

- `/api/auth/signup`, `/api/auth/login`, `/api/auth/request-password-reset`
  — per client IP, limits in `.env.example` (`RATE_LIMIT_SIGNUP_PER_HOUR`
  etc.)
- `/api/tools/{tool}/process` — per user, limit chosen by plan tier
  (`RATE_LIMIT_FREE_PER_HOUR` / `_PRO_` / `_BUSINESS_`; enterprise is
  unmetered)
- `/api/payments/callback` — per client IP
  (`RATE_LIMIT_PAYMENTS_CALLBACK_PER_HOUR`), plus an optional
  `DPO_WEBHOOK_IP_ALLOWLIST` (disabled by default — see `docs/TODO.md` for
  why nothing is pre-filled and what to do before launch)

A request over the limit gets `429` with a `Retry-After` header.

## Object storage & background jobs

- **Storage** (`apps/api/services/storage_service.py`): `STORAGE_BACKEND=local`
  (default) writes under `STORAGE_LOCAL_DIR` and needs nothing else — fine
  for a single-VPS deploy where the API and worker share a disk (Docker
  Compose mounts the same `./storage_outputs` volume into both). Switch to
  `STORAGE_BACKEND=s3` for real AWS S3 or self-hosted MinIO (Docker
  Compose brings up a `minio` service, matching the `S3_*` defaults in
  `.env.example`) once there's more than one API/worker replica, since
  each replica only sees its own local disk.
- **Retention**: neither backend expires objects on its own —
  `apps/api/scripts/cleanup_expired_outputs.py` enforces
  `FILE_RETENTION_HOURS` (default 48) and needs a cron entry on the VPS
  (see that file's docstring for the exact line).
- **Background jobs** (`apps/workers/README.md`): `rq worker
  tweakhub-tools --url $REDIS_URL`, run as the `worker` service in Docker
  Compose (same image as `api`, different command — scale it independently
  for more parallel jobs). Only `ASYNC_TOOL_NAMES` tools go through it;
  see "Running a tool" above.

## Running the full stack with Docker

```bash
cp .env.example .env.production   # fill in real secrets
cd infrastructure/docker
docker compose --env-file ../../.env.production up -d --build
```

This brings up Postgres, Redis, MinIO, the API, a job-queue worker, the
web app, and an nginx reverse proxy on ports 80/443. The API container
runs `alembic upgrade head` automatically on startup
(`apps/api/docker-entrypoint.sh`) before it starts serving — the worker
container shares the same entrypoint script but skips migrations (only
the API runs those), so migrations are never missed on deploy and never
raced by two containers starting at once.

## Database migrations

Schema lives in `apps/api/models/`; migrations live in
`apps/api/migrations/versions/`. After changing a model:

```bash
cd apps/api
alembic revision --autogenerate -m "describe the change"
# review the generated file — autogenerate misses renames and some
# constraint changes, so check it before committing
alembic upgrade head   # apply it locally to confirm it runs cleanly
```

## Deploying to Truehost

1. Provision a Truehost (truehost.co.za) Cloud VPS 2 (2 vCPU / 4 GB /
   100 GB SSD / 10 TB bandwidth, ~R140/mo — the closest match to this
   project's original KVM2 target spec; see docs/tweakhub-master-plan.md
   for why), and point `tweakhub.co.za` / `www.tweakhub.co.za` at its IP.
   Note: truehost.co.za's own hosting page states it has no physical
   servers inside South Africa — VPS instances run out of its
   Europe/USA data centers, so budget for that latency rather than the
   in-country latency the original Truehost-Kenya plan assumed.
2. SSH in and run `scripts/setup-truehost.sh` once (installs Docker,
   clones the repo, prints the remaining manual steps: `.env.production`,
   first `docker compose up`, and `certbot` for SSL).
3. Add `TRUEHOST_HOST`, `TRUEHOST_USERNAME`, `TRUEHOST_PASSWORD`,
   `TRUEHOST_PORT` as GitHub Actions secrets.
4. From then on, every push to `main` runs `.github/workflows/deploy.yml`:
   it runs the test suite, then SSHs into the VPS, pulls `main`, and
   rebuilds the Docker Compose stack in place.

## Credit pricing

Base cost per tool lives in `apps/api/services/tools_catalog.py` (one
source of truth also used for routing to the right engine). File-size
multipliers (1.5x over 50MB, 2x over 100MB) are applied in
`apps/api/services/credit_service.py::get_credit_cost` — see
`apps/api/tests/test_credit_service.py` for the exact numbers.

## Before you add tool #99

`docs/engines.md` explains which of the five engines (`pdf_manipulate`,
`pdf_generate`, `media_convert`, `document_convert`, `pdf_editor`) each
new tool should route through, what each one is actually built on
(pypdf/pikepdf/reportlab, Pillow, ffmpeg/poppler/LibreOffice/Playwright),
and the handful of tools that were tried and found not to work rather
than just left unimplemented. `docs/licensing.md` explains why iText and
Ghostscript are deliberately not used anywhere in this codebase — read it
before reaching for either to fill a gap the other engines don't cover.
