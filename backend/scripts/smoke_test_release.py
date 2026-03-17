#!/usr/bin/env python3
"""Modern release smoke test against a running ViralFlux backend."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

EXIT_OK = 0
EXIT_READY_BLOCKED = 10
EXIT_BUSINESS_SMOKE_FAILED = 20
EXIT_LIVE_FAILED = 30


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--virus", default="Influenza A")
    parser.add_argument("--horizon", type=int, default=7)
    parser.add_argument("--budget-eur", type=float, default=50_000.0)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--check-cockpit", action="store_true")
    parser.add_argument("--target-source", default="RKI_ARE")
    return parser.parse_args()


def _request_json(base_url: str, path: str, timeout: float) -> tuple[int, dict[str, Any]]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = urllib.request.Request(url=url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.getcode(), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"raw_body": body}
        return exc.code, payload


def _build_query(params: dict[str, Any]) -> str:
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def _response_status(payload: dict[str, Any]) -> str:
    value = str(payload.get("status") or "").strip().lower()
    return value or "success"


def _is_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _missing_keys(mapping: Any, required: list[str]) -> list[str]:
    if not isinstance(mapping, dict):
        return list(required)
    return [key for key in required if key not in mapping]


def _live_check(status_code: int, payload: dict[str, Any], path: str) -> dict[str, Any]:
    errors: list[str] = []
    if status_code != 200:
        errors.append(f"Expected HTTP 200, got {status_code}.")
    if str(payload.get("status") or "").strip().lower() != "alive":
        errors.append("Expected payload status 'alive'.")
    return {
        "path": path,
        "status_code": status_code,
        "passed": not errors,
        "errors": errors,
        "summary": {
            "status": payload.get("status"),
            "environment": payload.get("environment"),
            "app_version": payload.get("app_version"),
        },
    }


def _ready_check(status_code: int, payload: dict[str, Any], path: str) -> dict[str, Any]:
    readiness_status = str(payload.get("status") or "").strip().lower()
    blocked = status_code != 200 or readiness_status != "healthy"
    return {
        "path": path,
        "status_code": status_code,
        "passed": not blocked,
        "blocked": blocked,
        "summary": {
            "status": payload.get("status"),
            "blockers": len(payload.get("blockers") or []),
            "components": sorted((payload.get("components") or {}).keys()),
        },
        "errors": [] if not blocked else [f"Readiness is {payload.get('status') or status_code}."],
    }


def _forecast_check(status_code: int, payload: dict[str, Any], path: str) -> dict[str, Any]:
    errors: list[str] = []
    if status_code != 200:
        errors.append(f"Expected HTTP 200, got {status_code}.")
    payload_status = _response_status(payload)
    predictions = payload.get("predictions")
    if payload_status != "success":
        errors.append(f"Expected success forecast payload, got status '{payload_status}'.")
    if not _is_non_empty_list(predictions):
        errors.append("Expected non-empty predictions list.")
        first_prediction: dict[str, Any] = {}
    else:
        first_prediction = predictions[0]
        missing = _missing_keys(
            first_prediction,
            ["bundesland", "decision_label", "priority_score", "reason_trace", "uncertainty_summary"],
        )
        if missing:
            errors.append(f"Forecast payload is missing required region keys: {', '.join(missing)}.")
    return {
        "path": path,
        "status_code": status_code,
        "passed": not errors,
        "errors": errors,
        "summary": {
            "virus_typ": payload.get("virus_typ"),
            "horizon_days": payload.get("horizon_days"),
            "predictions": len(predictions or []),
            "top_region": first_prediction.get("bundesland"),
            "top_decision_label": first_prediction.get("decision_label"),
            "quality_gate": (payload.get("quality_gate") or {}).get("forecast_readiness"),
        },
    }


def _allocation_check(status_code: int, payload: dict[str, Any], path: str) -> dict[str, Any]:
    errors: list[str] = []
    if status_code != 200:
        errors.append(f"Expected HTTP 200, got {status_code}.")
    payload_status = _response_status(payload)
    recommendations = payload.get("recommendations")
    if payload_status != "success":
        errors.append(f"Expected success allocation payload, got status '{payload_status}'.")
    if not _is_non_empty_list(recommendations):
        errors.append("Expected non-empty allocation recommendations.")
        first_recommendation: dict[str, Any] = {}
    else:
        first_recommendation = recommendations[0]
        missing = _missing_keys(
            first_recommendation,
            [
                "bundesland",
                "recommended_activation_level",
                "suggested_budget_share",
                "suggested_budget_amount",
                "allocation_reason_trace",
                "confidence",
            ],
        )
        if missing:
            errors.append(f"Allocation payload is missing required keys: {', '.join(missing)}.")
    summary = payload.get("summary") or {}
    return {
        "path": path,
        "status_code": status_code,
        "passed": not errors,
        "errors": errors,
        "summary": {
            "virus_typ": payload.get("virus_typ"),
            "horizon_days": payload.get("horizon_days"),
            "recommendations": len(recommendations or []),
            "activate_regions": summary.get("activate_regions"),
            "prepare_regions": summary.get("prepare_regions"),
            "watch_regions": summary.get("watch_regions"),
            "total_budget_allocated": summary.get("total_budget_allocated"),
        },
    }


def _campaign_check(status_code: int, payload: dict[str, Any], path: str) -> dict[str, Any]:
    errors: list[str] = []
    if status_code != 200:
        errors.append(f"Expected HTTP 200, got {status_code}.")
    payload_status = _response_status(payload)
    recommendations = payload.get("recommendations")
    if payload_status != "success":
        errors.append(f"Expected success campaign payload, got status '{payload_status}'.")
    if not _is_non_empty_list(recommendations):
        errors.append("Expected non-empty campaign recommendations.")
        first_recommendation: dict[str, Any] = {}
    else:
        first_recommendation = recommendations[0]
        missing = _missing_keys(
            first_recommendation,
            [
                "region",
                "recommended_product_cluster",
                "recommended_keyword_cluster",
                "activation_level",
                "suggested_budget_amount",
                "confidence",
                "evidence_class",
                "recommendation_rationale",
            ],
        )
        if missing:
            errors.append(f"Campaign payload is missing required keys: {', '.join(missing)}.")
    summary = payload.get("summary") or {}
    return {
        "path": path,
        "status_code": status_code,
        "passed": not errors,
        "errors": errors,
        "summary": {
            "virus_typ": payload.get("virus_typ"),
            "horizon_days": payload.get("horizon_days"),
            "recommendations": len(recommendations or []),
            "top_region": summary.get("top_region"),
            "top_product_cluster": summary.get("top_product_cluster"),
            "ready_recommendations": summary.get("ready_recommendations"),
        },
    }


def _cockpit_check(status_code: int, payload: dict[str, Any], path: str) -> dict[str, Any]:
    errors: list[str] = []
    if status_code != 200:
        errors.append(f"Expected HTTP 200, got {status_code}.")
    if not isinstance(payload, dict):
        errors.append("Expected cockpit JSON object.")
        keys: list[str] = []
    else:
        keys = sorted(payload.keys())
    return {
        "path": path,
        "status_code": status_code,
        "passed": not errors,
        "advisory": True,
        "errors": errors,
        "summary": {
            "keys": keys[:12],
            "key_count": len(keys),
        },
    }


def run_smoke(
    *,
    base_url: str,
    timeout: float,
    virus: str,
    horizon: int,
    budget_eur: float,
    top_n: int,
    target_source: str,
    check_cockpit: bool,
) -> tuple[int, dict[str, Any]]:
    forecast_query = _build_query({"virus_typ": virus, "horizon_days": horizon})
    allocation_query = _build_query(
        {"virus_typ": virus, "horizon_days": horizon, "weekly_budget_eur": budget_eur}
    )
    campaign_query = _build_query(
        {
            "virus_typ": virus,
            "horizon_days": horizon,
            "weekly_budget_eur": budget_eur,
            "top_n": top_n,
        }
    )
    cockpit_query = _build_query({"virus_typ": virus, "target_source": target_source})

    checks: dict[str, dict[str, Any]] = {}

    live_path = "/health/live"
    live_status, live_payload = _request_json(base_url, live_path, timeout)
    checks["health_live"] = _live_check(live_status, live_payload, live_path)

    ready_path = "/health/ready"
    ready_status, ready_payload = _request_json(base_url, ready_path, timeout)
    checks["health_ready"] = _ready_check(ready_status, ready_payload, ready_path)

    forecast_path = f"/api/v1/forecast/regional/predict?{forecast_query}"
    forecast_status, forecast_payload = _request_json(base_url, forecast_path, timeout)
    checks["regional_forecast"] = _forecast_check(forecast_status, forecast_payload, forecast_path)

    allocation_path = f"/api/v1/forecast/regional/media-allocation?{allocation_query}"
    allocation_status, allocation_payload = _request_json(base_url, allocation_path, timeout)
    checks["regional_allocation"] = _allocation_check(allocation_status, allocation_payload, allocation_path)

    campaign_path = f"/api/v1/forecast/regional/campaign-recommendations?{campaign_query}"
    campaign_status, campaign_payload = _request_json(base_url, campaign_path, timeout)
    checks["regional_campaign_recommendations"] = _campaign_check(
        campaign_status,
        campaign_payload,
        campaign_path,
    )

    if check_cockpit:
        cockpit_path = f"/api/v1/media/cockpit?{cockpit_query}"
        cockpit_status, cockpit_payload = _request_json(base_url, cockpit_path, timeout)
        checks["media_cockpit_advisory"] = _cockpit_check(cockpit_status, cockpit_payload, cockpit_path)

    live_failed = not checks["health_live"]["passed"]
    ready_blocked = bool(checks["health_ready"]["blocked"])
    business_failures = [
        key
        for key in ("regional_forecast", "regional_allocation", "regional_campaign_recommendations")
        if not checks[key]["passed"]
    ]

    if live_failed:
        failure_level = "live_failed"
        exit_code = EXIT_LIVE_FAILED
        status = "fail"
    elif business_failures:
        failure_level = "business_smoke_failed"
        exit_code = EXIT_BUSINESS_SMOKE_FAILED
        status = "fail"
    elif ready_blocked:
        failure_level = "ready_blocked"
        exit_code = EXIT_READY_BLOCKED
        status = "warning"
    else:
        failure_level = "none"
        exit_code = EXIT_OK
        status = "pass"

    result = {
        "status": status,
        "failure_level": failure_level,
        "checks": checks,
        "business_core_scope": {
            "virus_typ": virus,
            "horizon_days": horizon,
            "weekly_budget_eur": round(float(budget_eur), 2),
            "top_n": int(top_n),
        },
        "failure_levels": {
            "live_failed": "Process is not alive or /health/live is not healthy.",
            "ready_blocked": "Service is alive but /health/ready is not healthy.",
            "business_smoke_failed": "Core regional product endpoints failed or returned invalid payloads.",
        },
    }
    return exit_code, result


def main() -> int:
    args = _parse_args()
    exit_code, result = run_smoke(
        base_url=args.base_url,
        timeout=args.timeout,
        virus=args.virus,
        horizon=args.horizon,
        budget_eur=args.budget_eur,
        top_n=args.top_n,
        target_source=args.target_source,
        check_cockpit=args.check_cockpit,
    )
    print(json.dumps(result, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
