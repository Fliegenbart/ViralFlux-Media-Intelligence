#!/usr/bin/env python3
"""Check whether the public production surface leaks internal details."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


EXIT_OK = 0
EXIT_PUBLIC_SURFACE_EXPOSED = 20

_MAIN_ASSET_PATTERN = re.compile(r'/static/js/main\.[a-f0-9]{8}\.js')


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://fluxengine.labpulse.ai")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--welcome-path", default="/")
    parser.add_argument("--admin-status-path", default="/api/v1/admin/ml/status/test-task")
    return parser.parse_args()


def _request(
    base_url: str,
    path: str,
    timeout: float,
) -> tuple[int, dict[str, str], bytes]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = urllib.request.Request(url=url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.getcode(), dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def _decode_body(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("utf-8", errors="replace")


def _extract_main_asset_path(html: str) -> str | None:
    match = _MAIN_ASSET_PATTERN.search(html or "")
    if not match:
        return None
    return match.group(0)


def _readiness_leaks_internal_details(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return True
    forbidden_keys = {"components", "startup", "blockers", "warnings"}
    return any(key in payload for key in forbidden_keys)


def _hidden_surface_check(name: str, path: str, status_code: int) -> dict[str, Any]:
    passed = status_code in {401, 403, 404}
    errors = [] if passed else [f"{name} should not be publicly reachable (HTTP {status_code})."]
    return {
        "path": path,
        "status_code": status_code,
        "passed": passed,
        "errors": errors,
    }


def _readiness_check(path: str, status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if status_code != 200:
        errors.append(f"Public readiness should answer with HTTP 200, got {status_code}.")
    if _readiness_leaks_internal_details(payload):
        errors.append("Public readiness still exposes internal readiness details.")
    return {
        "path": path,
        "status_code": status_code,
        "passed": not errors,
        "errors": errors,
        "summary": {
            "status": payload.get("status") if isinstance(payload, dict) else None,
            "keys": sorted(payload.keys()) if isinstance(payload, dict) else None,
        },
    }


def _source_map_check(
    *,
    welcome_path: str,
    welcome_status: int,
    welcome_html: str,
    source_map_status: int | None,
    source_map_path: str | None,
) -> dict[str, Any]:
    errors: list[str] = []
    if welcome_status != 200:
        errors.append(f"Landing page should be reachable to inspect assets (HTTP {welcome_status}).")

    asset_path = _extract_main_asset_path(welcome_html)
    if not asset_path:
        errors.append("Could not find the main frontend asset on the landing page.")
    elif source_map_status is None or source_map_path is None:
        errors.append("Could not derive the source-map path from the main frontend asset.")
    elif source_map_status == 200:
        errors.append("Frontend source map is still publicly reachable.")

    return {
        "path": source_map_path,
        "status_code": source_map_status,
        "passed": not errors,
        "errors": errors,
        "summary": {
            "welcome_path": welcome_path,
            "asset_path": asset_path,
        },
    }


def run_check(
    *,
    base_url: str,
    timeout: float,
    welcome_path: str,
    admin_status_path: str,
) -> tuple[int, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}

    docs_status, _, _ = _request(base_url, "/docs", timeout)
    checks["docs"] = _hidden_surface_check("Swagger UI", "/docs", docs_status)

    openapi_status, _, _ = _request(base_url, "/openapi.json", timeout)
    checks["openapi"] = _hidden_surface_check("OpenAPI schema", "/openapi.json", openapi_status)

    admin_status_code, _, _ = _request(base_url, admin_status_path, timeout)
    checks["admin_status"] = _hidden_surface_check(
        "Admin ML status endpoint",
        admin_status_path,
        admin_status_code,
    )

    ready_status, _, ready_body = _request(base_url, "/health/ready", timeout)
    try:
        ready_payload = json.loads(_decode_body(ready_body))
    except json.JSONDecodeError:
        ready_payload = {"raw_body": _decode_body(ready_body)}
    checks["public_readiness"] = _readiness_check("/health/ready", ready_status, ready_payload)

    welcome_status, _, welcome_body = _request(base_url, welcome_path, timeout)
    welcome_html = _decode_body(welcome_body)
    asset_path = _extract_main_asset_path(welcome_html)
    source_map_path = f"{asset_path}.map" if asset_path else None
    source_map_status = None
    if source_map_path:
        source_map_status, _, _ = _request(base_url, source_map_path, timeout)
    checks["source_map"] = _source_map_check(
        welcome_path=welcome_path,
        welcome_status=welcome_status,
        welcome_html=welcome_html,
        source_map_status=source_map_status,
        source_map_path=source_map_path,
    )

    failures = [name for name, check in checks.items() if not check["passed"]]
    exit_code = EXIT_OK if not failures else EXIT_PUBLIC_SURFACE_EXPOSED
    payload = {
        "status": "ok" if not failures else "fail",
        "failure_level": None if not failures else "public_surface_exposed",
        "checks": checks,
    }
    return exit_code, payload


def main() -> int:
    args = _parse_args()
    exit_code, payload = run_check(
        base_url=args.base_url,
        timeout=args.timeout,
        welcome_path=args.welcome_path,
        admin_status_path=args.admin_status_path,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
