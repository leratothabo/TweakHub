"""
app/services/tool_router.py

Dispatches a tool_name (from services.tools_catalog) to the engine that
implements it, and hands back a normalized EngineResult. This replaces the
if/elif sketch from the original plan with a lookup-driven router so
adding tool #201 never means touching this file.
"""
from __future__ import annotations

from typing import Any, BinaryIO

from .engines import (
    DocumentConvertEngine,
    Engine,
    EngineResult,
    MediaConvertEngine,
    PDFEditorEngine,
    PdfGenerateEngine,
    PdfManipulateEngine,
)
from .tools_catalog import ToolSpec, get_tool


class UnknownToolError(ValueError):
    pass


class ToolRouter:
    def __init__(self) -> None:
        self.engines: dict[str, Engine] = {
            "convert": MediaConvertEngine(),
            "document": DocumentConvertEngine(),
            "generate": PdfGenerateEngine(),
            "manipulate": PdfManipulateEngine(),
            "edit": PDFEditorEngine(),
        }

    def get_tool_spec(self, tool_name: str) -> ToolSpec:
        spec = get_tool(tool_name)
        if spec is None:
            raise UnknownToolError(f"Unknown tool: {tool_name}")
        return spec

    def route_tool(
        self, tool_name: str, input_data: BinaryIO, options: dict[str, Any] | None = None
    ) -> EngineResult:
        spec = self.get_tool_spec(tool_name)
        engine = self.engines.get(spec.engine)
        if engine is None:
            return EngineResult(ok=False, error=f"No engine registered for '{spec.engine}'")

        # tool_name is the unambiguous key engines dispatch on internally
        # (each engine keeps a {tool_name: handler} table) — engine_op and
        # the derived keys below exist as a convenience for engines that
        # only need "what operation" without caring which specific tool
        # asked for it (e.g. GenerateEngine only cares about `template`).
        #
        # `tool_name`/`engine_op` are spread LAST so they can never be
        # overridden by caller-supplied `options` (routes/tools.py passes
        # the raw, unvalidated JSON `options` request field straight
        # through as `options` here). Getting the spread order backwards
        # let a request post e.g. options={"tool_name": "video_compress"}
        # against a cheap, synchronous, low-credit tool sharing the same
        # engine and have the engine actually run — and get billed/
        # timed-out/routed sync-vs-async as — a completely different,
        # far more expensive tool. `tool_name` also drives per-tool
        # subprocess timeouts (see media_convert.py's uses of
        # get_subprocess_timeout_seconds(options.get("tool_name"))), so an
        # override didn't just bypass pricing, it could also run
        # expensive work under a cheaper tool's timeout budget.
        merged_options = {**(options or {}), "tool_name": tool_name, "engine_op": spec.engine_op}
        if spec.engine == "convert" and "=" in spec.engine_op:
            key, _, value = spec.engine_op.partition("=")
            merged_options.setdefault(key, value)
        elif spec.engine == "convert":
            merged_options.setdefault("target_format", merged_options.get("target_format"))
        elif spec.engine == "document":
            merged_options.setdefault("conversion_pair", spec.engine_op)
        elif spec.engine == "generate":
            merged_options.setdefault("template", spec.engine_op)
        elif spec.engine == "manipulate":
            merged_options.setdefault("operation", spec.engine_op)
        elif spec.engine == "edit":
            merged_options.setdefault("operation", spec.engine_op)

        return engine.process(input_data, merged_options)
