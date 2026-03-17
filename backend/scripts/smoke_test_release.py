#!/usr/bin/env python3
"""Release smoke test against a running ViralFlux backend."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--check-regional-validation", action="store_true")
    parser.add_argument("--virus", default="Influenza A")
    parser.add_argument("--horizon", type=int, default=7)
    return parser.parse_args()


def _request_json(base_url: str, path: str, timeout: float) -> tuple[int, dict]:
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


def main() -> int:
    args = _parse_args()
    results: dict[str, dict] = {}
    exit_code = 0

    live_status, live_payload = _request_json(args.base_url, "/health/live", args.timeout)
    results["health_live"] = {"status_code": live_status, "payload": live_payload}
    if live_status != 200:
        exit_code = 1

    ready_status, ready_payload = _request_json(args.base_url, "/health/ready", args.timeout)
    results["health_ready"] = {"status_code": ready_status, "payload": ready_payload}
    if args.require_ready and ready_status != 200:
        exit_code = 1

    if args.check_regional_validation:
        query = urllib.parse.urlencode(
            {
                "virus_typ": args.virus,
                "brand": "gelo",
                "horizon_days": args.horizon,
            }
        )
        validation_status, validation_payload = _request_json(
            args.base_url,
            f"/api/v1/forecast/regional/validation?{query}",
            args.timeout,
        )
        results["regional_validation"] = {
            "status_code": validation_status,
            "payload": validation_payload,
        }
        if validation_status >= 500:
            exit_code = 1

    print(json.dumps(results, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
