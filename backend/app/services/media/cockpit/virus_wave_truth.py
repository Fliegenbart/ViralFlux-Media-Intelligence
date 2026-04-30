"""Runtime SurvStat/AMELAG wave truth diagnostics.

This module computes a small, auditable wave layer from the existing raw
SurvStat and AMELAG tables. It intentionally does not write decisions or budget
rules; it only exposes epidemiological wave features that downstream layers can
inspect.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import math
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import func

from app.models.database import SurvstatKreisData, SurvstatWeeklyData, WastewaterAggregated

SCHEMA_VERSION = "virus_wave_truth_v1"
ENGINE_VERSION = "virus_wave_truth_runtime_v1_1"
EVIDENCE_VERSION = "virus-wave-evidence-runtime-v1.1"

SOURCE_ROLES: dict[str, str] = {
    "amelag": "early_warning_trend_signal",
    "survstat": "confirmed_reporting_signal",
    "syndromic": "planned_population_symptom_signal",
    "severity": "planned_healthcare_burden_signal",
}

BASE_WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "early_warning": {
        "amelag": 0.65,
        "survstat": 0.20,
        "syndromic": 0.15,
        "severity": 0.00,
    },
    "phase_detection": {
        "amelag": 0.50,
        "survstat": 0.35,
        "syndromic": 0.15,
        "severity": 0.00,
    },
    "confirmed_burden": {
        "amelag": 0.15,
        "survstat": 0.45,
        "syndromic": 0.25,
        "severity": 0.15,
    },
    "severity_pressure": {
        "amelag": 0.05,
        "survstat": 0.15,
        "syndromic": 0.20,
        "severity": 0.60,
    },
}

CONFIDENCE_INPUTS = [
    "freshness_score",
    "coverage_score",
    "site_count_score",
    "uncertainty_score",
    "alignment_score",
]

SURVSTAT_DISEASES_BY_VIRUS: dict[str, tuple[str, ...]] = {
    "Influenza A": ("influenza, saisonal",),
    "Influenza B": ("influenza, saisonal",),
    "Influenza A+B": ("influenza, saisonal",),
    "SARS-CoV-2": ("covid-19",),
    "RSV": (
        "rsv (meldepflicht gemäß ifsg)",
        "rsv (meldepflicht gemäß landesmeldeverordnung)",
    ),
    "RSV A": ("rsv (meldepflicht gemäß ifsg)",),
    "RSV A+B": (
        "rsv (meldepflicht gemäß ifsg)",
        "rsv (meldepflicht gemäß landesmeldeverordnung)",
    ),
}

AMELAG_VIRUS_BY_SCOPE: dict[str, str] = {
    "Influenza A": "Influenza A",
    "Influenza B": "Influenza B",
    "Influenza A+B": "Influenza A+B",
    "SARS-CoV-2": "SARS-CoV-2",
    "RSV": "RSV A+B",
    "RSV A": "RSV A",
    "RSV A+B": "RSV A+B",
}

BUNDESLAND_NAMES: dict[str, str] = {
    "SH": "Schleswig-Holstein",
    "HH": "Hamburg",
    "NI": "Niedersachsen",
    "HB": "Bremen",
    "NW": "Nordrhein-Westfalen",
    "HE": "Hessen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "MV": "Mecklenburg-Vorpommern",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "TH": "Thüringen",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def select_amelag_signal_basis(point: Mapping[str, Any]) -> tuple[float, str]:
    """Pick the AMELAG signal value in the documented runtime order."""

    for key in ("vorhersage", "viruslast_normalisiert", "viruslast", "value"):
        value = _safe_float(point.get(key), float("nan"))
        if math.isfinite(value):
            return value, key
    return 0.0, "missing"


def _normalise_points(points: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[date, list[float]] = {}
    for point in points or []:
        if "date" in point:
            point_date = _as_date(point["date"])
        elif "datum" in point:
            point_date = _as_date(point["datum"])
        else:
            continue
        value = _safe_float(point.get("value", point.get("incidence", point.get("viral_load"))), float("nan"))
        if not math.isfinite(value):
            continue
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
    pos = _clamp(q, 0.0, 1.0) * (len(clean) - 1)
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


def _relative_change(current: float, previous: float) -> float:
    return float((current - previous) / max(abs(previous), 1.0))


def _series_slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float((values[-1] - values[0]) / max(len(values) - 1, 1))


def _virus_slug(value: str) -> str:
    return value.lower().replace(" ", "_").replace("-", "_").replace("/", "_")


def compute_wave_features_from_points(
    points: Iterable[Mapping[str, Any]],
    *,
    source: str,
    virus_typ: str,
    region: str = "DE",
) -> dict[str, Any]:
    """Compute wave phase and strength from a single observed time series."""

    series = _normalise_points(points)
    if len(series) < 4:
        return {
            "source": source,
            "virus": virus_typ,
            "region": region,
            "status": "insufficient_data",
            "data_points": len(series),
            "phase": "unknown",
            "confidence": 0.0,
        }

    dates = [item["date"] for item in series]
    raw_values = [_safe_float(item["value"]) for item in series]
    smoothed = [_centered_median(raw_values, idx) for idx in range(len(raw_values))]
    baseline_window = smoothed[-104:] if len(smoothed) > 104 else smoothed
    baseline = _percentile(baseline_window, 0.20)
    mad = float(median(abs(value - baseline) for value in baseline_window)) if baseline_window else 0.0
    threshold = max(baseline + max(mad, 0.15) * 1.0, baseline * 1.35, 0.01)

    segments: list[tuple[int, int]] = []
    start_idx: int | None = None
    for idx, value in enumerate(smoothed):
        if value >= threshold and start_idx is None:
            start_idx = idx
        elif value < threshold and start_idx is not None:
            if idx - start_idx >= 2:
                segments.append((start_idx, idx - 1))
            start_idx = None
    if start_idx is not None and len(smoothed) - start_idx >= 2:
        segments.append((start_idx, len(smoothed) - 1))

    active_segment: tuple[int, int] | None = None
    if segments:
        if segments[-1][1] == len(smoothed) - 1:
            active_segment = segments[-1]
        elif len(smoothed) - 1 - segments[-1][1] <= 12:
            active_segment = segments[-1]

    onset_idx = active_segment[0] if active_segment is not None else None

    current = smoothed[-1]
    previous = smoothed[-2]
    prev2 = smoothed[-3] if len(smoothed) >= 3 else previous
    growth_1w = _relative_change(current, previous)
    growth_2w = _relative_change(current, prev2)
    peak_idx = max(range(len(smoothed)), key=lambda idx: smoothed[idx])
    if active_segment is not None:
        wave_peak_idx = max(range(active_segment[0], active_segment[1] + 1), key=lambda idx: smoothed[idx])
    else:
        wave_peak_idx = peak_idx

    if current < threshold:
        phase = "post_wave" if active_segment is not None else "pre_wave"
    elif growth_1w < -0.05:
        phase = "decline"
    elif abs(growth_1w) <= 0.05 and current >= 0.85 * max(smoothed):
        phase = "peak_plateau"
    else:
        phase = "early_growth"

    wave_strength = _clamp((current - baseline) / max((max(smoothed) - baseline), max(mad, 1.0), 1.0))
    freshness_days = max((datetime.utcnow().date() - dates[-1]).days, 0)
    confidence = _clamp(
        0.35
        + min(len(series), 52) / 52.0 * 0.25
        + wave_strength * 0.35
        - min(freshness_days / 120.0, 0.20)
    )
    wave_id = None
    if onset_idx is not None:
        wave_id = f"{source}_{_virus_slug(virus_typ)}_{region}_{dates[onset_idx].isoformat()}"

    return {
        "source": source,
        "virus": virus_typ,
        "region": region,
        "status": "ok",
        "data_points": len(series),
        "latest_date": dates[-1].isoformat(),
        "latest_value": round(raw_values[-1], 6),
        "smoothed_value": round(current, 6),
        "baseline": round(baseline, 6),
        "threshold": round(threshold, 6),
        "growth_rate_1w": round(growth_1w, 6),
        "growth_rate_2w": round(growth_2w, 6),
        "wave_id": wave_id,
        "phase": phase,
        "onset_date": _iso(dates[onset_idx]) if onset_idx is not None else None,
        "peak_date": dates[wave_peak_idx].isoformat(),
        "peak_intensity": round(smoothed[wave_peak_idx], 6),
        "wave_strength": round(wave_strength, 6),
        "confidence": round(confidence, 6),
    }


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _zscore_by_week(points: Iterable[Mapping[str, Any]]) -> dict[date, float]:
    series = _normalise_points(points)
    weekly: dict[date, list[float]] = {}
    for point in series:
        weekly.setdefault(_week_start(point["date"]), []).append(_safe_float(point["value"]))
    averaged = {week: sum(values) / len(values) for week, values in weekly.items() if values}
    if not averaged:
        return {}
    values = list(averaged.values())
    mean_value = sum(values) / len(values)
    variance = sum((value - mean_value) ** 2 for value in values) / max(len(values), 1)
    std = math.sqrt(variance) or 1.0
    return {week: (value - mean_value) / std for week, value in averaged.items()}


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_den = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_den = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    denominator = x_den * y_den
    if denominator <= 0.0:
        return None
    return numerator / denominator


def _parse_optional_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return _as_date(value)
    except (TypeError, ValueError):
        return None


def _phase_match_score(survstat_phase: str, amelag_phase: str) -> float:
    growth = {"early_growth", "acceleration"}
    quiet = {"pre_wave", "post_wave", "unknown"}
    if survstat_phase == amelag_phase:
        return 1.0
    if survstat_phase in growth and amelag_phase in growth:
        return 0.85
    if survstat_phase in quiet and amelag_phase in quiet:
        return 0.70
    if survstat_phase == "early_growth" and amelag_phase == "peak_plateau":
        return 0.65
    if survstat_phase == "decline" and amelag_phase == "peak_plateau":
        return 0.55
    return 0.35


def align_wave_points(
    *,
    survstat_points: Iterable[Mapping[str, Any]],
    amelag_points: Iterable[Mapping[str, Any]],
    survstat_features: Mapping[str, Any],
    amelag_features: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare SurvStat and AMELAG curves and report lead/lag diagnostics."""

    survstat_weekly = _zscore_by_week(survstat_points)
    amelag_weekly = _zscore_by_week(amelag_points)
    best_lag_days: int | None = None
    best_corr: float | None = None
    best_pairs = 0
    for lag_days in range(-42, 43, 7):
        xs: list[float] = []
        ys: list[float] = []
        for week, surv_value in survstat_weekly.items():
            amelag_value = amelag_weekly.get(week + timedelta(days=lag_days))
            if amelag_value is None:
                continue
            xs.append(surv_value)
            ys.append(amelag_value)
        corr = _pearson(xs, ys)
        if corr is None:
            continue
        if best_corr is None or corr > best_corr or (abs(corr - best_corr) < 0.000001 and abs(lag_days) < abs(best_lag_days or 999)):
            best_corr = corr
            best_lag_days = lag_days
            best_pairs = len(xs)

    surv_onset = _parse_optional_date(survstat_features.get("onset_date"))
    amelag_onset = _parse_optional_date(amelag_features.get("onset_date"))
    onset_lag_days = (amelag_onset - surv_onset).days if surv_onset and amelag_onset else None
    surv_peak = _parse_optional_date(survstat_features.get("peak_date"))
    amelag_peak = _parse_optional_date(amelag_features.get("peak_date"))
    peak_lag_days = (amelag_peak - surv_peak).days if surv_peak and amelag_peak else None
    if (
        onset_lag_days is not None
        and abs(onset_lag_days) <= 90
        and (best_lag_days is None or abs(onset_lag_days - best_lag_days) <= 21)
    ):
        lead_lag_days = onset_lag_days
    else:
        lead_lag_days = best_lag_days

    if lead_lag_days is None:
        status = "insufficient_overlap"
    elif lead_lag_days < -2:
        status = "amelag_leads_survstat"
    elif lead_lag_days > 2:
        status = "survstat_leads_amelag"
    else:
        status = "synchronized"

    phase_score = _phase_match_score(str(survstat_features.get("phase")), str(amelag_features.get("phase")))
    corr_score = _clamp(((best_corr or 0.0) + 1.0) / 2.0)
    alignment_score = _clamp(0.70 * corr_score + 0.30 * phase_score)
    latest_common_weeks = sorted(set(survstat_weekly) & set(amelag_weekly))
    if latest_common_weeks:
        latest_week = latest_common_weeks[-1]
        divergence_score = _clamp(abs(survstat_weekly[latest_week] - amelag_weekly[latest_week]) / 4.0)
    else:
        divergence_score = None

    return {
        "status": status,
        "lead_lag_days": lead_lag_days,
        "best_correlation_lag_days": best_lag_days,
        "correlation": round(best_corr, 6) if best_corr is not None else None,
        "overlap_points": best_pairs,
        "onset_lag_days": onset_lag_days,
        "peak_lag_days": peak_lag_days,
        "phase_match_score": round(phase_score, 6),
        "alignment_score": round(alignment_score, 6),
        "divergence_score": round(divergence_score, 6) if divergence_score is not None else None,
        "interpretation": _alignment_interpretation(status, lead_lag_days),
    }


def _alignment_interpretation(status: str, lead_lag_days: int | None) -> str:
    if status == "amelag_leads_survstat" and lead_lag_days is not None:
        return f"AMELAG signal leads SurvStat clinical reporting by about {abs(lead_lag_days)} days."
    if status == "survstat_leads_amelag" and lead_lag_days is not None:
        return f"SurvStat leads the AMELAG signal by about {abs(lead_lag_days)} days."
    if status == "synchronized":
        return "AMELAG and SurvStat are broadly synchronized."
    return "Not enough overlapping signal to calculate a stable lead/lag."


def _latest_point(points: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    latest_date: date | None = None
    for point in points or []:
        try:
            point_date = _as_date(point.get("date", point.get("datum")))
        except (TypeError, ValueError):
            continue
        if latest_date is None or point_date > latest_date:
            latest = dict(point)
            latest_date = point_date
    return latest


def _normalised_coverage(value: Any) -> float | None:
    coverage = _safe_float(value, float("nan"))
    if not math.isfinite(coverage):
        return None
    if coverage > 1.0:
        coverage = coverage / 100.0
    return _clamp(coverage)


def _round_score(value: float) -> float:
    return round(_clamp(value), 6)


def _amelag_lead_days_from_alignment(alignment: Mapping[str, Any]) -> int | None:
    lag = alignment.get("lead_lag_days")
    if lag is None:
        return None
    lag_days = int(_safe_float(lag))
    if lag_days < 0:
        return abs(lag_days)
    if lag_days == 0:
        return 0
    return -abs(lag_days)


def compute_amelag_quality(
    amelag_points: Iterable[Mapping[str, Any]],
    *,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Score whether AMELAG should receive its full early-signal weight."""

    points = list(amelag_points or [])
    today = reference_date or datetime.utcnow().date()
    latest = _latest_point(points)
    if latest is None:
        return {
            "freshness_score": 0.0,
            "coverage_score": 0.0,
            "site_count_score": 0.0,
            "uncertainty_score": 0.0,
            "lod_loq_score": 0.0,
            "cross_site_consistency_score": 0.0,
            "quality_multiplier": 0.0,
            "data_freshness_days": None,
            "site_count": 0,
            "population_coverage": None,
            "signal_basis": "missing",
            "signal_mode": "current_runtime",
            "backtest_safe": False,
            "quality_flags": ["amelag_no_data"],
        }

    flags: list[str] = []
    latest_date = _as_date(latest.get("date", latest.get("datum")))
    available_date = _parse_optional_date(latest.get("available_time"))
    if available_date is None:
        available_date = latest_date
        flags.append("amelag_available_time_missing")
    freshness_days = max((today - available_date).days, 0)
    freshness_score = _clamp(1.0 - freshness_days / 28.0)
    if freshness_days > 21:
        flags.append("amelag_stale")

    population_coverage = _normalised_coverage(latest.get("anteil_bev", latest.get("population_coverage")))
    if population_coverage is None:
        coverage_score = 0.55
        flags.append("amelag_population_coverage_missing")
    else:
        coverage_score = _clamp(population_coverage / 0.25)
        if population_coverage < 0.05:
            flags.append("amelag_low_population_coverage")

    site_count = _safe_int(latest.get("n_standorte", latest.get("site_count")), 0)
    if site_count <= 0:
        site_count_score = 0.50
        flags.append("amelag_site_count_missing")
    else:
        site_count_score = _clamp(site_count / 40.0)
        if site_count < 8:
            flags.append("amelag_low_site_count")

    signal_value, signal_basis = select_amelag_signal_basis(latest)
    upper = _safe_float(latest.get("obere_schranke"), float("nan"))
    lower = _safe_float(latest.get("untere_schranke"), float("nan"))
    if math.isfinite(upper) and math.isfinite(lower):
        interval_width = max(upper - lower, 0.0)
        relative_width = interval_width / max(abs(signal_value), 0.000001)
        uncertainty_score = _clamp(1.0 - relative_width / 3.0)
        if relative_width > 1.5:
            flags.append("amelag_wide_uncertainty_interval")
    else:
        uncertainty_score = 0.65
        flags.append("amelag_uncertainty_interval_missing")

    if "unter_bg" in latest:
        if bool(latest.get("unter_bg")):
            lod_loq_score = 0.25
            flags.append("amelag_lod_loq_near_or_below")
        else:
            lod_loq_score = 1.0
    else:
        lod_loq_score = 0.80
        flags.append("amelag_lod_loq_missing")

    if site_count <= 0:
        cross_site_consistency_score = 0.55
        flags.append("amelag_cross_site_consistency_unavailable")
    else:
        cross_site_consistency_score = _clamp(0.50 * site_count_score + 0.50 * uncertainty_score)

    quality_multiplier = _clamp(
        0.24 * freshness_score
        + 0.20 * coverage_score
        + 0.16 * site_count_score
        + 0.18 * uncertainty_score
        + 0.10 * lod_loq_score
        + 0.12 * cross_site_consistency_score
    )

    return {
        "freshness_score": _round_score(freshness_score),
        "coverage_score": _round_score(coverage_score),
        "site_count_score": _round_score(site_count_score),
        "uncertainty_score": _round_score(uncertainty_score),
        "lod_loq_score": _round_score(lod_loq_score),
        "cross_site_consistency_score": _round_score(cross_site_consistency_score),
        "quality_multiplier": _round_score(quality_multiplier),
        "data_freshness_days": freshness_days,
        "site_count": site_count,
        "population_coverage": round(population_coverage, 6) if population_coverage is not None else None,
        "signal_basis": signal_basis,
        "signal_mode": "current_runtime",
        "backtest_safe": False,
        "quality_flags": list(dict.fromkeys(flags)),
    }


def _source_availability(
    *,
    survstat_features: Mapping[str, Any],
    amelag_features: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "amelag": "available" if amelag_features.get("status") == "ok" else "unavailable",
        "survstat": "available" if survstat_features.get("status") == "ok" else "unavailable",
        "syndromic": "planned_unavailable",
        "severity": "planned_unavailable",
    }


def _availability_multiplier(status: str) -> float:
    return 1.0 if status == "available" else 0.0


def _survstat_quality_multiplier(features: Mapping[str, Any]) -> float:
    if features.get("status") != "ok":
        return 0.0
    confidence = _clamp(_safe_float(features.get("confidence"), 0.45))
    point_score = _clamp(_safe_float(features.get("data_points"), 0.0) / 12.0)
    return _clamp(0.20 + 0.60 * confidence + 0.20 * point_score)


def _build_weight_profiles(
    *,
    source_availability: Mapping[str, str],
    quality_multipliers: Mapping[str, float],
) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for profile_name, base_weights in BASE_WEIGHT_PROFILES.items():
        raw_weights: dict[str, float] = {}
        for source, base_weight in base_weights.items():
            raw_weights[source] = (
                base_weight
                * _clamp(_safe_float(quality_multipliers.get(source), 0.0))
                * _availability_multiplier(str(source_availability.get(source) or "unavailable"))
            )
        raw_sum = sum(raw_weights.values())
        effective_weights = {
            source: round((value / raw_sum) if raw_sum > 0.0 else 0.0, 6)
            for source, value in raw_weights.items()
        }
        profiles[profile_name] = {
            "base_weights": {source: round(value, 6) for source, value in base_weights.items()},
            "quality_multipliers": {
                source: round(_clamp(_safe_float(quality_multipliers.get(source), 0.0)), 6)
                for source in base_weights
            },
            "effective_weights": effective_weights,
            "evidence_coverage": round(raw_sum / max(sum(base_weights.values()), 0.000001), 6),
            "missing_sources": [
                source
                for source in base_weights
                if str(source_availability.get(source) or "unavailable") != "available"
            ],
        }
    return profiles


def build_wave_evidence(
    *,
    survstat_features: Mapping[str, Any],
    amelag_features: Mapping[str, Any],
    alignment: Mapping[str, Any],
    amelag_points: Iterable[Mapping[str, Any]],
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Build diagnostic source evidence without affecting budget decisions."""

    amelag_quality = compute_amelag_quality(amelag_points, reference_date=reference_date)
    source_availability = _source_availability(
        survstat_features=survstat_features,
        amelag_features=amelag_features,
    )
    quality_multipliers = {
        "amelag": _safe_float(amelag_quality.get("quality_multiplier"), 0.0),
        "survstat": _survstat_quality_multiplier(survstat_features),
        "syndromic": 0.0,
        "severity": 0.0,
    }
    weight_profiles = _build_weight_profiles(
        source_availability=source_availability,
        quality_multipliers=quality_multipliers,
    )
    early_weights = weight_profiles["early_warning"]["effective_weights"]
    early_primary = "amelag" if source_availability.get("amelag") == "available" else "survstat"
    alignment_score = _clamp(_safe_float(alignment.get("alignment_score"), 0.0))
    amelag_confidence = _clamp(
        0.40 * quality_multipliers["amelag"]
        + 0.25 * _clamp(_safe_float(amelag_features.get("confidence"), 0.0))
        + 0.20 * alignment_score
        + 0.15 * _clamp(_safe_float(early_weights.get("amelag"), 0.0))
    )
    survstat_confidence = _clamp(
        0.65 * quality_multipliers["survstat"]
        + 0.35 * _clamp(_safe_float(survstat_features.get("confidence"), 0.0))
    )

    early_phase = amelag_features.get("phase") if early_primary == "amelag" else survstat_features.get("phase")
    early_confidence = amelag_confidence if early_primary == "amelag" else survstat_confidence

    return {
        "mode": "diagnostic_only",
        "algorithm_version": EVIDENCE_VERSION,
        "source_roles": dict(SOURCE_ROLES),
        "source_availability": source_availability,
        "early_warning_signal": {
            "primary_source": early_primary,
            "phase": early_phase,
            "confidence": round(early_confidence, 6),
            "confidence_method": "heuristic_v1",
            "confidence_inputs": list(CONFIDENCE_INPUTS),
            "reason": str(alignment.get("status") or "wave_evidence_weighting"),
        },
        "confirmed_reporting_signal": {
            "primary_source": "survstat",
            "phase": survstat_features.get("phase"),
            "confidence": round(survstat_confidence, 6),
            "confidence_method": "heuristic_v1",
            "confidence_inputs": ["survstat_wave_confidence", "survstat_data_points"],
        },
        "weight_profiles": weight_profiles,
        "amelag_quality": amelag_quality,
        "budget_impact": {
            "mode": "diagnostic_only",
            "can_change_budget": False,
            "reason": "awaiting_backtest_validation",
        },
    }


def _region_name_for_query(region: str) -> str:
    if region in {"DE", "Gesamt", "Deutschland"}:
        return "Gesamt"
    return BUNDESLAND_NAMES.get(region, region)


def _load_survstat_points(db: Any, *, virus_typ: str, region: str, lookback_weeks: int) -> list[dict[str, Any]]:
    diseases = SURVSTAT_DISEASES_BY_VIRUS.get(virus_typ, ())
    if not diseases:
        return []
    start_date = datetime.utcnow() - timedelta(weeks=max(int(lookback_weeks), 12))
    query = (
        db.query(
            SurvstatWeeklyData.week_start.label("date"),
            func.avg(SurvstatWeeklyData.incidence).label("value"),
        )
        .filter(func.lower(SurvstatWeeklyData.disease).in_(list(diseases)))
            .filter(SurvstatWeeklyData.week_start >= start_date)
            .filter(SurvstatWeeklyData.week > 0)
    )
    query = query.filter(SurvstatWeeklyData.bundesland == _region_name_for_query(region))
    query = query.with_entities(
        SurvstatWeeklyData.week_start.label("date"),
        func.max(SurvstatWeeklyData.incidence).label("value"),
    )
    rows = query.group_by(SurvstatWeeklyData.week_start).order_by(SurvstatWeeklyData.week_start.asc()).all()
    return [{"date": row.date, "value": row.value} for row in rows]


def _load_amelag_points(db: Any, *, virus_typ: str, lookback_weeks: int) -> list[dict[str, Any]]:
    amelag_virus = AMELAG_VIRUS_BY_SCOPE.get(virus_typ)
    if not amelag_virus:
        return []
    start_date = datetime.utcnow() - timedelta(weeks=max(int(lookback_weeks), 12))
    rows = (
        db.query(
            WastewaterAggregated.datum.label("date"),
            func.max(WastewaterAggregated.available_time).label("available_time"),
            func.max(WastewaterAggregated.n_standorte).label("n_standorte"),
            func.max(WastewaterAggregated.anteil_bev).label("anteil_bev"),
            func.avg(WastewaterAggregated.vorhersage).label("vorhersage"),
            func.avg(WastewaterAggregated.viruslast_normalisiert).label("viruslast_normalisiert"),
            func.avg(WastewaterAggregated.viruslast).label("viruslast"),
            func.avg(WastewaterAggregated.obere_schranke).label("obere_schranke"),
            func.avg(WastewaterAggregated.untere_schranke).label("untere_schranke"),
        )
        .filter(WastewaterAggregated.virus_typ == amelag_virus)
        .filter(WastewaterAggregated.datum >= start_date)
        .group_by(WastewaterAggregated.datum)
        .order_by(WastewaterAggregated.datum.asc())
        .all()
    )
    points: list[dict[str, Any]] = []
    for row in rows:
        point = {
            "date": row.date,
            "available_time": row.available_time,
            "n_standorte": row.n_standorte,
            "anteil_bev": row.anteil_bev,
            "vorhersage": row.vorhersage,
            "viruslast_normalisiert": row.viruslast_normalisiert,
            "viruslast": row.viruslast,
            "obere_schranke": row.obere_schranke,
            "untere_schranke": row.untere_schranke,
        }
        value, basis = select_amelag_signal_basis(point)
        point["value"] = value
        point["signal_basis"] = basis
        points.append(point)
    return points


def _safe_count(db: Any, model: Any) -> int:
    try:
        return int(db.query(func.count(model.id)).scalar() or 0)
    except Exception:
        return 0


def build_virus_wave_truth(
    db: Any,
    *,
    virus_typ: str,
    region: str = "DE",
    lookback_weeks: int = 156,
) -> dict[str, Any]:
    """Build the API diagnostic block for SurvStat/AMELAG wave truth."""

    survstat_points = _load_survstat_points(db, virus_typ=virus_typ, region=region, lookback_weeks=lookback_weeks)
    amelag_points = _load_amelag_points(db, virus_typ=virus_typ, lookback_weeks=lookback_weeks)
    survstat_features = compute_wave_features_from_points(
        survstat_points,
        source="survstat",
        virus_typ=virus_typ,
        region=region,
    )
    amelag_features = compute_wave_features_from_points(
        amelag_points,
        source="amelag",
        virus_typ=virus_typ,
        region=region,
    )
    alignment = align_wave_points(
        survstat_points=survstat_points,
        amelag_points=amelag_points,
        survstat_features=survstat_features,
        amelag_features=amelag_features,
    )
    evidence = build_wave_evidence(
        survstat_features=survstat_features,
        amelag_features=amelag_features,
        alignment=alignment,
        amelag_points=amelag_points,
        reference_date=datetime.utcnow().date(),
    )

    return {
        "schema": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "algorithm_version": EVIDENCE_VERSION,
        "scope": {
            "virus": virus_typ,
            "region": region,
            "lookback_weeks": int(lookback_weeks),
        },
        "sourceStatus": {
            "survstat_points": _safe_count(db, SurvstatKreisData),
            "survstat_weekly_points": _safe_count(db, SurvstatWeeklyData),
            "survstat_wave_points": len(survstat_points),
            "amelag_points": _safe_count(db, WastewaterAggregated),
            "amelag_wave_points": len(amelag_points),
            "wave_feature_tables_present": False,
            "computation_mode": "runtime_from_existing_timeseries",
        },
        "survstat_phase": survstat_features.get("phase"),
        "amelag_phase": amelag_features.get("phase"),
        "lead_lag_days": alignment.get("lead_lag_days"),
        "amelag_lead_days": _amelag_lead_days_from_alignment(alignment),
        "alignment_status": alignment.get("status"),
        "alignment_score": alignment.get("alignment_score"),
        "survstat": survstat_features,
        "amelag": amelag_features,
        "alignment": alignment,
        "evidence": evidence,
        "limitations": [
            "runtime_diagnostic_not_persisted_yet",
            "national_amelag_aggregates_compared_to_national_survstat",
            "evidence_weighting_is_diagnostic_only_and_not_budget_effective",
        ],
    }
