from __future__ import annotations

from typing import Any

from app.services.source_coverage_semantics import (
    ARTIFACT_SOURCE_COVERAGE_SCOPE,
    live_source_readiness,
)


def _gate_snapshot(
    service,
    *,
    forecast: dict[str, Any],
    truth_coverage: dict[str, Any],
    business_validation: dict[str, Any],
    evaluation: dict[str, Any] | None,
    operational_snapshot: dict[str, Any] | None,
    forecast_readiness: str,
    commercial_validation_status: str,
    overall_scope_readiness: str,
    missing_requirements: list[str],
) -> dict[str, Any]:
    quality_gate = forecast.get("quality_gate") or {}
    latest_evaluation = evaluation or {}
    budget_mode = service._budget_mode(business_validation=business_validation)
    return {
        "scope_readiness": overall_scope_readiness,
        "forecast_readiness": forecast_readiness,
        "epidemiology_status": service._epidemiology_status(
            forecast,
            operational_snapshot=operational_snapshot,
        ),
        "commercial_data_status": service._commercial_data_status(
            truth_coverage=truth_coverage,
            business_validation=business_validation,
        ),
        "commercial_validation_status": commercial_validation_status,
        "holdout_status": "GO" if business_validation.get("holdout_ready") else "WATCH",
        "budget_release_status": (
            "GO" if business_validation.get("validated_for_budget_activation") else "WATCH"
        ),
        "pilot_mode": "forecast_first",
        "budget_mode": budget_mode,
        "validation_disclaimer": service._validation_disclaimer(
            business_validation=business_validation,
            budget_mode=budget_mode,
        ),
        "missing_requirements": missing_requirements,
        "coverage_weeks": truth_coverage.get("coverage_weeks"),
        "truth_freshness_state": truth_coverage.get("truth_freshness_state"),
        "validation_status": business_validation.get("validation_status"),
        "quality_gate_failed_checks": list(quality_gate.get("failed_checks") or []),
        "forecast_gate_outcome": quality_gate.get("forecast_readiness"),
        "operational_readiness": service._operational_readiness_snapshot(operational_snapshot),
        "latest_evaluation": {
            "available": bool(evaluation),
            "run_id": latest_evaluation.get("run_id"),
            "generated_at": latest_evaluation.get("generated_at"),
            "selected_experiment_name": latest_evaluation.get("selected_experiment_name"),
            "calibration_mode": latest_evaluation.get("calibration_mode"),
            "gate_outcome": latest_evaluation.get("gate_outcome"),
            "retained": latest_evaluation.get("retained"),
            "archive_dir": latest_evaluation.get("archive_dir"),
        },
    }


def _missing_requirements(
    service,
    *,
    truth_coverage: dict[str, Any],
    business_validation: dict[str, Any],
) -> list[str]:
    requirements: list[str] = []
    coverage_weeks = int(truth_coverage.get("coverage_weeks") or 0)
    if coverage_weeks <= 0:
        requirements.append("Es sind noch keine GELO-Outcome-Daten angeschlossen.")
    elif coverage_weeks < 26:
        requirements.append("Es fehlen noch mindestens 26 Wochen GELO-Outcome-Historie.")
    if not truth_coverage.get("required_fields_present"):
        requirements.append("Wöchentliche Media-Spend-Daten fehlen noch in der GELO-Outcome-Schicht.")
    if not truth_coverage.get("conversion_fields_present"):
        requirements.append("Sales-, Orders- oder Revenue-Metriken fehlen noch in der GELO-Outcome-Schicht.")
    if int(business_validation.get("activation_cycles") or 0) < 2:
        requirements.append("Es werden noch mindestens zwei klar markierte Aktivierungszyklen benötigt.")
    if not business_validation.get("holdout_ready"):
        requirements.append("Eine Test-/Kontrolllogik beziehungsweise ein Holdout-Design fehlt noch.")
    if not business_validation.get("lift_metrics_available"):
        requirements.append("Validierte inkrementelle Lift-Metriken fehlen noch.")
    return requirements


def _forecast_scope_readiness(
    service,
    forecast: dict[str, Any],
    *,
    operational_snapshot: dict[str, Any] | None = None,
) -> str:
    status = str(forecast.get("status") or "").strip().lower()
    if status in {"no_model", "unsupported"}:
        return "NO_GO"
    if status == "no_data" or not (forecast.get("predictions") or []):
        return "NO_GO"
    if not bool((forecast.get("quality_gate") or {}).get("overall_passed")):
        return "WATCH"
    if operational_snapshot:
        operational_status = service._operational_scope_status(operational_snapshot)
        if operational_status == "NO_GO":
            return "NO_GO"
        if operational_status == "WATCH":
            return "WATCH"
    if bool((forecast.get("quality_gate") or {}).get("overall_passed")):
        return "GO"
    return "WATCH"


def _allocation_scope_readiness(service, allocation: dict[str, Any]) -> str:
    status = str(allocation.get("status") or "").strip().lower()
    if status in {"no_model", "unsupported", "no_data"} or not (allocation.get("recommendations") or []):
        return "NO_GO"
    if any(
        item.get("suggested_budget_share") is not None
        or item.get("suggested_budget_amount") is not None
        or item.get("budget_eur") is not None
        for item in (allocation.get("recommendations") or [])
    ):
        return "GO"
    return "WATCH"


def _recommendation_scope_readiness(service, recommendations: dict[str, Any]) -> str:
    status = str(recommendations.get("status") or "").strip().lower()
    if status in {"no_model", "unsupported", "no_data"} or not (recommendations.get("recommendations") or []):
        return "NO_GO"
    if int(recommendations.get("summary", {}).get("ready_recommendations") or 0) > 0:
        return "GO"
    if int(recommendations.get("summary", {}).get("guarded_recommendations") or 0) > 0:
        return "GO"
    if int(recommendations.get("summary", {}).get("observe_only_recommendations") or 0) > 0:
        return "GO"
    return "WATCH"


def _evidence_scope_readiness(
    service,
    *,
    business_validation: dict[str, Any],
    evaluation: dict[str, Any] | None,
) -> str:
    if evaluation and evaluation.get("gate_outcome") == "GO" and evaluation.get("retained") is True:
        return "GO"
    if evaluation or business_validation.get("coverage_weeks") or business_validation.get("validation_status"):
        return "WATCH"
    return "NO_GO"


def _forecast_first_scope_readiness(
    service,
    *,
    forecast: dict[str, Any],
    evaluation: dict[str, Any] | None,
    operational_snapshot: dict[str, Any] | None = None,
) -> str:
    forecast_readiness = service._forecast_scope_readiness(
        forecast,
        operational_snapshot=operational_snapshot,
    )
    if forecast_readiness == "NO_GO":
        return "NO_GO"
    if (
        forecast_readiness == "GO"
        and evaluation
        and evaluation.get("gate_outcome") == "GO"
        and evaluation.get("retained") is True
    ):
        return "GO"
    return "WATCH"


def _epidemiology_status(
    service,
    forecast: dict[str, Any],
    *,
    operational_snapshot: dict[str, Any] | None = None,
) -> str:
    forecast_status = service._forecast_scope_readiness(
        forecast,
        operational_snapshot=operational_snapshot,
    )
    if forecast_status == "GO":
        return "GO"
    if forecast_status == "NO_GO":
        return "NO_GO"
    if str(forecast.get("status") or "").strip().lower() in {"no_model", "no_data", "unsupported"}:
        return "NO_GO"
    return "WATCH"


def _status_to_readiness(service, value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "ok":
        return "GO"
    if normalized == "critical":
        return "NO_GO"
    return "WATCH"


def _operational_scope_status(service, operational_snapshot: dict[str, Any] | None) -> str:
    if not operational_snapshot:
        return "GO"
    live_readiness = live_source_readiness(operational_snapshot)
    coverage_status = str(live_readiness.get("coverage_status") or "").strip().lower()
    freshness_status = str(live_readiness.get("freshness_status") or "").strip().lower()
    recency_status = str(operational_snapshot.get("forecast_recency_status") or "").strip().lower()
    candidates = [status for status in (coverage_status, freshness_status, recency_status) if status]
    if "critical" in candidates:
        return "NO_GO"
    if "warning" in candidates or "unknown" in candidates:
        return "WATCH"
    return "GO"


def _operational_readiness_snapshot(
    service,
    operational_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    if not operational_snapshot:
        return {
            "available": False,
            "scope_status": "WATCH",
            "forecast_recency_status": None,
            "live_source_coverage_status": None,
            "live_source_freshness_status": None,
            "forecast_recency_readiness": "WATCH",
            "live_source_coverage_readiness": "WATCH",
            "live_source_freshness_readiness": "WATCH",
            "source_coverage_scope": ARTIFACT_SOURCE_COVERAGE_SCOPE,
        }
    live_readiness = live_source_readiness(operational_snapshot)
    forecast_recency_status = str(operational_snapshot.get("forecast_recency_status") or "").strip().lower() or None
    live_source_coverage_status = str(live_readiness.get("coverage_status") or "").strip().lower() or None
    live_source_freshness_status = str(live_readiness.get("freshness_status") or "").strip().lower() or None
    return {
        "available": True,
        "scope_status": service._operational_scope_status(operational_snapshot),
        "forecast_recency_status": forecast_recency_status,
        "live_source_coverage_status": live_source_coverage_status,
        "live_source_freshness_status": live_source_freshness_status,
        "forecast_recency_readiness": service._status_to_readiness(forecast_recency_status),
        "live_source_coverage_readiness": service._status_to_readiness(live_source_coverage_status),
        "live_source_freshness_readiness": service._status_to_readiness(live_source_freshness_status),
        "source_coverage_scope": str(
            live_readiness.get("source_coverage_scope") or ARTIFACT_SOURCE_COVERAGE_SCOPE
        ),
    }


def _commercial_data_status(
    service,
    *,
    truth_coverage: dict[str, Any],
    business_validation: dict[str, Any],
) -> str:
    if int(truth_coverage.get("coverage_weeks") or 0) <= 0:
        return "NO_GO"
    if business_validation.get("validated_for_budget_activation"):
        return "GO"
    return "WATCH"


def _commercial_validation_status(
    service,
    *,
    truth_coverage: dict[str, Any],
    business_validation: dict[str, Any],
) -> str:
    return service._commercial_data_status(
        truth_coverage=truth_coverage,
        business_validation=business_validation,
    )


def _budget_mode(
    service,
    *,
    business_validation: dict[str, Any],
) -> str:
    if business_validation.get("validated_for_budget_activation"):
        return "validated_allocation"
    return "scenario_split"


def _validation_disclaimer(
    service,
    *,
    business_validation: dict[str, Any],
    budget_mode: str,
) -> str:
    if budget_mode == "validated_allocation" and business_validation.get("validated_for_budget_activation"):
        return "Forecast und kommerzielle Validierung greifen für diesen Scope bereits sauber zusammen."
    return (
        "Diese Budgetsicht ist ein forecast-basierter Szenario-Split. "
        "Die kommerzielle Validierung für die Budgetfreigabe von GELO steht noch aus."
    )


def _promotion_status(
    service,
    *,
    evaluation: dict[str, Any] | None,
    forecast: dict[str, Any],
    operational_snapshot: dict[str, Any] | None = None,
) -> str:
    if evaluation and evaluation.get("gate_outcome") == "GO" and evaluation.get("retained") is True:
        return "promoted_or_ready"
    if service._forecast_scope_readiness(
        forecast,
        operational_snapshot=operational_snapshot,
    ) == "GO":
        return "operational_go_without_budget_release"
    return "not_promoted"


def _empty_state(
    service,
    *,
    forecast: dict[str, Any],
    overall_scope_readiness: str,
    gate_snapshot: dict[str, Any],
) -> dict[str, Any]:
    status = str(forecast.get("status") or "").strip().lower()
    if status in {"no_model", "unsupported"}:
        return {
            "code": "no_model",
            "title": "Für diesen Scope ist aktuell kein kundenfähiges Modell verfügbar.",
            "body": "Wechsle Virus oder Horizont, bis der regionale Forecast-Pfad wieder verfügbar ist.",
        }
    if status == "no_data" or not (forecast.get("predictions") or []):
        return {
            "code": "no_data",
            "title": "Der Modellpfad existiert, aber aktuell reichen die Live-Daten noch nicht für eine Pilotentscheidung.",
            "body": "Die Oberfläche bleibt lesbar, aber es wird keine harte Empfehlung gezeigt.",
        }
    if overall_scope_readiness == "GO":
        return {
            "code": "ready",
            "title": "Dieser Scope ist für den Forecast-First-Pilot bereit.",
            "body": "Die aktuelle Empfehlungskette ist konsistent genug für ein kundenseitiges Forecast-Gespräch.",
        }
    if overall_scope_readiness == "NO_GO":
        return {
            "code": "no_go",
            "title": "Dieser Scope bleibt bewusst gesperrt.",
            "body": "Harte Gates schlagen noch fehl, deshalb bleibt die Budgetfreigabe geschlossen.",
        }
    if gate_snapshot.get("forecast_readiness") != "GO":
        return {
            "code": "watch_only",
            "title": "Der Pilot ist sichtbar, aber der Forecast-Pfad ist noch nicht stabil genug.",
            "body": "Belasse den Scope auf WATCH, bis Forecast-Evidenz und Promotion-Pfad stark genug für einen sauberen kundenseitigen Readout sind.",
        }
    return {
        "code": "watch_only",
        "title": "Der Forecast ist nutzbar, die kommerzielle Validierung steht aber noch aus.",
        "body": "Nutze die aktuelle Verteilung als Szenario-Split für die Planung und erkläre, dass GELO-Outcome-Daten später die kommerzielle Validierung freischalten.",
    }
