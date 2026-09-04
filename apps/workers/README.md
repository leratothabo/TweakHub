# apps/workers

The background job queue from `docs/TODO.md` is real now — this directory
holds no code of its own because there's none needed: the actual task
(`apps/api/services/job_worker.py::run_processing_job`) lives inside
`apps/api` since it needs the same models, engines, and config the API
does, and RQ's own CLI is the worker process. This directory is just
where that process's operational docs live.

## Running a worker

```bash
cd apps/api
source .venv/bin/activate
rq worker tweakhub-tools --url "$REDIS_URL"
```

`tweakhub-tools` is the default queue name (`JOB_QUEUE_NAME` in
`.env.example`); `$REDIS_URL` needs to be the same Redis
`apps/api/services/job_queue.py` enqueues onto (`JOB_QUEUE_REDIS_URL` if
set, otherwise `REDIS_URL` — same instance rate limiting uses, by
default). Run more than one `rq worker` process (any count, any host with
network access to Redis and the same job code) to process jobs in
parallel — RQ workers are stateless and don't coordinate with each other
beyond the shared queue.

In Docker Compose, this is the `worker` service in
`infrastructure/docker/docker-compose.yml` — same image as the API
(`Dockerfile.api`), different command.

## Which tools actually go through here

Not all 70+ tools — most process synchronously, inline in the
`/api/tools/{tool}/process` request, same as before. Only the ones
`routes/tools.py`'s `ASYNC_TOOL_NAMES` set marks as async — every
`category == "video"` tool (ffmpeg on real video files is slow) and every
tool routed to the `document` engine (LibreOffice headless and
Playwright+Chromium subprocesses, plus OCR, all meaningfully slower than
the in-memory pypdf/pikepdf/Pillow operations). See `docs/engines.md` for
the exact list and `docs/TODO.md` for why this split exists instead of
making everything async (most tools finish in well under a second — an
async round-trip would be pure latency for those, not a fix for anything).

## What a worker needs to run correctly

Everything `Dockerfile.api` already installs — LibreOffice, ffmpeg,
poppler-utils, tesseract-ocr, qpdf, Playwright's Chromium — since the
worker runs the exact same engine code the sync path does. It also needs
whatever `STORAGE_BACKEND` is configured (local: a filesystem it shares
with the API container, e.g. the same Docker volume; s3: just network
access and the `S3_*` credentials, no shared filesystem required — see
`services/storage_service.py`).
