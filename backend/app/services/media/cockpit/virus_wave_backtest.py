"""Research-only backtests for virusWaveTruth/evidence.

The backtest answers one narrow question before any budget logic changes:
does AMELAG + SurvStat detect wave timing earlier or more robustly than
SurvStat alone? Results are persisted for audit, but they are never used to
change live media budgets in v1.3.
"""

from __future__ import annotations

from datetime import date, datetime, time
import hashlib
import math
import re
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy.orm import Session

from app.models.database import (
    VirusWaveBacktestEvent,
    VirusWaveBacktestResult,
    VirusWaveBacktestRun,
)
from app.services.media.cockpit.virus_wave_truth import (
    BASE_WEIGHT_PROFILES,
    EVIDENCE_VERSION,
    align_wave_points,
    build_wave_evidence,
    compute_wave_features_from_points,
    _load_amelag_points,
    _load_survstat_points,
)


BACKTEST_VERSION = "virus-wave-backtest-v1.7"
LEGACY_SCOPES = ["Influenza A", "Influenza B", "RSV A", "SARS-CoV-2"]
CANONICAL_COMPARISON_SCOPES = ["Influenza A+B", "RSV", "SARS-CoV-2"]
DEFAULT_SCOPES = list(CANONICAL_COMPARISON_SCOPES)
BACKTEST_MODES = {"historical_cutoff", "retrospective_descriptive"}
MODEL_SURVSTAT_ONLY = "survstat_only"
MODEL_AMELAG_ONLY = "amelag_only"
MODEL_STATIC_COMBO = "static_amelag_survstat_combo"
MODEL_EVIDENCE_WEIGHTED = "evidence_v1_1_quality_weighted"
BASELINE_MODELS = [MODEL_SURVSTAT_ONLY]
CANDIDATE_MODELS = [MODEL_AMELAG_ONLY, MODEL_STATIC_COMBO, MODEL_EVIDENCE_WEIGHTED]
ALL_MODELS = [MODEL_SURVSTAT_ONLY, *CANDIDATE_MODELS]
MIN_SEASON_SOURCE_POINTS = 8
MIN_SEASON_SPAN_DAYS = 70


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value[:10]).date()
    raise TypeError(f"Unsupported date value: {value!r}")


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            try:
                return datetime.combine(date.fromisoformat(text[:10]), time.min)
            except ValueError:
                return None
    return None


def _iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, 6)


def _season_for_dates(dates: Iterable[date]) -> str | None:
    clean = sorted(dates)
    if not clean:
        return None
    reference = clean[-1]
    start_year = reference.year if reference.month >= 7 else reference.year - 1
    return f"{start_year}_{start_year + 1}"


def _epi_season_for_date(value: date) -> str:
    start_year = value.year if value.month >= 7 else value.year - 1
    return f"{start_year}_{start_year + 1}"


def _season_bounds(season: str) -> tuple[date, date]:
    try:
        start_year_text, end_year_text = season.split("_", 1)
        start_year = int(start_year_text)
        end_year = int(end_year_text)
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Unsupported epidemiological season: {season!r}") from exc
    if end_year != start_year + 1:
        raise ValueError(f"Unsupported epidemiological season: {season!r}")
    return date(start_year, 7, 1), date(end_year, 6, 30)


def filter_points_to_epi_season(
    points: Iterable[Mapping[str, Any]],
    season: str,
) -> list[dict[str, Any]]:
    """Keep only points inside one July-June epidemiological season."""

    start_date, end_date = _season_bounds(season)
    filtered: list[dict[str, Any]] = []
    for point in points or []:
        try:
            point_date = _as_date(point.get("date", point.get("datum")))
        except (TypeError, ValueError):
            continue
        if start_date <= point_date <= end_date:
            item = dict(point)
            item["date"] = point_date
            filtered.append(item)
    return sorted(filtered, key=lambda item: item["date"])


def _available_epi_seasons(*point_sets: Iterable[Mapping[str, Any]]) -> list[str]:
    seasons: set[str] = set()
    for points in point_sets:
        for point in points or []:
            try:
                seasons.add(_epi_season_for_date(_as_date(point.get("date", point.get("datum")))))
            except (TypeError, ValueError):
                continue
    return sorted(seasons)


def candidate_epi_seasons_for_backtest(
    survstat_points: Iterable[Mapping[str, Any]],
    amelag_points: Iterable[Mapping[str, Any]],
    *,
    min_points_per_source: int = MIN_SEASON_SOURCE_POINTS,
    min_span_days: int = MIN_SEASON_SPAN_DAYS,
) -> list[str]:
    """Return seasons with enough source overlap for a meaningful comparison."""

    survstat_list = list(survstat_points or [])
    amelag_list = list(amelag_points or [])
    candidates = _available_epi_seasons(survstat_list, amelag_list)
    valid: list[str] = []
    for season in candidates:
        season_survstat = filter_points_to_epi_season(survstat_list, season)
        season_amelag = filter_points_to_epi_season(amelag_list, season)
        season_dates = [point["date"] for point in season_survstat] + [point["date"] for point in season_amelag]
        span_days = (max(season_dates) - min(season_dates)).days if season_dates else 0
        if len(season_survstat) >= min_points_per_source and len(season_amelag) >= min_points_per_source and span_days >= min_span_days:
            valid.append(season)
    return valid


def canonicalize_pathogen_scope(pathogen: str) -> dict[str, str | None]:
    """Return stable product-level pathogen names without losing variants."""

    original = (pathogen or "").strip()
    compact = re.sub(r"[^a-z0-9]+", " ", original.lower()).strip()
    tokens = compact.split()

    is_rsv = (
        compact == "rsv"
        or compact.startswith("rsv ")
        or "syncytial" in compact
        or "synzytial" in compact
    )
    if is_rsv:
        variant: str | None = None
        if ("a" in tokens and "b" in tokens and "rsv" in tokens) or "ab" in tokens:
            variant = None
        elif "a" in tokens and "rsv" in tokens:
            variant = "RSV A"
        elif "b" in tokens and "rsv" in tokens:
            variant = "RSV B"
        return {"pathogen": "RSV", "pathogen_variant": variant}

    aliases = {
        "sars cov 2": "SARS-CoV-2",
        "sars cov2": "SARS-CoV-2",
        "covid 19": "SARS-CoV-2",
        "influenza a": "Influenza A",
        "influenza b": "Influenza B",
        "influenza a b": "Influenza A+B",
        "influenza ab": "Influenza A+B",
    }
    return {"pathogen": aliases.get(compact, original), "pathogen_variant": None}


def _select_signal(point: Mapping[str, Any], keys: Sequence[str]) -> tuple[float, str]:
    for key in keys:
        value = _safe_float(point.get(key), float("nan"))
        if math.isfinite(value):
            return value, key
    return 0.0, "missing"


def prepare_amelag_points_for_backtest(
    points: Iterable[Mapping[str, Any]],
    *,
    mode: str,
) -> list[dict[str, Any]]:
    """Prepare AMELAG points with explicit leakage semantics."""

    if mode not in BACKTEST_MODES:
        raise ValueError(f"Unsupported virus wave backtest mode: {mode}")

    if mode == "historical_cutoff":
        signal_order = ("viruslast_normalisiert", "viruslast", "value")
        backtest_safe = True
    else:
        signal_order = ("vorhersage", "viruslast_normalisiert", "viruslast", "value")
        backtest_safe = False

    prepared: list[dict[str, Any]] = []
    for point in points or []:
        try:
            point_date = _as_date(point.get("date", point.get("datum")))
        except (TypeError, ValueError):
            continue
        value, basis = _select_signal(point, signal_order)
        item = dict(point)
        item["date"] = point_date
        item["value"] = max(value, 0.0)
        item["signal_basis"] = basis
        item["signal_mode"] = mode
        item["backtest_safe"] = backtest_safe
        prepared.append(item)
    return sorted(prepared, key=lambda item: item["date"])


def _normalise_series(points: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[date, list[float]] = {}
    for point in points or []:
        try:
            point_date = _as_date(point.get("date", point.get("datum")))
        except (TypeError, ValueError):
            continue
        value = _safe_float(point.get("value", point.get("incidence", point.get("viral_load"))), float("nan"))
        if math.isfinite(value):
            by_date.setdefault(point_date, []).append(max(value, 0.0))
    return [
        {"date": point_date, "value": sum(values) / len(values)}
        for point_date, values in sorted(by_date.items())
        if values
    ]


def _percentile(values: Sequence[float], q: float) -> float:
    clean = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not clean:
        return 0.0
    if len(clean) == 1:
        return clean[0]
    pos = _clamp(q) * (len(clean) - 1)
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return clean[lower]
    weight = pos - lower
    return clean[lower] * (1.0 - weight) + clean[upper] * weight


def _centered_median(values: Sequence[float], idx: int) -> float:
    left = max(0, idx - 1)
    right = min(len(values), idx + 2)
    return float(median(values[left:right]))


def _live_like_threshold(history: Sequence[float]) -> float:
    baseline = _percentile(history, 0.20)
    mad = float(median(abs(value - baseline) for value in history)) if history else 0.0
    return max(baseline + max(mad, 0.15), baseline * 1.35, 0.01)


def _detect_onset_live_like(points: Iterable[Mapping[str, Any]]) -> date | None:
    series = _normalise_series(points)
    if len(series) < 4:
        return None
    values = [point["value"] for point in series]
    smoothed = [_centered_median(values, idx) for idx in range(len(values))]
    for idx in range(1, len(series)):
        history = smoothed[: idx + 1]
        threshold = _live_like_threshold(history)
        if smoothed[idx - 1] >= threshold and smoothed[idx] >= threshold and smoothed[idx] >= smoothed[idx - 1]:
            return series[idx - 1]["date"]
    return None


def _detect_peak_live_like(points: Iterable[Mapping[str, Any]], *, onset: date | None = None) -> date | None:
    series = _normalise_series(points)
    if len(series) < 4:
        return None
    values = [point["value"] for point in series]
    smoothed = [_centered_median(values, idx) for idx in range(len(values))]
    start_idx = 0
    if onset is not None:
        for idx, point in enumerate(series):
            if point["date"] >= onset:
                start_idx = idx
                break
        else:
            return None
    for idx in range(max(2, start_idx + 2), len(smoothed)):
        previous = smoothed[idx - 1]
        if previous >= smoothed[idx - 2] and previous >= smoothed[idx] and smoothed[idx] <= previous * 0.95:
            return series[idx - 1]["date"]
    peak_idx = max(range(start_idx, len(smoothed)), key=lambda item: smoothed[item])
    return series[peak_idx]["date"]


def _phase_for_date(check_date: date, *, onset: date | None, peak: date | None, series_end: date | None) -> str:
    if onset is None or check_date < onset:
        return "pre_wave"
    if peak is None or check_date < peak:
        return "early_growth"
    if (check_date - peak).days <= 7:
        return "peak_plateau"
    if series_end and (series_end - check_date).days <= 7:
        return "post_wave"
    return "decline"


def _phase_accuracy(
    *,
    model_onset: date | None,
    model_peak: date | None,
    observed_onset: date | None,
    observed_peak: date | None,
    evaluation_dates: Sequence[date],
) -> float | None:
    if not evaluation_dates:
        return None
    series_end = evaluation_dates[-1]
    matches = 0
    for check_date in evaluation_dates:
        predicted = _phase_for_date(check_date, onset=model_onset, peak=model_peak, series_end=series_end)
        observed = _phase_for_date(check_date, onset=observed_onset, peak=observed_peak, series_end=series_end)
        if predicted == observed:
            matches += 1
    return matches / len(evaluation_dates)


def _first_available(*values: date | None) -> date | None:
    clean = [value for value in values if value is not None]
    return min(clean) if clean else None


def _first_peak_after_onset(onset: date | None, *values: date | None) -> date | None:
    clean = [value for value in values if value is not None and (onset is None or value >= onset)]
    return min(clean) if clean else None


def _gain_days(baseline_date: date | None, model_date: date | None) -> float | None:
    if baseline_date is None or model_date is None:
        return None
    return float((baseline_date - model_date).days)


def _mean(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _model_confidence(model_name: str, evidence: Mapping[str, Any], survstat_features: Mapping[str, Any], amelag_features: Mapping[str, Any]) -> float:
    if model_name == MODEL_SURVSTAT_ONLY:
        return _clamp(_safe_float(survstat_features.get("confidence"), 0.0))
    if model_name == MODEL_AMELAG_ONLY:
        return _clamp(_safe_float(amelag_features.get("confidence"), 0.0))
    if model_name == MODEL_EVIDENCE_WEIGHTED:
        signal = evidence.get("early_warning_signal") if isinstance(evidence.get("early_warning_signal"), Mapping) else {}
        return _clamp(_safe_float(signal.get("confidence"), 0.0))
    return _clamp(
        0.50 * _safe_float(survstat_features.get("confidence"), 0.0)
        + 0.50 * _safe_float(amelag_features.get("confidence"), 0.0)
    )


def _result_row(
    *,
    model_name: str,
    status: str,
    pathogen: str,
    canonical_pathogen: str,
    pathogen_variant: str | None,
    region: str,
    season: str | None,
    model_onset: date | None,
    model_peak: date | None,
    baseline_onset: date | None,
    baseline_peak: date | None,
    evaluation_dates: Sequence[date],
    alignment: Mapping[str, Any],
    confidence: float,
) -> dict[str, Any]:
    has_observed_wave = baseline_onset is not None
    has_model_wave = model_onset is not None
    false_warning = 1.0 if has_model_wave and not has_observed_wave else 0.0
    missed_wave = 1.0 if has_observed_wave and not has_model_wave else 0.0
    false_post_peak = 0.0
    if baseline_peak and model_peak and model_peak < baseline_peak and (baseline_peak - model_peak).days > 28:
        false_post_peak = 1.0

    lead_lag_days = alignment.get("lead_lag_days")
    lead_lag_stability = None
    if lead_lag_days is not None:
        lead_lag_stability = _clamp(1.0 - abs(_safe_float(lead_lag_days)) / 56.0)
    observed_active = 1.0 if has_observed_wave else 0.0
    brier = (confidence - observed_active) ** 2

    return {
        "pathogen": pathogen,
        "canonical_pathogen": canonical_pathogen,
        "pathogen_variant": pathogen_variant,
        "region_code": region,
        "season": season,
        "model_name": model_name,
        "status": status,
        "onset_detection_gain_days": _round_metric(_gain_days(baseline_onset, model_onset)),
        "peak_detection_gain_days": _round_metric(_gain_days(baseline_peak, model_peak)),
        "phase_accuracy": _round_metric(
            _phase_accuracy(
                model_onset=model_onset,
                model_peak=model_peak,
                observed_onset=baseline_onset,
                observed_peak=baseline_peak,
                evaluation_dates=evaluation_dates,
            )
        ),
        "false_early_warning_rate": _round_metric(false_warning),
        "missed_wave_rate": _round_metric(missed_wave),
        "false_post_peak_rate": _round_metric(false_post_peak),
        "lead_lag_stability": _round_metric(lead_lag_stability),
        "mean_alignment_score": _round_metric(_safe_float(alignment.get("alignment_score"), float("nan"))),
        "mean_divergence_score": _round_metric(_safe_float(alignment.get("divergence_score"), float("nan"))),
        "confidence_brier_score": _round_metric(brier),
        "summary_json": {
            "model_onset_date": _iso(model_onset),
            "model_peak_date": _iso(model_peak),
            "baseline_onset_date": _iso(baseline_onset),
            "baseline_peak_date": _iso(baseline_peak),
            "mode": "diagnostic_only",
            "budget_can_change": False,
        },
    }


def _event_rows(
    *,
    result: Mapping[str, Any],
    model_onset: date | None,
    model_peak: date | None,
    survstat_features: Mapping[str, Any],
    amelag_features: Mapping[str, Any],
    alignment: Mapping[str, Any],
    confidence: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    common = {
        "pathogen": result["pathogen"],
        "canonical_pathogen": result["canonical_pathogen"],
        "pathogen_variant": result.get("pathogen_variant"),
        "region_code": result["region_code"],
        "season": result.get("season"),
        "model_name": result["model_name"],
        "survstat_phase": survstat_features.get("phase"),
        "amelag_phase": amelag_features.get("phase"),
        "lead_lag_days": alignment.get("lead_lag_days"),
        "confidence_score": round(confidence, 6),
    }
    if model_onset:
        rows.append(
            {
                **common,
                "event_type": "onset",
                "event_date": model_onset.isoformat(),
                "predicted_phase": "early_growth",
                "observed_phase": survstat_features.get("phase"),
                "details_json": dict(result.get("summary_json") or {}),
            }
        )
    if model_peak:
        rows.append(
            {
                **common,
                "event_type": "peak",
                "event_date": model_peak.isoformat(),
                "predicted_phase": "peak_plateau",
                "observed_phase": survstat_features.get("phase"),
                "details_json": dict(result.get("summary_json") or {}),
            }
        )
    return rows


def _default_clinical_anchor(pathogen: str) -> str:
    if pathogen in {"Influenza A", "Influenza B", "Influenza A+B"}:
        return "combined_influenza_survstat"
    if pathogen in {"RSV", "RSV A", "RSV B"}:
        return "rsv_survstat"
    if pathogen == "SARS-CoV-2":
        return "covid_survstat"
    return "survstat"


def _default_amelag_scope(pathogen: str) -> str:
    if pathogen == "RSV":
        return "RSV A+B"
    return pathogen


def _method_flags(
    *,
    pathogen: str,
    canonical_pathogen: str,
    pathogen_variant: str | None,
    clinical_anchor: str,
    amelag_scope: str | None,
    scope_mode: str | None,
    season: str | None,
    model_dates: Mapping[str, tuple[str, date | None, date | None]],
) -> dict[str, Any]:
    warnings: list[str] = []
    if pathogen in {"Influenza A", "Influenza B"} and clinical_anchor == "combined_influenza_survstat":
        warnings.append("subtype_specific_amelag_vs_combined_clinical_anchor")
    if canonical_pathogen == "RSV" and pathogen_variant and amelag_scope not in {"RSV A+B", "RSV A/B", "RSV"}:
        warnings.append("rsv_variant_scope_requires_review")
    peak_before_onset = any(
        onset is not None and peak is not None and peak < onset
        for _status, onset, peak in model_dates.values()
    )
    if peak_before_onset:
        warnings.append("peak_before_onset_detected")
    return {
        "version": "backtest_method_flags_v1.7",
        "scope_mode": scope_mode or "manual",
        "comparison_pair": f"{amelag_scope or pathogen}_to_{clinical_anchor}",
        "season_windowed": season is not None,
        "peak_after_onset_enforced": True,
        "peak_before_onset_detected": peak_before_onset,
        "clinical_anchor": clinical_anchor,
        "amelag_scope": amelag_scope,
        "requires_anchor_review": any(
            warning in warnings
            for warning in (
                "subtype_specific_amelag_vs_combined_clinical_anchor",
                "rsv_variant_scope_requires_review",
            )
        ),
        "warnings": list(dict.fromkeys(warnings)),
    }


def run_wave_backtest_from_points(
    *,
    pathogen: str,
    region: str,
    survstat_points: Iterable[Mapping[str, Any]],
    amelag_points: Iterable[Mapping[str, Any]],
    mode: str = "historical_cutoff",
    season: str | None = None,
    clinical_anchor: str | None = None,
    amelag_scope: str | None = None,
    scope_mode: str | None = None,
) -> dict[str, Any]:
    """Run one diagnostic backtest from already-loaded SurvStat/AMELAG points."""

    if mode not in BACKTEST_MODES:
        raise ValueError(f"Unsupported virus wave backtest mode: {mode}")

    canonical = canonicalize_pathogen_scope(pathogen)
    canonical_pathogen = str(canonical["pathogen"])
    pathogen_variant = canonical["pathogen_variant"]
    raw_survstat_points = list(survstat_points or [])
    raw_amelag_points = list(amelag_points or [])
    if season:
        raw_survstat_points = filter_points_to_epi_season(raw_survstat_points, season)
        raw_amelag_points = filter_points_to_epi_season(raw_amelag_points, season)
    survstat_series = _normalise_series(raw_survstat_points)
    amelag_series = prepare_amelag_points_for_backtest(raw_amelag_points, mode=mode)
    all_dates = [item["date"] for item in survstat_series] + [item["date"] for item in amelag_series]
    season = season or _season_for_dates(all_dates)
    season_window_span_days = (max(all_dates) - min(all_dates)).days if all_dates else 0
    clinical_anchor = clinical_anchor or _default_clinical_anchor(pathogen)
    amelag_scope = amelag_scope or _default_amelag_scope(pathogen)
    evaluation_dates = sorted({item["date"] for item in survstat_series})

    survstat_features = compute_wave_features_from_points(
        survstat_series,
        source="survstat",
        virus_typ=pathogen,
        region=region,
    )
    amelag_features = compute_wave_features_from_points(
        amelag_series,
        source="amelag",
        virus_typ=pathogen,
        region=region,
    )
    alignment = align_wave_points(
        survstat_points=survstat_series,
        amelag_points=amelag_series,
        survstat_features=survstat_features,
        amelag_features=amelag_features,
    )
    reference_date = max(all_dates) if all_dates else datetime.utcnow().date()
    evidence = build_wave_evidence(
        survstat_features=survstat_features,
        amelag_features=amelag_features,
        alignment=alignment,
        amelag_points=amelag_series,
        reference_date=reference_date,
    )

    surv_onset = _detect_onset_live_like(survstat_series)
    surv_peak = _detect_peak_live_like(survstat_series, onset=surv_onset)
    amelag_onset = _detect_onset_live_like(amelag_series)
    amelag_peak = _detect_peak_live_like(amelag_series, onset=amelag_onset)
    static_onset = _first_available(amelag_onset, surv_onset)
    evidence_onset = _first_available(amelag_onset, surv_onset) if amelag_series else None

    model_dates: dict[str, tuple[str, date | None, date | None]] = {
        MODEL_SURVSTAT_ONLY: (
            "ok" if survstat_features.get("status") == "ok" else "insufficient_data",
            surv_onset,
            surv_peak,
        ),
        MODEL_AMELAG_ONLY: (
            "ok" if amelag_features.get("status") == "ok" and amelag_series else "insufficient_data",
            amelag_onset,
            amelag_peak,
        ),
        MODEL_STATIC_COMBO: (
            "ok" if (survstat_features.get("status") == "ok" or amelag_features.get("status") == "ok") else "insufficient_data",
            static_onset,
            _first_peak_after_onset(static_onset, amelag_peak, surv_peak),
        ),
        MODEL_EVIDENCE_WEIGHTED: (
            "ok" if amelag_features.get("status") == "ok" and amelag_series else "insufficient_data",
            evidence_onset,
            _first_peak_after_onset(evidence_onset, amelag_peak, surv_peak) if amelag_series else None,
        ),
    }
    method_flags = _method_flags(
        pathogen=pathogen,
        canonical_pathogen=canonical_pathogen,
        pathogen_variant=pathogen_variant,
        clinical_anchor=clinical_anchor,
        amelag_scope=amelag_scope,
        scope_mode=scope_mode,
        season=season,
        model_dates=model_dates,
    )

    results: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for model_name in ALL_MODELS:
        status, model_onset, model_peak = model_dates[model_name]
        confidence = _model_confidence(model_name, evidence, survstat_features, amelag_features)
        result = _result_row(
            model_name=model_name,
            status=status,
            pathogen=pathogen,
            canonical_pathogen=canonical_pathogen,
            pathogen_variant=pathogen_variant,
            region=region,
            season=season,
            model_onset=model_onset if status == "ok" else None,
            model_peak=model_peak if status == "ok" else None,
            baseline_onset=surv_onset,
            baseline_peak=surv_peak,
            evaluation_dates=evaluation_dates,
            alignment=alignment,
            confidence=confidence,
        )
        results.append(result)
        events.extend(
            _event_rows(
                result=result,
                model_onset=model_onset if status == "ok" else None,
                model_peak=model_peak if status == "ok" else None,
                survstat_features=survstat_features,
                amelag_features=amelag_features,
                alignment=alignment,
                confidence=confidence,
            )
        )

    return {
        "schema": "virus_wave_backtest_v1",
        "algorithm_version": EVIDENCE_VERSION,
        "backtest_version": BACKTEST_VERSION,
        "mode": mode,
        "scope_mode": scope_mode or "manual",
        "backtest_safe": mode == "historical_cutoff",
        "pathogen": pathogen,
        "canonical_pathogen": canonical_pathogen,
        "pathogen_variant": pathogen_variant,
        "clinical_anchor": clinical_anchor,
        "amelag_scope": amelag_scope,
        "region": region,
        "season": season,
        "baseline_models": list(BASELINE_MODELS),
        "candidate_models": list(CANDIDATE_MODELS),
        "budget_impact": {
            "mode": "diagnostic_only",
            "can_change_budget": False,
            "reason": "backtest_research_only",
        },
        "source_status": {
            "survstat_points": len(survstat_series),
            "amelag_points": len(amelag_series),
            "amelag_signal_basis": sorted({str(item.get("signal_basis")) for item in amelag_series}),
            "amelag_backtest_safe": mode == "historical_cutoff",
            "clinical_anchor": clinical_anchor,
            "amelag_scope": amelag_scope,
            "scope_mode": scope_mode or "manual",
            "season_windowed": method_flags["season_windowed"],
            "season_window_span_days": season_window_span_days,
        },
        "method_flags": method_flags,
        "survstat": survstat_features,
        "amelag": amelag_features,
        "alignment": alignment,
        "evidence": {
            "mode": evidence.get("mode"),
            "weight_profiles": evidence.get("weight_profiles"),
            "budget_impact": evidence.get("budget_impact"),
            "base_weight_profiles": BASE_WEIGHT_PROFILES,
        },
        "results": results,
        "events": events,
    }


def _run_key_for_report(report: Mapping[str, Any]) -> str:
    parts = [
        str(report.get("backtest_version") or BACKTEST_VERSION),
        str(report.get("algorithm_version") or EVIDENCE_VERSION),
        str(report.get("mode") or "historical_cutoff"),
        str(report.get("scope_mode") or "manual"),
        str(report.get("pathogen") or "unknown"),
        str(report.get("region") or "DE"),
        str(report.get("season") or "unseasoned"),
        str(report.get("source_status", {}).get("survstat_points") if isinstance(report.get("source_status"), Mapping) else ""),
        str(report.get("source_status", {}).get("amelag_points") if isinstance(report.get("source_status"), Mapping) else ""),
    ]
    digest = hashlib.blake2b("|".join(parts).encode("utf-8"), digest_size=12).hexdigest()
    return f"virus-wave-backtest:{parts[2]}:{parts[3]}:{parts[4]}:{parts[5]}:{digest}"


def persist_virus_wave_backtest_report(
    db: Session,
    report: Mapping[str, Any],
    *,
    computed_at: datetime | None = None,
) -> dict[str, Any]:
    """Persist one backtest report idempotently."""

    now = (computed_at or datetime.utcnow()).replace(tzinfo=None)
    run_key = _run_key_for_report(report)
    run = db.query(VirusWaveBacktestRun).filter(VirusWaveBacktestRun.run_key == run_key).one_or_none()
    if run is None:
        run = VirusWaveBacktestRun(
            run_key=run_key,
            algorithm_version=str(report.get("algorithm_version") or EVIDENCE_VERSION),
            backtest_version=str(report.get("backtest_version") or BACKTEST_VERSION),
            mode=str(report.get("mode") or "historical_cutoff"),
            status="success",
            started_at=now,
        )
        db.add(run)
    else:
        db.query(VirusWaveBacktestEvent).filter(VirusWaveBacktestEvent.run_id == run.id).delete(synchronize_session=False)
        db.query(VirusWaveBacktestResult).filter(VirusWaveBacktestResult.run_id == run.id).delete(synchronize_session=False)
        db.flush()

    run.algorithm_version = str(report.get("algorithm_version") or EVIDENCE_VERSION)
    run.backtest_version = str(report.get("backtest_version") or BACKTEST_VERSION)
    run.mode = str(report.get("mode") or "historical_cutoff")
    run.status = "success"
    run.started_at = now
    run.finished_at = now
    run.pathogens = [str(report.get("pathogen") or "unknown")]
    run.regions = [str(report.get("region") or "DE")]
    run.seasons = [str(report.get("season"))] if report.get("season") else []
    run.baseline_models = list(report.get("baseline_models") or BASELINE_MODELS)
    run.candidate_models = list(report.get("candidate_models") or CANDIDATE_MODELS)
    run.parameters_json = {
        "backtest_safe": bool(report.get("backtest_safe")),
        "source_status": dict(report.get("source_status") or {}),
        "method_flags": dict(report.get("method_flags") or {}),
        "budget_impact": dict(report.get("budget_impact") or {}),
        "scope_mode": str(report.get("scope_mode") or "manual"),
    }
    run.summary_json = dict(report)
    db.flush()

    for row in report.get("results") or []:
        db.add(
            VirusWaveBacktestResult(
                run_id=run.id,
                pathogen=str(row.get("pathogen") or report.get("pathogen") or ""),
                canonical_pathogen=str(row.get("canonical_pathogen") or report.get("canonical_pathogen") or ""),
                pathogen_variant=row.get("pathogen_variant"),
                region_code=str(row.get("region_code") or report.get("region") or "DE"),
                season=row.get("season") or report.get("season"),
                model_name=str(row.get("model_name") or ""),
                status=str(row.get("status") or "ok"),
                onset_detection_gain_days=_round_metric(row.get("onset_detection_gain_days")),
                peak_detection_gain_days=_round_metric(row.get("peak_detection_gain_days")),
                phase_accuracy=_round_metric(row.get("phase_accuracy")),
                false_early_warning_rate=_round_metric(row.get("false_early_warning_rate")),
                missed_wave_rate=_round_metric(row.get("missed_wave_rate")),
                false_post_peak_rate=_round_metric(row.get("false_post_peak_rate")),
                lead_lag_stability=_round_metric(row.get("lead_lag_stability")),
                mean_alignment_score=_round_metric(row.get("mean_alignment_score")),
                mean_divergence_score=_round_metric(row.get("mean_divergence_score")),
                confidence_brier_score=_round_metric(row.get("confidence_brier_score")),
                summary_json=dict(row.get("summary_json") or {}),
            )
        )

    for row in report.get("events") or []:
        lead_lag = row.get("lead_lag_days")
        db.add(
            VirusWaveBacktestEvent(
                run_id=run.id,
                pathogen=str(row.get("pathogen") or report.get("pathogen") or ""),
                canonical_pathogen=str(row.get("canonical_pathogen") or report.get("canonical_pathogen") or ""),
                pathogen_variant=row.get("pathogen_variant"),
                region_code=str(row.get("region_code") or report.get("region") or "DE"),
                season=row.get("season") or report.get("season"),
                event_type=str(row.get("event_type") or "unknown"),
                event_date=_as_datetime(row.get("event_date")),
                model_name=str(row.get("model_name") or ""),
                survstat_phase=row.get("survstat_phase"),
                amelag_phase=row.get("amelag_phase"),
                predicted_phase=row.get("predicted_phase"),
                observed_phase=row.get("observed_phase"),
                lead_lag_days=int(lead_lag) if lead_lag is not None else None,
                confidence_score=_round_metric(row.get("confidence_score")),
                details_json=dict(row.get("details_json") or {}),
            )
        )
    db.flush()
    return {"run_id": run.id, "run_key": run.run_key, "status": run.status}


def run_virus_wave_backtest(
    db: Session,
    *,
    virus_typ: str,
    region: str = "DE",
    lookback_weeks: int = 156,
    mode: str = "historical_cutoff",
    season: str | None = None,
    clinical_anchor: str | None = None,
    amelag_scope: str | None = None,
    scope_mode: str | None = None,
) -> dict[str, Any]:
    """Load source points, run one diagnostic backtest, and persist it."""

    survstat_points = _load_survstat_points(db, virus_typ=virus_typ, region=region, lookback_weeks=lookback_weeks)
    amelag_points = _load_amelag_points(db, virus_typ=virus_typ, lookback_weeks=lookback_weeks)
    report = run_wave_backtest_from_points(
        pathogen=virus_typ,
        region=region,
        survstat_points=survstat_points,
        amelag_points=amelag_points,
        mode=mode,
        season=season,
        clinical_anchor=clinical_anchor,
        amelag_scope=amelag_scope,
        scope_mode=scope_mode,
    )
    persisted = persist_virus_wave_backtest_report(db, report)
    return {**persisted, "virus": virus_typ, "region": region, "report": report}


def run_all_virus_wave_backtests(
    db: Session,
    *,
    virus_types: list[str] | None = None,
    region: str = "DE",
    lookback_weeks: int = 156,
    mode: str = "historical_cutoff",
    seasonal_windows: bool = True,
    scope_mode: str = "canonical",
) -> dict[str, Any]:
    """Manual trigger helper for research-only virus wave backtests."""

    if virus_types:
        scopes = list(virus_types)
    elif scope_mode == "legacy":
        scopes = list(LEGACY_SCOPES)
    else:
        scopes = list(CANONICAL_COMPARISON_SCOPES)
    results: list[dict[str, Any]] = []
    for virus_typ in scopes:
        if not seasonal_windows:
            results.append(
                run_virus_wave_backtest(
                    db,
                    virus_typ=virus_typ,
                    region=region,
                    lookback_weeks=lookback_weeks,
                    mode=mode,
                    scope_mode=scope_mode,
                )
            )
            continue
        survstat_points = _load_survstat_points(db, virus_typ=virus_typ, region=region, lookback_weeks=lookback_weeks)
        amelag_points = _load_amelag_points(db, virus_typ=virus_typ, lookback_weeks=lookback_weeks)
        for season in candidate_epi_seasons_for_backtest(survstat_points, amelag_points):
            report = run_wave_backtest_from_points(
                pathogen=virus_typ,
                region=region,
                survstat_points=survstat_points,
                amelag_points=amelag_points,
                mode=mode,
                season=season,
                scope_mode=scope_mode,
            )
            persisted = persist_virus_wave_backtest_report(db, report)
            results.append({**persisted, "virus": virus_typ, "region": region, "report": report})
    return {
        "status": "success",
        "mode": mode,
        "scope_mode": scope_mode,
        "backtest_safe": mode == "historical_cutoff",
        "seasonal_windows": bool(seasonal_windows),
        "budget_impact": {
            "mode": "diagnostic_only",
            "can_change_budget": False,
            "reason": "backtest_research_only",
        },
        "count": len(results),
        "runs": [
            {
                "virus": row["virus"],
                "region": row["region"],
                "run_id": row["run_id"],
                "run_key": row["run_key"],
                "status": row["status"],
                "results": row["report"].get("results"),
            }
            for row in results
        ],
    }
