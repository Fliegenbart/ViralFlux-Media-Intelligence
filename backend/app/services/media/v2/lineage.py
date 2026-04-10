from __future__ import annotations
from app.core.time import utc_now

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func

from app.models.database import BacktestRun, ForecastAccuracyLog, MLForecast, WastewaterAggregated
from app.services.media.peix_score_service import PeixEpiScoreService
from app.services.media.semantic_contracts import infer_feature_families
from app.services.ml.forecast_service import _ML_MODELS_DIR, _virus_slug

SIGNAL_GROUPS: dict[str, dict[str, str]] = {
    "wastewater": {
        "label": "AMELAG Abwasser",
        "signal_group": "epi_core",
        "contribution_state": "core",
        "quality_note": "Zentrales epidemiologisches Primärsignal.",
    },
    "survstat": {
        "label": "RKI SurvStat",
        "signal_group": "epi_core",
        "contribution_state": "core",
        "quality_note": "IfSG-Meldedaten als zweite epidemiologische Achse.",
    },
    "are_konsultation": {
        "label": "RKI ARE",
        "signal_group": "epi_support",
        "contribution_state": "supporting",
        "quality_note": "Arztkonsultationen als Belastungs- und Validierungssignal.",
    },
    "notaufnahme": {
        "label": "Notaufnahme",
        "signal_group": "epi_support",
        "contribution_state": "supporting",
        "quality_note": "Kurzfristiger Morbiditätsdruck aus AKTIN/RKI.",
    },
    "google_trends": {
        "label": "Google Trends",
        "signal_group": "demand_context",
        "contribution_state": "context",
        "quality_note": "Suchverhalten als Nachfrage- und Aufmerksamkeitskontext.",
    },
    "weather": {
        "label": "Wetter",
        "signal_group": "context",
        "contribution_state": "context",
        "quality_note": "Wetterdruck als Verstärker, nicht als Primärsignal.",
    },
    "bfarm_shortage": {
        "label": "BfArM Engpässe",
        "signal_group": "supply_context",
        "contribution_state": "context",
        "quality_note": "Versorgungssignal, kein epidemiologischer Beweis.",
    },
}

CORE_SIGNAL_KEYS = {"wastewater", "survstat", "are_konsultation", "notaufnahme"}


def build_signal_stack_payload(service, *, virus_typ: str = "Influenza A") -> dict[str, Any]:
    cockpit = service.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source="RKI_ARE")
    data_freshness = cockpit.get("data_freshness") or {}
    source_status_items = {
        item.get("source_key"): item
        for item in (cockpit.get("source_status") or {}).get("items", [])
    }
    peix = cockpit.get("peix_epi_score") or PeixEpiScoreService(service.db).build(virus_typ=virus_typ)
    signal_groups = service._signal_group_summary(peix)
    model_lineage = service.get_model_lineage(virus_typ=virus_typ)

    items = []
    for source_key, meta in SIGNAL_GROUPS.items():
        status_item = source_status_items.get(source_key) or {}
        last_available_at = data_freshness.get(source_key)
        coverage_state = "covered" if last_available_at else "missing"
        if status_item.get("freshness_state") == "stale":
            coverage_state = "stale"
        items.append({
            "source_key": source_key,
            "label": meta["label"],
            "signal_group": meta["signal_group"],
            "last_available_at": last_available_at,
            "freshness_state": status_item.get("freshness_state") or "no_data",
            "coverage_state": coverage_state,
            "quality_note": meta["quality_note"],
            "contribution_state": meta["contribution_state"],
            "is_core_signal": source_key in CORE_SIGNAL_KEYS,
        })

    items.sort(key=lambda item: (not item["is_core_signal"], item["label"]))
    summary = {
        "peix_epi_score": peix.get("national_score"),
        "national_band": peix.get("national_band"),
        "top_drivers": peix.get("top_drivers") or [],
        "context_signals": peix.get("context_signals") or {},
        "math_stack": {
            "base_models": ["Holt-Winters", "Ridge", "Prophet"],
            "meta_learner": "XGBoost",
            "feature_families": model_lineage.get("feature_families") or [],
        },
        **signal_groups,
    }
    return {
        "virus_typ": virus_typ,
        "generated_at": utc_now().isoformat(),
        "items": items,
        "summary": summary,
    }


def build_model_lineage_payload(service, *, virus_typ: str = "Influenza A") -> dict[str, Any]:
    latest_forecast = (
        service.db.query(MLForecast)
        .filter(MLForecast.virus_typ == virus_typ)
        .order_by(MLForecast.created_at.desc())
        .first()
    )
    latest_market = (
        service.db.query(BacktestRun)
        .filter(
            BacktestRun.mode == "MARKET_CHECK",
            BacktestRun.virus_typ == virus_typ,
        )
        .order_by(BacktestRun.created_at.desc())
        .first()
    )
    latest_accuracy = (
        service.db.query(ForecastAccuracyLog)
        .filter(ForecastAccuracyLog.virus_typ == virus_typ)
        .order_by(ForecastAccuracyLog.computed_at.desc())
        .first()
    )
    training_window = service.db.query(
        func.min(WastewaterAggregated.datum),
        func.max(WastewaterAggregated.datum),
        func.count(WastewaterAggregated.id),
    ).filter(WastewaterAggregated.virus_typ == virus_typ).first()

    metadata = service._read_model_metadata(virus_typ)
    feature_names = metadata.get("feature_names") or (latest_forecast.features_used if latest_forecast else []) or []
    feature_families = infer_feature_families(feature_names)
    drift_state = "warning" if bool(getattr(latest_accuracy, "drift_detected", False)) else ("ok" if latest_accuracy else "unknown")
    coverage_limits: list[str] = []
    training_samples = int(metadata.get("training_samples") or 0)
    if training_samples and training_samples < 52:
        coverage_limits.append("Trainingsfenster ist noch relativ kurz.")
    if latest_accuracy and (latest_accuracy.samples or 0) < 14:
        coverage_limits.append("Die Vorhersagegenauigkeit basiert noch auf einem kleinen Monitoring-Fenster.")
    if not metadata:
        coverage_limits.append("Kein serialisiertes Modell-Metadata gefunden.")

    return {
        "virus_typ": virus_typ,
        "model_family": "stacking_forecast",
        "base_estimators": ["Holt-Winters", "Ridge", "Prophet"],
        "meta_learner": "XGBoost",
        "model_version": metadata.get("version") or (latest_forecast.model_version if latest_forecast else None) or "unbekannt",
        "trained_at": metadata.get("trained_at"),
        "feature_set_version": f"meta_{len(feature_names)}",
        "feature_names": feature_names,
        "feature_families": feature_families,
        "training_window": {
            "start": training_window[0].isoformat() if training_window and training_window[0] else None,
            "end": training_window[1].isoformat() if training_window and training_window[1] else None,
            "points": int(training_window[2] or 0) if training_window else 0,
        },
        "drift_state": drift_state,
        "coverage_limits": coverage_limits,
        "forecast_quality": (latest_market.metrics or {}).get("quality_gate") if latest_market else None,
        "latest_accuracy": {
            "computed_at": latest_accuracy.computed_at.isoformat() if latest_accuracy and latest_accuracy.computed_at else None,
            "samples": latest_accuracy.samples if latest_accuracy else None,
            "mape": latest_accuracy.mape if latest_accuracy else None,
            "rmse": latest_accuracy.rmse if latest_accuracy else None,
            "correlation": latest_accuracy.correlation if latest_accuracy else None,
        },
        "latest_forecast_created_at": latest_forecast.created_at.isoformat() if latest_forecast and latest_forecast.created_at else None,
    }


def _signal_group_summary(service, peix: dict[str, Any]) -> dict[str, Any]:
    virus_scores = peix.get("virus_scores") or {}
    context_signals = peix.get("context_signals") or {}

    epidemic_core = round(sum(float(item.get("contribution") or 0.0) for item in virus_scores.values()), 1)
    forecast_contribution = round(float((context_signals.get("forecast") or {}).get("contribution") or 0.0), 1)
    supply_contribution = round(float((context_signals.get("shortage") or {}).get("contribution") or 0.0), 1)
    context_contribution = round(sum(
        float((context_signals.get(key) or {}).get("contribution") or 0.0)
        for key in ("weather", "search", "baseline")
    ), 1)

    decision_mode = service._decision_mode_from_contributions(
        epidemic_total=epidemic_core + forecast_contribution,
        supply_total=supply_contribution,
        context_total=context_contribution,
    )
    return {
        "driver_groups": {
            "epidemic_core": {"label": "Epi-Kern", "contribution": epidemic_core},
            "forecast_model": {"label": "Vorhersage", "contribution": forecast_contribution},
            "supply_window": {"label": "Versorgung", "contribution": supply_contribution},
            "context_window": {"label": "Wetter und Grundrauschen", "contribution": context_contribution},
        },
        "decision_mode": decision_mode["key"],
        "decision_mode_label": decision_mode["label"],
        "decision_mode_reason": decision_mode["reason"],
    }


def _decision_mode_from_contributions(
    service,
    *,
    epidemic_total: float,
    supply_total: float,
    context_total: float,
) -> dict[str, str]:
    if supply_total >= max(8.0, epidemic_total * 0.7):
        return {
            "key": "supply_window",
            "label": "Versorgungsfenster",
            "reason": "Das aktuelle Signal wird vor allem durch Versorgung und Kontext getrieben, nicht durch eine reine Wellenbeschleunigung.",
        }
    if supply_total >= 4.0 and (supply_total + context_total) >= epidemic_total:
        return {
            "key": "mixed",
            "label": "Gemischtes Signal",
            "reason": "Epi-Kern, Vorhersage und Kontext zeigen gleichzeitig nach oben. Die Entscheidung bleibt deshalb bewusst defensiv.",
        }
    return {
        "key": "epidemic_wave",
        "label": "Atemwegswelle",
        "reason": "AMELAG, SurvStat und Vorhersage tragen die Entscheidung. Versorgung bleibt Zusatzsignal, nicht Hauptbeweis.",
    }


def _read_model_metadata(service, virus_typ: str) -> dict[str, Any]:
    slug = _virus_slug(virus_typ)
    metadata_path = Path(_ML_MODELS_DIR) / slug / "metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
