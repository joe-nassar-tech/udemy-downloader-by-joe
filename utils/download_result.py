from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DownloadResult:
    """Outcome returned by every download helper."""

    success: bool
    error: Optional[str] = None

    @classmethod
    def ok(cls):
        return cls(True)

    @classmethod
    def failed(cls, error):
        return cls(False, str(error))
