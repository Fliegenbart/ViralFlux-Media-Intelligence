"""Health and monitoring helpers for weather vintage shadow runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def build_weather_vintage_shadow_health_report(
    run_summaries: list[dict[str, Any]],
    *,
    now: datetime | None,
    max_run_age_hours: int,
    max_days_without_comparable: int,
    max_insufficient_identity_streak: int,
    parse_generated_at_fn: Any,
    weather_health_status_exit_code_fn: Any,
    combine_weather_health_status_fn: Any,
    json_safe_fn: Any,
) -> dict[str, Any]:
    now_dt = now or datetime.utcnow()
    status = "ok"
    findings: list[dict[str, Any]] = []
    sorted_runs = sorted(
        run_summaries,
        key=lambda item: parse_generated_at_fn(item.get("generated_at")) or datetime.min,
    )
    latest_run = sorted_runs[-1] if sorted_runs else None

    def add_finding(severity: str, code: str, message: str, **details: Any) -> None:
        nonlocal status
        status = combine_weather_health_status_fn(status, severity)
        findings.append(
            json_safe_fn(
                {
                    "severity": severity,
                    "code": code,
                    "message": message,
                    **details,
                }
            )
        )

    if latest_run is None:
        add_finding(
            "critical",
            "no_scheduled_shadow_runs",
            "Es gibt noch keine archivierten scheduled_shadow-Läufe für den Weather-Vintage-Shadow-Betrieb.",
        )
    else:
        latest_generated_at = parse_generated_at_fn(latest_run.get("generated_at"))
        if latest_generated_at is not None:
            age_hours = round(
                max((now_dt - latest_generated_at).total_seconds(), 0.0) / 3600.0,
                2,
            )
            if age_hours > float(max_run_age_hours * 2):
                add_finding(
                    "critical",
                    "latest_run_stale",
                    "Der letzte scheduled_shadow-Lauf ist deutlich aelter als erlaubt.",
                    run_id=latest_run.get("run_id"),
                    generated_at=latest_run.get("generated_at"),
                    age_hours=age_hours,
                    threshold_hours=max_run_age_hours,
                )
            elif age_hours > float(max_run_age_hours):
                add_finding(
                    "warning",
                    "latest_run_stale",
                    "Der letzte scheduled_shadow-Lauf ist aelter als der erlaubte Schwellwert.",
                    run_id=latest_run.get("run_id"),
                    generated_at=latest_run.get("generated_at"),
                    age_hours=age_hours,
                    threshold_hours=max_run_age_hours,
                )
        latest_summary = latest_run.get("summary") or {}
        latest_failed_scopes = int(latest_summary.get("failed_scopes") or 0)
        latest_archived_scopes = int(latest_summary.get("archived_scopes") or 0)
        if latest_archived_scopes > 0 and latest_failed_scopes >= latest_archived_scopes:
            add_finding(
                "critical",
                "latest_run_failed",
                "Der letzte scheduled_shadow-Lauf hat für alle Scopes unbrauchbare Ergebnisse geliefert.",
                run_id=latest_run.get("run_id"),
                failed_scopes=latest_failed_scopes,
                archived_scopes=latest_archived_scopes,
            )
        elif latest_failed_scopes > 0:
            add_finding(
                "warning",
                "latest_run_partial_failure",
                "Der letzte scheduled_shadow-Lauf hat für mindestens einen Scope einen Fehler geliefert.",
                run_id=latest_run.get("run_id"),
                failed_scopes=latest_failed_scopes,
                archived_scopes=latest_archived_scopes,
            )

    grouped_scopes: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for run_summary in sorted_runs:
        generated_at = run_summary.get("generated_at")
        for scope in run_summary.get("scopes") or []:
            key = (str(scope.get("virus_typ") or ""), int(scope.get("horizon_days") or 0))
            grouped_scopes.setdefault(key, []).append(
                {
                    **scope,
                    "generated_at": generated_at,
                    "run_id": run_summary.get("run_id"),
                }
            )

    scope_health: list[dict[str, Any]] = []
    for (virus_typ, horizon_days), rows in sorted(grouped_scopes.items()):
        rows = sorted(
            rows,
            key=lambda item: parse_generated_at_fn(item.get("generated_at")) or datetime.min,
        )
        first_seen = parse_generated_at_fn(rows[0].get("generated_at"))
        last_comparable = None
        insufficient_streak = 0
        for row in reversed(rows):
            eligibility = str(row.get("comparison_eligibility") or "")
            if eligibility == "insufficient_identity":
                insufficient_streak += 1
            else:
                break
        for row in reversed(rows):
            if str(row.get("comparison_eligibility") or "") == "comparable":
                last_comparable = parse_generated_at_fn(row.get("generated_at"))
                break

        scope_status = "ok"
        scope_findings: list[dict[str, Any]] = []
        if insufficient_streak >= int(max_insufficient_identity_streak * 2):
            scope_status = combine_weather_health_status_fn(scope_status, "critical")
            scope_findings.append(
                {
                    "severity": "critical",
                    "code": "insufficient_identity_streak",
                    "streak": insufficient_streak,
                    "threshold": max_insufficient_identity_streak,
                }
            )
        elif insufficient_streak >= int(max_insufficient_identity_streak):
            scope_status = combine_weather_health_status_fn(scope_status, "warning")
            scope_findings.append(
                {
                    "severity": "warning",
                    "code": "insufficient_identity_streak",
                    "streak": insufficient_streak,
                    "threshold": max_insufficient_identity_streak,
                }
            )

        if last_comparable is None:
            days_without_comparable = (
                round(max((now_dt - first_seen).total_seconds(), 0.0) / 86400.0, 2)
                if first_seen is not None
                else None
            )
            if (
                days_without_comparable is not None
                and days_without_comparable > float(max_days_without_comparable)
            ):
                scope_status = combine_weather_health_status_fn(scope_status, "critical")
                scope_findings.append(
                    {
                        "severity": "critical",
                        "code": "no_comparable_runs",
                        "days_without_comparable": days_without_comparable,
                        "threshold_days": max_days_without_comparable,
                    }
                )
            elif rows:
                scope_status = combine_weather_health_status_fn(scope_status, "warning")
                scope_findings.append(
                    {
                        "severity": "warning",
                        "code": "still_waiting_for_comparable_run",
                        "days_without_comparable": days_without_comparable,
                        "threshold_days": max_days_without_comparable,
                    }
                )
        else:
            days_since_comparable = round(
                max((now_dt - last_comparable).total_seconds(), 0.0) / 86400.0,
                2,
            )
            if days_since_comparable > float(max_days_without_comparable * 2):
                scope_status = combine_weather_health_status_fn(scope_status, "critical")
                scope_findings.append(
                    {
                        "severity": "critical",
                        "code": "comparable_run_too_old",
                        "days_since_comparable": days_since_comparable,
                        "threshold_days": max_days_without_comparable,
                    }
                )
            elif days_since_comparable > float(max_days_without_comparable):
                scope_status = combine_weather_health_status_fn(scope_status, "warning")
                scope_findings.append(
                    {
                        "severity": "warning",
                        "code": "comparable_run_old",
                        "days_since_comparable": days_since_comparable,
                        "threshold_days": max_days_without_comparable,
                    }
                )

        status = combine_weather_health_status_fn(status, scope_status)
        scope_health.append(
            json_safe_fn(
                {
                    "virus_typ": virus_typ,
                    "horizon_days": horizon_days,
                    "status": scope_status,
                    "archived_runs": len(rows),
                    "comparable_runs": sum(
                        1 for row in rows if row.get("comparison_eligibility") == "comparable"
                    ),
                    "insufficient_identity_streak": insufficient_streak,
                    "last_comparable_generated_at": (
                        last_comparable.isoformat() if last_comparable is not None else None
                    ),
                    "findings": scope_findings,
                }
            )
        )

    summary = {
        "total_runs": int(len(sorted_runs)),
        "monitored_scopes": int(len(scope_health)),
        "comparable_scopes": int(
            sum(1 for item in scope_health if int(item.get("comparable_runs") or 0) > 0)
        ),
        "warning_scopes": int(sum(1 for item in scope_health if item.get("status") == "warning")),
        "critical_scopes": int(
            sum(1 for item in scope_health if item.get("status") == "critical")
        ),
    }
    return json_safe_fn(
        {
            "comparison_type": "weather_vintage_prospective_shadow_health",
            "generated_at": now_dt.isoformat(),
            "status": status,
            "exit_code": weather_health_status_exit_code_fn(status),
            "thresholds": {
                "max_run_age_hours": int(max_run_age_hours),
                "max_days_without_comparable": int(max_days_without_comparable),
                "max_insufficient_identity_streak": int(max_insufficient_identity_streak),
            },
            "included_run_purposes": sorted(
                {str(item.get("run_purpose") or "unknown") for item in sorted_runs}
            ),
            "latest_run": (
                {
                    "run_id": latest_run.get("run_id"),
                    "generated_at": latest_run.get("generated_at"),
                    "run_purpose": latest_run.get("run_purpose"),
                    "summary": latest_run.get("summary") or {},
                }
                if latest_run is not None
                else None
            ),
            "findings": findings,
            "scopes": scope_health,
            "summary": summary,
        }
    )
