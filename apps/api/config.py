"""
Central settings for the TweakHub API, loaded from environment variables.
See ../../.env.example for the full list of variables and defaults.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    node_env: str = "development"
    base_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:3001"

    database_url: str = "postgresql://tweakhub:tweakhub@localhost:5432/tweakhub"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_expires_in: str = "7d"

    dpo_company_token: str = ""
    dpo_service_type: str = ""
    dpo_api_base_url: str = "https://secure.dpogroup.com"

    # -- Payments: Paystack (https://paystack.com/docs/api) --
    # Backend-only plumbing so far (services/payment_service.py's
    # initialize_paystack_transaction/verify_paystack_transaction, routes/
    # payments.py's /api/payments/paystack/* routes) — not yet wired into
    # credit_service.initiate_purchase() or the PaymentMethod enum
    # alongside DPO; that's a separate decision. paystack_secret_key is
    # the sk_... key and must only ever be read server-side, same as
    # dpo_company_token above — never send it to the Next.js frontend.
    # The pk_... publishable key (safe to expose client-side, e.g. for
    # @paystack/inline-js) isn't a backend setting at all — it belongs in
    # apps/web's NEXT_PUBLIC_* env vars if/when a checkout UI is built.
    paystack_secret_key: str = ""
    paystack_base_url: str = "https://api.paystack.co"

    max_upload_mb_free: int = 10
    max_upload_mb_pro: int = 100
    max_upload_mb_business: int = 500
    file_retention_hours: int = 48
    upload_dir: str = "./uploads"

    # -- Object storage for processed outputs (services/storage_service.py) --
    # "local" writes under storage_local_dir and serves files back through
    # a signed-URL download route in routes/files.py — no cloud account
    # needed for local dev or a single-VPS deploy. "s3" talks to any
    # S3-compatible API via boto3 (real AWS S3, or self-hosted MinIO on the
    # same VPS — set s3_endpoint_url for MinIO, leave it empty for AWS).
    storage_backend: str = "local"
    storage_local_dir: str = "./storage_outputs"
    signed_url_expires_seconds: int = 3600
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    # AWS S3 supports this with zero extra setup (SSE-S3, S3-managed keys)
    # so it's on by default for the s3 backend. Self-hosted MinIO needs its
    # own encryption/KMS configured before it will accept this parameter —
    # not something this codebase can verify from here (see
    # storage_service.py's module docstring) — so a MinIO deployment that
    # hasn't set that up should set this to "" to disable it rather than
    # have every save() fail.
    s3_server_side_encryption: str = "AES256"
    # Encrypts objects client-side before they touch disk (Fernet/AES128 —
    # see storage_service.py). Empty (the default) derives the key from
    # jwt_secret so encryption is on out of the box with no extra config;
    # set a dedicated value here in production so rotating jwt_secret
    # doesn't also make every previously-stored file undecryptable.
    storage_encryption_key: str = ""

    # -- Background job queue (services/job_queue.py, services/job_worker.py) --
    # RQ, on the same Redis instance by default — set this separately only
    # if the job queue should live on a different Redis than caching/rate
    # limiting (e.g. to isolate queue memory pressure from rate-limit keys).
    job_queue_redis_url: str = ""
    job_queue_name: str = "tweakhub-tools"
    job_timeout_seconds: int = 900
    # RQ's own escape hatch for running enqueued jobs in-process instead of
    # handing them to a separate `rq worker` — true only in tests, so the
    # whole enqueue -> job_worker.run_processing_job path is exercised for
    # real without needing a worker process alongside the test run.
    job_queue_synchronous: bool = False

    # Per-plan hourly limits on /api/tools/{tool}/process, keyed by user id.
    # ENTERPRISE has no entry in rate_limiter.py's plan map at all (treated
    # as unlimited), so it isn't listed here.
    rate_limit_free_per_hour: int = 100
    rate_limit_pro_per_hour: int = 1000
    rate_limit_business_per_hour: int = 5000

    # Unauthenticated-endpoint limits, keyed by client IP.
    rate_limit_signup_per_hour: int = 5
    rate_limit_login_per_hour: int = 20
    rate_limit_password_reset_per_hour: int = 5
    rate_limit_payments_callback_per_hour: int = 60

    # Comma-separated IPs/CIDRs (e.g. "41.79.85.0/24,196.216.192.10") that
    # DPO's payment callback is allowed to arrive from. Empty (the default)
    # disables the check — DPO does not publish a fixed, verified webhook
    # IP range in a place this codebase can cite, so hardcoding one would
    # be a guess dressed up as a fact (see docs/engines.md's AVX/
    # ConvertAgent/TerraPDF postmortem for why that's a bad habit here).
    # Get the real ranges from DPO support before launch and set this in
    # production; see docs/TODO.md.
    dpo_webhook_ip_allowlist: str = ""

    # -- Transactional email (services/email_service.py) --
    # "console" (the default) just logs the email — nothing to configure,
    # and every verification/reset link stays visible in the server log
    # for local dev, same behavior as before this setting existed. "smtp"
    # sends for real via smtplib/STARTTLS — set at minimum smtp_host; this
    # works with SendGrid/Postmark/SES's SMTP relays or a plain Gmail/
    # Workspace account, not just a dedicated ESP.
    email_backend: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_address: str = "noreply@tweakhub.com"

    # -- Referral / bonus credits (services/auth_service.py) --
    # Granted once per referral, when the invitee verifies their email —
    # not at signup — so a burst of throwaway unverified signups can't be
    # used to farm free credits for either side.
    referral_bonus_credits_invitee: int = 25
    referral_bonus_credits_referrer: int = 50

    # -- Google OAuth (services/oauth_service.py) --
    # Gracefully disabled — not a 500 — when client_id/secret aren't set:
    # GET /api/auth/google/status reports {"enabled": false} and
    # GET /api/auth/google/login returns 501. No separate feature flag.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Empty derives redirect_uri from api_url at request time
    # (api_url + "/api/auth/google/callback").
    google_redirect_uri: str = ""
    # Configurable so tests can point these at a local stand-in HTTP
    # server instead of the real Google — Google's actual consent screen
    # needs a real user in a real browser, so it can't be exercised
    # end-to-end by an automated suite (see oauth_service.py's docstring).
    # Defaults are the real Google OAuth2 endpoints.
    google_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_userinfo_url: str = "https://www.googleapis.com/oauth2/v3/userinfo"


@lru_cache
def get_settings() -> Settings:
    return Settings()
