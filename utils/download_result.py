import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DownloadResult:
    """Outcome returned by every download helper."""

    success: bool
    error: Optional[str] = None
    file_path: Optional[str] = None
    file_size: int = 0
    elapsed_seconds: float = 0.0
    retries: int = 0

    # -- Convenience constructors ------------------------------------------

    @classmethod
    def ok(cls, file_path: Optional[str] = None, elapsed_seconds: float = 0.0, retries: int = 0):
        """Return a successful result, optionally with file metadata."""
        size = 0
        if file_path and os.path.isfile(file_path):
            try:
                size = os.path.getsize(file_path)
            except OSError:
                pass
        return cls(
            success=True,
            file_path=file_path,
            file_size=size,
            elapsed_seconds=elapsed_seconds,
            retries=retries,
        )

    @classmethod
    def failed(cls, error, elapsed_seconds: float = 0.0, retries: int = 0):
        return cls(
            success=False,
            error=str(error),
            elapsed_seconds=elapsed_seconds,
            retries=retries,
        )

    @classmethod
    def with_file_info(cls, path: str, elapsed_seconds: float = 0.0, retries: int = 0):
        """Build a successful result by reading file size automatically."""
        size = 0
        if os.path.isfile(path):
            try:
                size = os.path.getsize(path)
            except OSError:
                pass
        return cls(
            success=True,
            file_path=path,
            file_size=size,
            elapsed_seconds=elapsed_seconds,
            retries=retries,
        )

    # -- Display -----------------------------------------------------------

    def __str__(self) -> str:
        status = "✓ OK" if self.success else "✗ FAILED"
        parts = [status]
        if self.file_path:
            parts.append(f"path={self.file_path}")
        if self.file_size:
            if self.file_size >= 1024 * 1024:
                parts.append(f"size={self.file_size / (1024 * 1024):.1f} MB")
            else:
                parts.append(f"size={self.file_size / 1024:.1f} KB")
        if self.elapsed_seconds:
            parts.append(f"elapsed={self.elapsed_seconds:.2f}s")
        if self.retries:
            parts.append(f"retries={self.retries}")
        if self.error:
            parts.append(f"error={self.error}")
        return " | ".join(parts)
