from __future__ import annotations

from typing import Any

from app.core.time import utc_now

JsonDict = dict[str, Any]


def generated_at() -> str:
    return utc_now().isoformat()
