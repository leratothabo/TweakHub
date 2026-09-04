from __future__ import annotations

from typing import Any, BinaryIO

from .base import Engine, EngineResult


class PDFEditorEngine(Engine):
    """
    PDFEditor (MIT license) is a browser-based React component — annotation,
    highlighting, shapes, form-filling all happen client-side in apps/web.
    This backend engine exists only for operations that need to persist an
    edited document server-side (e.g. "flatten and save my annotated PDF"),
    which the frontend posts here once the user is done editing in-browser.
    """

    name = "pdf_editor"

    def process(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        operation = options.get("operation")  # e.g. "flatten"
        if operation != "flatten":
            return EngineResult(
                ok=False,
                error="PDFEditorEngine only supports server-side flatten; "
                "all other editing happens client-side in apps/web.",
            )

        # TODO: implement flatten via PDFBox or pypdf once the annotated
        # PDF + annotation layer contract with the frontend is finalized.
        return EngineResult(ok=False, error="flatten not yet implemented")
