from __future__ import annotations

import json
from typing import Any


def reason_trace_lines(trace: Any) -> list[str]:
    if not trace:
        return []
    if isinstance(trace, str):
        stripped = trace.strip()
        return [stripped] if stripped else []
    if isinstance(trace, list):
        lines: list[str] = []
        for item in trace:
            if is_reason_detail_item(item):
                message = str(item.get("message") or "").strip()
                if message:
                    lines.append(message)
                continue
            stripped = str(item).strip()
            if stripped:
                lines.append(stripped)
        return lines
    if isinstance(trace, dict):
        lines: list[str] = []
        for key in (
            "why",
            "uncertainty",
            "guardrails",
            "budget_notes",
            "evidence_notes",
            "product_fit",
            "keyword_fit",
        ):
            value = trace.get(key)
            if isinstance(value, list):
                lines.extend(str(item).strip() for item in value if str(item).strip())
        for key in (
            "why_details",
            "uncertainty_details",
            "policy_override_details",
            "budget_driver_details",
            "blocker_details",
            "guardrail_details",
            "budget_note_details",
            "evidence_note_details",
            "product_fit_details",
            "keyword_fit_details",
        ):
            value = trace.get(key)
            if isinstance(value, list):
                for item in value:
                    if is_reason_detail_item(item):
                        message = str(item.get("message") or "").strip()
                        if message:
                            lines.append(message)
        if trace.get("summary"):
            lines.append(str(trace.get("summary")).strip())
        return [item for item in lines if item]
    return [str(trace).strip()]


def is_reason_detail_item(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("code"), str)
        and isinstance(value.get("message"), str)
    )


def reason_trace_detail_items(trace: Any) -> list[dict[str, Any]]:
    if not trace:
        return []
    if is_reason_detail_item(trace):
        return [dict(trace)]
    if isinstance(trace, list):
        return [dict(item) for item in trace if is_reason_detail_item(item)]
    if isinstance(trace, dict):
        details: list[dict[str, Any]] = []
        for key in (
            "why_details",
            "uncertainty_details",
            "policy_override_details",
            "budget_driver_details",
            "blocker_details",
            "guardrail_details",
            "budget_note_details",
            "evidence_note_details",
            "product_fit_details",
            "keyword_fit_details",
        ):
            value = trace.get(key)
            if isinstance(value, list):
                details.extend(dict(item) for item in value if is_reason_detail_item(item))
        return details
    return []


def unique_reason_details(values: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        if not is_reason_detail_item(value):
            continue
        key = json.dumps(value, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(value))
    return result


def unique_non_empty(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result
