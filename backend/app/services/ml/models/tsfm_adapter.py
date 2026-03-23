from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TSFMAdapter:
    provider: str = "disabled"
    enabled: bool = False
    available: bool = False
    reason: str = "feature_flag_disabled"

    @classmethod
    def from_settings(cls, *, enabled: bool = False, provider: str = "timesfm") -> "TSFMAdapter":
        if not enabled:
            return cls(provider=provider, enabled=False, available=False, reason="feature_flag_disabled")
        try:
            __import__(provider)
            return cls(provider=provider, enabled=True, available=True, reason="import_ok")
        except Exception as exc:
            return cls(provider=provider, enabled=True, available=False, reason=f"import_failed:{exc.__class__.__name__}")

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "available": self.available,
            "reason": self.reason,
        }
