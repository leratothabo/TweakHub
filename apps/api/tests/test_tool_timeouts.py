"""
Tests for services/tool_timeouts.py's lookup functions — pure functions,
no fixtures needed. Verifies the override -> category -> engine -> default
precedence and cross-checks a couple of the wired-in call sites
(media_convert.py's _run_ffmpeg, job_queue.py's enqueue_processing_job)
actually use it rather than a hardcoded constant.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.tool_timeouts import (  # noqa: E402
    DEFAULT_JOB_TIMEOUT,
    DEFAULT_SUBPROCESS_TIMEOUT,
    get_job_timeout_seconds,
    get_subprocess_timeout_seconds,
)


def test_subprocess_timeout_explicit_override_wins():
    # video_compress is both a video-category tool (would get 300 from the
    # category default) and has its own override (420) — override must win.
    assert get_subprocess_timeout_seconds("video_compress") == 420


def test_subprocess_timeout_falls_back_to_category_default():
    # video_resize has no explicit override, so it should get the
    # video-category default (300), not the global default (90).
    assert get_subprocess_timeout_seconds("video_resize") == 300


def test_subprocess_timeout_stream_copy_override_is_shorter_than_category():
    # video_mute is a stream-copy op (no re-encode) — its override should
    # be shorter than the video-category default, not longer.
    assert get_subprocess_timeout_seconds("video_mute") == 90
    assert get_subprocess_timeout_seconds("video_mute") < get_subprocess_timeout_seconds("video_resize")


def test_subprocess_timeout_unknown_tool_gets_global_default():
    assert get_subprocess_timeout_seconds("not_a_real_tool") == DEFAULT_SUBPROCESS_TIMEOUT


def test_subprocess_timeout_non_video_tool_gets_global_default():
    # audio_normalize has no override and audio isn't in
    # CATEGORY_SUBPROCESS_TIMEOUT, so it should fall all the way to the
    # global default.
    assert get_subprocess_timeout_seconds("audio_normalize") == DEFAULT_SUBPROCESS_TIMEOUT


def test_job_timeout_explicit_override_wins():
    assert get_job_timeout_seconds("subtitle_burn") == 540


def test_job_timeout_falls_back_to_category_default():
    # video_resize: no override, falls to the video-category job default (480).
    assert get_job_timeout_seconds("video_resize") == 480


def test_job_timeout_falls_back_to_engine_default_for_document_tools():
    # html_to_pdf is a document-engine async tool with no category or
    # per-tool override — should land on the document engine default (240),
    # not the global default (300) or a video-category value.
    assert get_job_timeout_seconds("html_to_pdf") == 240


def test_job_timeout_unknown_tool_gets_global_default():
    assert get_job_timeout_seconds("not_a_real_tool") == DEFAULT_JOB_TIMEOUT


def test_job_timeout_at_least_covers_matching_subprocess_timeout():
    # Sanity check on the two tables' relationship: for every tool that
    # appears in both timeout tables, the RQ-level ceiling must be >= the
    # ffmpeg-subprocess-level ceiling plus some headroom, or a legitimately
    # slow-but-successful ffmpeg run could get killed by RQ before it even
    # finishes, turning a working conversion into a false "job timed out."
    from services.tool_timeouts import TOOL_SUBPROCESS_TIMEOUT_OVERRIDES

    for tool_name, subprocess_timeout in TOOL_SUBPROCESS_TIMEOUT_OVERRIDES.items():
        job_timeout = get_job_timeout_seconds(tool_name)
        assert job_timeout > subprocess_timeout, (
            f"{tool_name}: job timeout ({job_timeout}s) must exceed its ffmpeg "
            f"subprocess timeout ({subprocess_timeout}s) with headroom for DB/"
            f"storage overhead around the call"
        )
