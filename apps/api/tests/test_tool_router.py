import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.tool_router import ToolRouter, UnknownToolError  # noqa: E402


def test_unknown_tool_raises():
    router = ToolRouter()
    with pytest.raises(UnknownToolError):
        router.get_tool_spec("does_not_exist")


def test_known_tool_resolves_to_expected_engine():
    router = ToolRouter()
    assert router.get_tool_spec("pdf_merge").engine == "manipulate"
    assert router.get_tool_spec("pdf_to_word").engine == "document"
    assert router.get_tool_spec("video_compress").engine == "convert"
    assert router.get_tool_spec("invoice_generator").engine == "generate"


def test_route_tool_passes_tool_name_and_dispatches():
    """route_tool should reach the right engine's handler table by tool_name,
    not just return a generic 'not configured' stub (that was true of the old
    AVX/ConvertAgent/TerraPDF placeholder engines — real engines dispatch by
    tool_name and either do the work or fail on the actual input)."""
    router = ToolRouter()
    # Garbage bytes aren't a valid image — Pillow should raise, and the
    # engine should turn that into a clean ok=False rather than a 500.
    result = router.route_tool("image_convert", io.BytesIO(b"not a real image"), {"target_format": "png"})
    assert result.ok is False
    assert "image_convert failed" in result.error


def test_route_tool_unknown_engine_handler_is_clean():
    router = ToolRouter()
    # engine="edit" tools are still stubs (client-side annotation is out of
    # scope for this pass — see services/engines/pdf_editor_engine.py).
    result = router.route_tool("pdf_edit", io.BytesIO(b"whatever"), {})
    assert result.ok is False


def test_caller_supplied_options_cannot_override_tool_name_or_engine_op():
    """Regression test for a real bug: routes/tools.py passes the raw,
    unvalidated `options` JSON request field straight through as
    route_tool()'s `options` argument. If that dict merged in AFTER the
    internal tool_name/engine_op keys (the original bug — a dict literal
    with the internal keys spread first, then `**options` last), a caller
    could post e.g. options={"tool_name": "video_compress"} against a
    cheap, synchronous, low-credit tool sharing MediaConvertEngine and
    have the engine actually run — and get billed, timed-out, and
    sync-vs-async routed as — a completely different, far more expensive
    tool (routes/tools.py prices/routes by the URL's tool_name, but the
    engine dispatches on merged_options["tool_name"]). Confirm the
    merged options route_tool() hands to the engine always reflect the
    tool actually being billed, never a caller override."""
    router = ToolRouter()
    from PIL import Image

    img = Image.new("RGB", (20, 20), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    # image_crop and video_compress both live on MediaConvertEngine
    # (engine="convert"), so an override would actually reach a real,
    # different handler rather than just erroring on an unknown engine.
    assert router.get_tool_spec("image_crop").engine == router.get_tool_spec("video_compress").engine == "convert"

    result = router.route_tool(
        "image_crop",
        io.BytesIO(buf.getvalue()),
        {"tool_name": "video_compress", "engine_op": "video_compress_op", "crop_box": "0,0,10,10"},
    )
    # If the override had worked, MediaConvertEngine would have tried to
    # run video_compress's ffmpeg handler against PNG bytes and failed
    # loudly and differently (or, worse, "succeeded" at running the
    # wrong, pricier tool). Getting a clean image_crop result back proves
    # tool_name/engine_op won the merge, not the caller-supplied values.
    assert result.ok, result.error
    assert result.content_type == "image/png"


def test_named_format_pair_gets_target_format_from_engine_op_alone():
    """png_to_jpg (and the rest of tools_catalog.py's "specific named
    pair" tools — see its module docstring) never requires the caller to
    pass target_format: engine_op="target_format=jpg" on the ToolSpec is
    what supplies it, via route_tool()'s engine_op auto-population. This
    is the one thing test_engines.py's direct engine.process() calls
    (which pass target_format explicitly) don't cover — the actual
    end-to-end wiring a real client request relies on."""
    from PIL import Image

    router = ToolRouter()
    img = Image.new("RGB", (20, 20), (200, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    # Note: no target_format in options — only what png_to_jpg's catalog
    # entry supplies via engine_op.
    result = router.route_tool("png_to_jpg", io.BytesIO(buf.getvalue()), {})
    assert result.ok, result.error
    assert result.content_type == "image/jpeg"
