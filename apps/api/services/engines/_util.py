"""
Shared helpers for engines that shell out to a CLI tool (LibreOffice,
ffmpeg, poppler, tesseract, qpdf) or need scratch files on disk. Every
engine here processes one request at a time in a throwaway temp
directory — fine at this scale; the background job queue in
docs/TODO.md is where this would move to worker-local scratch space once
jobs run async.
"""
from __future__ import annotations

import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


class SubprocessError(Exception):
    def __init__(self, cmd: list[str], returncode: int, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"{cmd[0]} exited {returncode}: {stderr[:500]}")


@contextmanager
def scratch_dir():
    with tempfile.TemporaryDirectory(prefix="tweakhub-") as d:
        yield Path(d)


_FONT_CACHE: list[str] = []


def find_ttf_font() -> str | None:
    """Locate any installed TrueType font — used where a tool (Pillow watermarking,
    ffmpeg's drawtext filter) needs an explicit font file path rather than relying on
    a system default that may not exist in a minimal container."""
    if _FONT_CACHE:
        return _FONT_CACHE[0]

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            _FONT_CACHE.append(c)
            return c

    for p in Path("/usr/share/fonts").rglob("*.ttf"):
        _FONT_CACHE.append(str(p))
        return str(p)

    return None


def run(cmd: list[str], timeout: int = 120, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    """Run a subprocess, raising SubprocessError with captured stderr on failure."""
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise SubprocessError(cmd, -1, f"timed out after {timeout}s") from exc

    if result.returncode != 0:
        raise SubprocessError(cmd, result.returncode, result.stderr or result.stdout)
    return result
