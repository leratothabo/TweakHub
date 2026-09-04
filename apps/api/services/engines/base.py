"""
Common interface every processing engine wraps behind. Each engine is a
thin HTTP client to an external microservice (AVX, ConvertAgent, TerraPDF)
or a local library call (php-pdf, PDFEditor). Keeping this interface small
means ToolRouter never needs to know which engine is behind a tool name.

NOTE: the concrete engines below (AVXEngine, ConvertAgentEngine, ...) are
scaffolds. They validate config and shape the request/response contract,
but the actual HTTP calls are stubbed with clear TODOs — wire each one up
to its real service URL (see .env.example) once that service is deployed.
Before wiring TerraPDFEngine or any iText-backed path to production,
resolve the AGPL-vs-commercial-license question flagged in
docs/licensing.md.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, BinaryIO


@dataclass
class EngineResult:
    ok: bool
    output_path: str | None = None
    output_bytes: bytes | None = None
    content_type: str | None = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class Engine(ABC):
    """Base class for all conversion/manipulation engines."""

    name: str = "base"

    @abstractmethod
    def process(self, input_data: BinaryIO, options: dict[str, Any]) -> EngineResult:
        """Run this engine against an input file-like object and return a result."""
        raise NotImplementedError

    def health_check(self) -> bool:
        """Override in subclasses that wrap a remote service."""
        return True
