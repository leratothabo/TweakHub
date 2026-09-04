import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.tools_catalog import TOOLS, get_tool, list_tools  # noqa: E402


def test_catalog_has_no_duplicate_names():
    names = [t.name for t in TOOLS]
    assert len(names) == len(set(names))


def test_catalog_covers_all_five_categories():
    categories = {t.category for t in TOOLS}
    assert categories == {"pdf", "image", "video", "audio", "document"}


def test_list_tools_filters_by_category():
    pdf_tools = list_tools("pdf")
    assert all(t.category == "pdf" for t in pdf_tools)
    assert len(pdf_tools) > 0


def test_get_tool_returns_none_for_unknown():
    assert get_tool("nonexistent") is None
