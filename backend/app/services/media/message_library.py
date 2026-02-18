"""Deterministic, repo-local message library for Gelo OTC playbooks.

Hard rule: do not hallucinate copy. If a mapping is missing, mark it as
`needs_review` and fall back to conservative generic copy.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_LIB_PATH = Path(__file__).with_name("gelo_message_library.json")


@dataclass(frozen=True)
class MessagePack:
    status: str  # "ok" | "needs_review"
    condition_key: str
    message_direction: str
    hero_message: str
    support_points: list[str]
    creative_angles: list[str]
    keyword_clusters: list[str]
    cta: str
    compliance_note: str
    library_version: str | None = None
    library_source: str | None = None

    def to_framework(self) -> dict[str, Any]:
        return {
            "hero_message": self.hero_message,
            "support_points": self.support_points,
            "compliance_note": self.compliance_note,
            "cta": self.cta,
            "copy_status": self.status,
            "library_version": self.library_version,
            "library_source": self.library_source,
        }

    def to_prompt_hints(self) -> dict[str, Any]:
        """Compact hints to bias LLM output without letting it invent claims."""
        return {
            "message_direction": self.message_direction,
            "hero_message": self.hero_message,
            "support_points": self.support_points[:3],
            "keyword_clusters": self.keyword_clusters[:6],
            "cta": self.cta,
            "compliance_note": self.compliance_note,
            "copy_status": self.status,
        }


def _stable_pick(items: list[str], seed: str) -> str:
    if not items:
        return ""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(items)
    return items[idx]


def _load_library() -> dict[str, Any]:
    try:
        raw = _LIB_PATH.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception as exc:
        logger.error("Failed to load message library at %s: %s", _LIB_PATH, exc)
        return {}


def _normalize_key(value: str | None) -> str:
    return str(value or "").strip().lower()


def select_gelo_message_pack(
    *,
    brand: str,
    product: str,
    condition_key: str,
    playbook_key: str | None = None,
    region_code: str | None = None,
    trigger_event: str | None = None,
) -> MessagePack:
    """Select a deterministic message pack for Gelo OTC consumer copy.

    This is conservative by design: missing mappings do not trigger LLM generation.
    """
    lib = _load_library()
    lib_version = lib.get("version")
    brand_key = _normalize_key(brand)
    product_key = _normalize_key(product)
    condition_key_norm = _normalize_key(condition_key)

    defaults = (((lib.get("defaults") or {}).get("conditions")) or {}).get(condition_key_norm) or {}
    product_cfg = (((lib.get("products") or {}).get(product_key)) or {}).get("conditions") or {}
    product_hit = product_cfg.get(condition_key_norm) or {}

    effective = {**defaults, **product_hit}
    status = "ok" if product_hit else "needs_review"

    # Deterministic seed per region+playbook so results stay stable for dashboards.
    seed = "|".join(
        [
            brand_key,
            product_key,
            condition_key_norm,
            _normalize_key(playbook_key),
            _normalize_key(region_code),
            _normalize_key(trigger_event),
        ]
    )

    direction = str(effective.get("message_direction") or defaults.get("message_direction") or "").strip()
    hero_messages = list(effective.get("hero_messages") or [])
    support_points = list(effective.get("support_points") or defaults.get("support_points") or [])
    creative_angles = list(effective.get("creative_angles") or defaults.get("creative_angles") or [])
    keyword_clusters = list(effective.get("keyword_clusters") or defaults.get("keyword_clusters") or [])
    cta_pool = list(effective.get("cta_pool") or defaults.get("cta_pool") or [])
    compliance_note = str(effective.get("compliance_note") or defaults.get("compliance_note") or "").strip()

    hero = _stable_pick(hero_messages, seed + "|hero") or "Konservativ, symptomnah kommunizieren."
    cta = _stable_pick(cta_pool, seed + "|cta") or "Mehr erfahren"

    # Provide a safe direction even when missing, but keep status as needs_review.
    if not direction:
        direction = "Konservativ, symptomnah und ohne Heilversprechen kommunizieren."

    return MessagePack(
        status=status if brand_key in {"gelo", "gelomyrtol", "gelo myrtol"} else status,
        condition_key=condition_key_norm or condition_key,
        message_direction=direction,
        hero_message=hero,
        support_points=support_points,
        creative_angles=creative_angles,
        keyword_clusters=keyword_clusters,
        cta=cta,
        compliance_note=compliance_note or "Hinweis: Aussagen konservativ und ohne Heilversprechen formulieren.",
        library_version=str(lib_version) if lib_version else None,
        library_source=str(_LIB_PATH.name),
    )
