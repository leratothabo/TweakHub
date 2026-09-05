# Running TweakHub locally (VS Code / Windows)

This is the "get it running on my own machine" runbook — for the actual
deploy target (Truehost VPS via Docker Compose), see
`infrastructure/docker/` and `.github/workflows/deploy.yml` instead. This
doc covers running the two dev servers directly, the way you'd work on
the code day to day.

## Prerequisites

Check what you already have (open a terminal — PowerShell is fine — and
run each):

```
python --version     # need 3.11+
node --version        # need 20+
npm --version
git --version
psql --version         # PostgreSQL client — need Postgres 14+ running
redis-cli --version    # or see the Redis note below
```

If Python/Node/git are missing, install them from python.org /
nodejs.org / git-scm.com, or via `winget install Python.Python.3.11`,
`winget install OpenJS.NodeJS.LTS`, `winget install Git.Git`.

**PostgreSQL**: `winget install PostgreSQL.PostgreSQL` (or use an
existing install/Docker container). Then create the app's role and
database once:

```
psql -U postgres -c "CREATE ROLE tweakhub WITH LOGIN PASSWORD 'tweakhub' SUPERUSER;"
psql -U postgres -c "CREATE DATABASE tweakhub OWNER tweakhub;"
```

**Redis**: Redis itself doesn't officially support Windows. Easiest
options, pick one:
- Docker Desktop, if you have it: `docker run -d -p 6379:6379 redis:7-alpine`
- [Memurai](https://www.memurai.com/) — a Redis-compatible Windows service
- WSL2 with Redis installed inside it, forwarded to `localhost:6379`

The app degrades gracefully without Redis for some things (rate limiting
fails open), but the background job queue (video-category and
document-engine tools — see `docs/engines.md`'s `ASYNC_TOOL_NAMES`) needs
a real Redis to actually process anything.

**Optional, for the tools themselves to work** (not needed just to get
the servers to boot): `ffmpeg`, `poppler` (`pdftoppm`), `LibreOffice`,
and `tesseract` are what the engines actually shell out to for
video/audio, pdf-to-image, document-format, and OCR conversions
respectively (see `docs/engines.md`). Without them installed and on
`PATH`, the app runs fine and pure-Python tools (most PDF manipulation,
image conversion) work, but anything routed through those engines will
error. Install via `winget install Gyan.FFmpeg`, and LibreOffice/
poppler/tesseract from their own installers, if you want the full
catalog working locally.

## 1. Open the project

In VS Code: **File → Open Folder** → the `tweakhub` folder you already
have checked out. Open two integrated terminals (the split-terminal
button, or `` Ctrl+Shift+` `` twice) — one for the backend, one for the
frontend.

## 2. Backend (`apps/api`)

```powershell
cd apps\api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\..\.env.example .env
```

Edit the new `apps\api\.env`:
- `JWT_SECRET` — any long random string
- `DATABASE_URL`/`REDIS_URL` — ship commented out in `.env.example` on
  purpose (see the comment above them — the same file also becomes
  `.env.production` for the Docker Compose deploy, where a literal value
  here breaks container-to-container networking). Leave them commented
  out for local dev too, once you've run the `psql` commands above and
  Redis is running: `apps/api/config.py`'s `Settings` class already
  defaults both to `postgresql://tweakhub:tweakhub@localhost:5432/tweakhub`
  and `redis://localhost:6379/0`, so an absent env var resolves to the
  same value as an explicit one would.
- Everything else (DPO keys, SMTP, Google OAuth) can stay blank for local
  dev — those features gracefully no-op without credentials (see each
  setting's comment in `apps/api/config.py`)

Then:

```powershell
alembic upgrade head
uvicorn main:app --reload --port 3001
```

Leave this running. `GET http://localhost:3001/health` should return
`{"status": "ok", ...}`.

## 3. Frontend (`apps/web`)

In the second terminal:

```powershell
cd apps\web
npm install
```

Create `apps\web\.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:3001
```

Then:

```powershell
npm run dev
```

## 4. Open it

`http://localhost:3000` in your browser. Sign up an account (email
verification just logs the link to the backend terminal — `EMAIL_BACKEND
=console` is the default — copy the link from there rather than waiting
on a real email), then the tool catalog, credit purchase flow (including
the new bank-transfer instructions), and everything else should be live.

To reach the admin page (`/admin`) for confirming bank-transfer
payments, set `is_admin` on your own row directly in Postgres once
you've signed up:

```
psql -U tweakhub -d tweakhub -c "UPDATE users SET is_admin = true WHERE email = 'you@example.com';"
```
