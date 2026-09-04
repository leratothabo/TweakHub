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
