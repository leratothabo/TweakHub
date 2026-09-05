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
    # Only meaningful when ok=False. Whether the credits spent on this run
    # should be refunded — True (the default) for anything that looks like
    # TweakHub's own fault (an engine crash, a missing dependency, a
    # subprocess failing for reasons unrelated to the input), False for a
    # failure caused by the input/options the user chose to send (wrong
    # password, a corrupted/unparseable file, an unsupported format,
    # invalid or missing options, a missing file in a multi-file op). The
    # default of True preserves the pre-existing "always refund on
    # failure" behavior for every site that hasn't been reviewed and
    # explicitly marked otherwise. See routes/tools.py and
    # services/job_worker.py's _fail_job, the two call sites that read
    # this to decide whether to call credit_service.refund_credits().
    refundable: bool = True


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
