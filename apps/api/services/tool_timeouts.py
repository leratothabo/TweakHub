"""
app/services/tool_timeouts.py

Per-tool timeout lookup, used at two call sites: services/engines/
media_convert.py's _run_ffmpeg() (the subprocess-level timeout for the
ffmpeg call itself) and services/job_queue.py's enqueue_processing_job()
(RQ's job-level timeout, which has to cover DB/storage overhead around the
engine call too, not just the subprocess).

Before this module, both call sites used one blanket constant regardless
of which tool was running: _run_ffmpeg() hardcoded timeout=180 for every
video/audio ffmpeg invocation, and enqueue_processing_job() passed one
flat settings.job_timeout_seconds (900) for all of ASYNC_TOOL_NAMES. That
was safe but imprecise in both directions — a cheap stream-copy op like
video_mute (-c:v copy, no re-encode) got the same ceiling as a full
multi-input concat re-encode, and a genuinely large/slow job on the
document engine only had the flat default to lean on.

Lookup order for a tool name: explicit per-tool override (reasoning
documented inline below) -> category default -> engine default (job
timeout only) -> global default. Category/engine come from
services/tools_catalog.py's ToolSpec, so a new tool with no explicit
override here still gets a sane default automatically as long as its
category/engine is set correctly — no hand-maintained list to keep in
sync as the catalog grows toward 200.

Document-engine tools (document_convert.py: LibreOffice, Playwright,
tesseract) already set their own explicit subprocess-level timeouts
inline per operation (90/60/120s, tuned per binary — see that file) and
don't call through _run_ffmpeg at all, so get_subprocess_timeout_seconds()
below is only consulted by media_convert.py. get_job_timeout_seconds() is
consulted for every ASYNC_TOOL_NAMES tool (video-category *and*
document-engine), since that's the RQ-level ceiling regardless of engine.
"""
from __future__ import annotations

from services.tools_catalog import get_tool

# -- ffmpeg subprocess-level timeout (services/engines/media_convert.py) ---

DEFAULT_SUBPROCESS_TIMEOUT = 90
CATEGORY_SUBPROCESS_TIMEOUT = {
    "video": 300,
}
# Reasoning per override, not just a guessed number:
TOOL_SUBPROCESS_TIMEOUT_OVERRIDES = {
    # Stream-copy operations (-c copy / -c:v copy) don't re-encode
    # anything, so they finish in a small fraction of the video-category
    # default even on a large file. A shorter timeout here fails a
    # genuinely stuck ffmpeg process faster instead of waiting out the
    # full 300s for an operation that should be near-instant.
    "video_trim": 90,
    "video_mute": 90,
    "video_extract_audio": 120,  # decodes audio but leaves video untouched
    # Full re-encodes and multi-input concats are the genuinely slow end —
    # give them headroom above the category default rather than risk
    # truncating a real conversion on a large input.
    "video_compress": 420,
    "video_merge": 420,
    "video_watermark": 360,
    "subtitle_burn": 360,  # burns a filter over every frame, same cost class
    "video_to_gif": 240,  # palette generation pass + full re-encode to gif
}

# -- RQ job-level timeout (services/job_queue.py) --------------------------

DEFAULT_JOB_TIMEOUT = 300
CATEGORY_JOB_TIMEOUT = {
    "video": 480,
}
ENGINE_JOB_TIMEOUT = {
    # LibreOffice/Playwright process startup plus the conversion itself is
    # slower per-call than most single ffmpeg operations, even though
    # document-engine tools don't handle large binary media the way video
    # tools do.
    "document": 240,
}
TOOL_JOB_TIMEOUT_OVERRIDES = {
    "video_compress": 600,
    "video_merge": 600,
    "video_watermark": 540,
    "subtitle_burn": 540,
    "video_to_gif": 420,
    "ocr_extract": 420,  # tesseract runs once per rasterized page, in series
}


def get_subprocess_timeout_seconds(tool_name: str) -> int:
    """ffmpeg-call-level timeout for media_convert.py's _run_ffmpeg().
    Only meaningful for tools that actually go through ffmpeg (video/
    audio categories) — callers outside that engine don't need this."""
    if tool_name in TOOL_SUBPROCESS_TIMEOUT_OVERRIDES:
        return TOOL_SUBPROCESS_TIMEOUT_OVERRIDES[tool_name]
    spec = get_tool(tool_name)
    if spec and spec.category in CATEGORY_SUBPROCESS_TIMEOUT:
        return CATEGORY_SUBPROCESS_TIMEOUT[spec.category]
    return DEFAULT_SUBPROCESS_TIMEOUT


def get_job_timeout_seconds(tool_name: str) -> int:
    """RQ job-level timeout for job_queue.py's enqueue_processing_job().
    Applies to every ASYNC_TOOL_NAMES tool (video-category *and*
    document-engine), not just ffmpeg-backed ones."""
    if tool_name in TOOL_JOB_TIMEOUT_OVERRIDES:
        return TOOL_JOB_TIMEOUT_OVERRIDES[tool_name]
    spec = get_tool(tool_name)
    if spec:
        if spec.category in CATEGORY_JOB_TIMEOUT:
            return CATEGORY_JOB_TIMEOUT[spec.category]
        if spec.engine in ENGINE_JOB_TIMEOUT:
            return ENGINE_JOB_TIMEOUT[spec.engine]
    return DEFAULT_JOB_TIMEOUT
