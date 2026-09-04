"""
TweakHub API entrypoint.

Local dev:  uvicorn main:app --reload --port 3001
Docker:     see infrastructure/docker/Dockerfile.api
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from routes import admin, auth, credits, files, jobs, organizations, payments, tools

settings = get_settings()

app = FastAPI(
    title="TweakHub API",
    description="200+ file processing tools — PDF, image, video, audio, document.",
    version="0.1.0",
)

# Starlette makes the most-recently-added middleware the outermost layer
# (first to see the request, last to see the response), so CORS is added
# last — the conventional place for it, so it can short-circuit preflight
# OPTIONS requests before anything else runs and so its headers land on
# every response, error responses included. Security headers and access
# logging sit just inside it.
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.base_url] if settings.node_env == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tools.router)
app.include_router(jobs.router)
app.include_router(credits.router)
app.include_router(payments.router)
app.include_router(files.router)
app.include_router(organizations.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.node_env}
