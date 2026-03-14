from __future__ import annotations

from typing import Any


_FEATURE_FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AMELAG-Lags", ("amelag_",)),
    ("Cross-Disease-Lags", ("xdisease_",)),
    ("SurvStat-Lags", ("survstat_",)),
    ("Google Trends", ("trends_score",)),
    ("Schulferien", ("schulferien",)),
    ("Interne Historie", ("lab_",)),
    ("Wetter-Kontext", ("weather_", "temperatur", "luftfeuchtigkeit", "humidity", "uv_")),
)


def infer_feature_families(feature_names: list[Any] | tuple[Any, ...] | set[Any] | None) -> list[str]:
    normalized = {
        str(name).strip().lower()
        for name in (feature_names or [])
        if str(name).strip()
    }
    families: list[str] = []
    for label, prefixes in _FEATURE_FAMILY_RULES:
        if any(
            feature == prefix or feature.startswith(prefix)
            for prefix in prefixes
            for feature in normalized
        ):
            families.append(label)
    return families


def normalize_confidence_pct(raw_confidence: Any) -> float | None:
    if raw_confidence is None:
        return None
    try:
        parsed = float(raw_confidence)
    except (TypeError, ValueError):
        return None
    if parsed <= 1.0:
        parsed = parsed * 100.0
    return round(max(0.0, min(100.0, parsed)), 1)


def build_metric_contract(
    *,
    label: str,
    semantics: str,
    source: str,
    unit: str,
    calibrated: bool,
    derived_from: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    contract = {
        "label": label,
        "semantics": semantics,
        "source": source,
        "unit": unit,
        "calibrated": calibrated,
    }
    if derived_from:
        contract["derived_from"] = derived_from
    if note:
        contract["note"] = note
    return contract


def forecast_probability_contract(*, source: str = "ForecastDecisionService") -> dict[str, Any]:
    return build_metric_contract(
        label="Event-Wahrscheinlichkeit",
        semantics="forecast_event_probability",
        source=source,
        unit="ratio",
        calibrated=True,
        derived_from="forecast_quality + event_calibration",
        note="Nur fuer kalibrierte Forecast-Ereignisse verwenden.",
    )


def ranking_signal_contract(*, source: str, label: str = "Signal-Score") -> dict[str, Any]:
    return build_metric_contract(
        label=label,
        semantics="ranking_signal",
        source=source,
        unit="score_0_100",
        calibrated=False,
        derived_from="heuristische oder komposite Signalaggregation",
        note="Ranking- oder Priorisierungssignal, keine Eintrittswahrscheinlichkeit.",
    )


def priority_score_contract(*, source: str) -> dict[str, Any]:
    return build_metric_contract(
        label="Priority-Score",
        semantics="activation_priority",
        source=source,
        unit="score_0_100",
        calibrated=False,
        derived_from="Decision Policy / Opportunity Ranking",
        note="Nur fuer Aktivierungsreihenfolge, nicht fuer Wahrscheinlichkeitsinterpretation.",
    )


def signal_confidence_contract(*, source: str, derived_from: str) -> dict[str, Any]:
    return build_metric_contract(
        label="Signal-Konfidenz",
        semantics="signal_confidence",
        source=source,
        unit="pct",
        calibrated=False,
        derived_from=derived_from,
        note="Agreement- oder Signalsicherheit; keine kalibrierte Modellwahrscheinlichkeit.",
    )


def truth_readiness_contract(*, source: str = "MediaOutcomeRecord") -> dict[str, Any]:
    return build_metric_contract(
        label="Truth-Readiness",
        semantics="truth_readiness",
        source=source,
        unit="state",
        calibrated=False,
        derived_from="coverage_weeks + freshness + required_fields + conversion_fields",
        note="Beschreibt, wie belastbar der Outcome-Layer bereits angeschlossen ist.",
    )


def business_gate_contract(*, source: str = "BusinessValidationService") -> dict[str, Any]:
    return build_metric_contract(
        label="Business-Gate",
        semantics="business_validation_gate",
        source=source,
        unit="state",
        calibrated=False,
        derived_from="truth_readiness + activation_cycles + holdout_design + lift_validation",
        note="Beschreibt, ob epidemiologische Empfehlungen bereits als kommerziell validierte Budget-Entscheidung gelten duerfen.",
    )


def evidence_tier_contract(*, source: str = "BusinessValidationService") -> dict[str, Any]:
    return build_metric_contract(
        label="Evidenz-Tier",
        semantics="business_evidence_tier",
        source=source,
        unit="state",
        calibrated=False,
        derived_from="truth_coverage + holdout_setup + validated_lift",
        note="Ordnet den Reifegrad der Outcome- und Business-Validierung ein.",
    )


def outcome_signal_contract(*, source: str = "OutcomeSignalService") -> dict[str, Any]:
    return build_metric_contract(
        label="Outcome-Score",
        semantics="observed_outcome_signal",
        source=source,
        unit="score_0_100",
        calibrated=False,
        derived_from="observed outcome response over media spend and search lift context",
        note="Beobachtetes Lernsignal aus Outcome-Daten; keine Forecast-Wahrscheinlichkeit.",
    )


def outcome_confidence_contract(*, source: str = "OutcomeSignalService") -> dict[str, Any]:
    return build_metric_contract(
        label="Learning-Konfidenz",
        semantics="outcome_learning_confidence",
        source=source,
        unit="pct",
        calibrated=False,
        derived_from="coverage_weeks + outcome_rows + spend_coverage + freshness",
        note="Sicherheit des beobachteten Outcome-Lernsignals, nicht Modellkalibrierung.",
    )
