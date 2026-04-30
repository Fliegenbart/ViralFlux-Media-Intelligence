"""Materialized storage for virusWaveTruth/evidence diagnostics.

The runtime engine remains the source of calculation. This module snapshots the
runtime result into normalized tables so later backtests can inspect exactly
which wave, alignment and evidence weights were available at a point in time.
"""

from __future__ import annotations

from datetime import date, datetime, time
import hashlib
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.models.database import (
    VirusWaveAlignment,
    VirusWaveEvidence,
    VirusWaveFeature,
    VirusWaveFeatureRun,
)
from app.services.media.cockpit.virus_wave_truth import EVIDENCE_VERSION, SOURCE_ROLES, build_virus_wave_truth


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


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _season_for_payload(payload: Mapping[str, Any]) -> str | None:
    dates: list[datetime] = []
    for source in ("amelag", "survstat"):
        block = payload.get(source) if isinstance(payload.get(source), Mapping) else {}
        for key in ("peak_date", "onset_date", "latest_date"):
            parsed = _as_datetime(block.get(key))
            if parsed is not None:
                dates.append(parsed)
    if not dates:
        return None
    reference = max(dates)
    start_year = reference.year if reference.month >= 7 else reference.year - 1
    return f"{start_year}_{start_year + 1}"


def _run_key_for_payload(payload: Mapping[str, Any]) -> str:
    scope = payload.get("scope") if isinstance(payload.get("scope"), Mapping) else {}
    parts = [
        str(scope.get("virus") or payload.get("pathogen_scope") or "unknown"),
        str(scope.get("region") or "DE"),
        str(payload.get("algorithm_version") or EVIDENCE_VERSION),
        str((payload.get("survstat") or {}).get("latest_date") if isinstance(payload.get("survstat"), Mapping) else ""),
        str((payload.get("amelag") or {}).get("latest_date") if isinstance(payload.get("amelag"), Mapping) else ""),
        str(payload.get("lead_lag_days")),
        str(payload.get("alignment_score")),
    ]
    digest = hashlib.blake2b("|".join(parts).encode("utf-8"), digest_size=12).hexdigest()
    return f"virus-wave:{parts[0]}:{parts[1]}:{parts[2]}:{digest}"


def _input_bounds(payload: Mapping[str, Any]) -> tuple[datetime | None, datetime | None]:
    dates: list[datetime] = []
    for source in ("amelag", "survstat"):
        block = payload.get(source) if isinstance(payload.get(source), Mapping) else {}
        for key in ("onset_date", "peak_date", "latest_date"):
            parsed = _as_datetime(block.get(key))
            if parsed is not None:
                dates.append(parsed)
    if not dates:
        return None, None
    return min(dates), max(dates)


def _feature_row(
    *,
    run_id: int,
    source: str,
    payload: Mapping[str, Any],
    season: str | None,
    algorithm_version: str,
    computed_at: datetime,
) -> VirusWaveFeature:
    scope = payload.get("scope") if isinstance(payload.get("scope"), Mapping) else {}
    features = payload.get(source) if isinstance(payload.get(source), Mapping) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), Mapping) else {}
    amelag_quality = evidence.get("amelag_quality") if isinstance(evidence.get("amelag_quality"), Mapping) else {}
    latest = _as_datetime(features.get("latest_date"))
    if source == "amelag":
        signal_basis = str(amelag_quality.get("signal_basis") or features.get("signal_basis") or "unknown")
        quality_flags = list(amelag_quality.get("quality_flags") or [])
        freshness_days = _safe_int(amelag_quality.get("data_freshness_days"))
    else:
        signal_basis = "incidence"
        quality_flags = []
        freshness_days = max((computed_at.date() - latest.date()).days, 0) if latest else None
    growth = _safe_float(features.get("growth_rate_1w"))
    return VirusWaveFeature(
        run_id=run_id,
        source=source,
        source_role=SOURCE_ROLES.get(source, source),
        pathogen=str(scope.get("virus") or features.get("virus") or ""),
        region_code=str(scope.get("region") or features.get("region") or "DE"),
        season=season,
        phase=features.get("phase"),
        onset_date=_as_datetime(features.get("onset_date")),
        peak_date=_as_datetime(features.get("peak_date")),
        end_date=_as_datetime(features.get("end_date")),
        wave_strength=_safe_float(features.get("wave_strength")),
        peak_value=_safe_float(features.get("peak_intensity") or features.get("peak_value")),
        area_under_curve=_safe_float(features.get("area_under_curve")),
        growth_rate=growth,
        decline_rate=abs(growth) if growth is not None and growth < 0 else None,
        wave_points=_safe_int(features.get("data_points")),
        latest_observation_date=latest,
        data_freshness_days=freshness_days,
        signal_basis=signal_basis,
        quality_flags_json=quality_flags,
        confidence_score=_safe_float(features.get("confidence")),
        feature_payload_json=dict(features),
        algorithm_version=algorithm_version,
        computed_at=computed_at,
    )


def _primary_source_for_profile(profile_name: str, profile: Mapping[str, Any], evidence: Mapping[str, Any]) -> str | None:
    if profile_name == "early_warning":
        signal = evidence.get("early_warning_signal") if isinstance(evidence.get("early_warning_signal"), Mapping) else {}
        return signal.get("primary_source") or "amelag"
    if profile_name == "confirmed_burden":
        return "survstat"
    weights = profile.get("effective_weights") if isinstance(profile.get("effective_weights"), Mapping) else {}
    if not weights:
        return None
    return max(weights, key=lambda source: _safe_float(weights.get(source)) or 0.0)


def _confidence_for_profile(profile_name: str, evidence: Mapping[str, Any]) -> tuple[float | None, str | None]:
    if profile_name == "early_warning":
        signal = evidence.get("early_warning_signal") if isinstance(evidence.get("early_warning_signal"), Mapping) else {}
        return _safe_float(signal.get("confidence")), signal.get("confidence_method")
    if profile_name == "confirmed_burden":
        signal = evidence.get("confirmed_reporting_signal") if isinstance(evidence.get("confirmed_reporting_signal"), Mapping) else {}
        return _safe_float(signal.get("confidence")), signal.get("confidence_method")
    signal = evidence.get("early_warning_signal") if isinstance(evidence.get("early_warning_signal"), Mapping) else {}
    return _safe_float(signal.get("confidence")), signal.get("confidence_method")


def materialize_virus_wave_truth_payload(
    db: Session,
    payload: Mapping[str, Any],
    *,
    computed_at: datetime | None = None,
    mode: str = "materialized",
) -> dict[str, Any]:
    """Persist one runtime virusWaveTruth payload idempotently."""

    now = (computed_at or datetime.utcnow()).replace(tzinfo=None)
    scope = payload.get("scope") if isinstance(payload.get("scope"), Mapping) else {}
    pathogen = str(scope.get("virus") or "unknown")
    region = str(scope.get("region") or "DE")
    algorithm_version = str(payload.get("algorithm_version") or EVIDENCE_VERSION)
    run_key = _run_key_for_payload(payload)
    input_min_date, input_max_date = _input_bounds(payload)
    season = _season_for_payload(payload)

    run = db.query(VirusWaveFeatureRun).filter(VirusWaveFeatureRun.run_key == run_key).one_or_none()
    if run is None:
        run = VirusWaveFeatureRun(
            run_key=run_key,
            algorithm_version=algorithm_version,
            mode=mode,
            status="success",
            pathogen=pathogen,
            region_code=region,
            started_at=now,
            finished_at=now,
            pathogens_processed=1,
            regions_processed=1,
            input_min_date=input_min_date,
            input_max_date=input_max_date,
        )
        db.add(run)
        db.flush()
    else:
        db.query(VirusWaveEvidence).filter(VirusWaveEvidence.run_id == run.id).delete(synchronize_session=False)
        db.query(VirusWaveAlignment).filter(VirusWaveAlignment.run_id == run.id).delete(synchronize_session=False)
        db.query(VirusWaveFeature).filter(VirusWaveFeature.run_id == run.id).delete(synchronize_session=False)
        db.flush()

    run.algorithm_version = algorithm_version
    run.mode = mode
    run.status = "success"
    run.pathogen = pathogen
    run.region_code = region
    run.started_at = now
    run.finished_at = now
    run.pathogens_processed = 1
    run.regions_processed = 1
    run.input_min_date = input_min_date
    run.input_max_date = input_max_date
    run.parameters_json = {
        "scope": dict(scope),
        "sourceStatus": dict(payload.get("sourceStatus") or {}),
        "lookback_weeks": scope.get("lookback_weeks"),
    }
    run.snapshot_json = dict(payload)
    db.flush()

    feature_by_source: dict[str, VirusWaveFeature] = {}
    for source in ("survstat", "amelag"):
        feature = _feature_row(
            run_id=run.id,
            source=source,
            payload=payload,
            season=season,
            algorithm_version=algorithm_version,
            computed_at=now,
        )
        db.add(feature)
        feature_by_source[source] = feature
    db.flush()

    alignment = payload.get("alignment") if isinstance(payload.get("alignment"), Mapping) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), Mapping) else {}
    early_confidence, _confidence_method = _confidence_for_profile("early_warning", evidence)
    db.add(
        VirusWaveAlignment(
            run_id=run.id,
            pathogen=pathogen,
            region_code=region,
            season=season,
            early_source="amelag",
            confirmed_source="survstat",
            early_wave_feature_id=getattr(feature_by_source.get("amelag"), "id", None),
            confirmed_wave_feature_id=getattr(feature_by_source.get("survstat"), "id", None),
            raw_lead_lag_days=_safe_int(payload.get("lead_lag_days") or alignment.get("lead_lag_days")),
            early_source_lead_days=_safe_int(payload.get("amelag_lead_days")),
            alignment_status=payload.get("alignment_status") or alignment.get("status"),
            alignment_score=_safe_float(payload.get("alignment_score") or alignment.get("alignment_score")),
            divergence_score=_safe_float(alignment.get("divergence_score")),
            correlation_score=_safe_float(alignment.get("correlation")),
            confidence_score=early_confidence,
            matched_window_start=_as_datetime(alignment.get("matched_window_start")),
            matched_window_end=_as_datetime(alignment.get("matched_window_end")),
            alignment_payload_json=dict(alignment),
            algorithm_version=algorithm_version,
            computed_at=now,
        )
    )

    profiles = evidence.get("weight_profiles") if isinstance(evidence.get("weight_profiles"), Mapping) else {}
    source_availability = evidence.get("source_availability") if isinstance(evidence.get("source_availability"), Mapping) else {}
    amelag_quality = evidence.get("amelag_quality") if isinstance(evidence.get("amelag_quality"), Mapping) else {}
    budget_impact = evidence.get("budget_impact") if isinstance(evidence.get("budget_impact"), Mapping) else {}
    for profile_name, profile in profiles.items():
        if not isinstance(profile, Mapping):
            continue
        confidence_score, confidence_method = _confidence_for_profile(str(profile_name), evidence)
        quality_flags = list(amelag_quality.get("quality_flags") or [])
        quality_flags.extend(str(item) for item in profile.get("missing_sources") or [])
        db.add(
            VirusWaveEvidence(
                run_id=run.id,
                pathogen=pathogen,
                region_code=region,
                season=season,
                profile_name=str(profile_name),
                primary_source=_primary_source_for_profile(str(profile_name), profile, evidence),
                base_weights_json=dict(profile.get("base_weights") or {}),
                quality_multipliers_json=dict(profile.get("quality_multipliers") or {}),
                effective_weights_json=dict(profile.get("effective_weights") or {}),
                source_availability_json=dict(source_availability),
                evidence_coverage=_safe_float(profile.get("evidence_coverage")),
                evidence_mode=str(evidence.get("mode") or "diagnostic_only"),
                budget_can_change=bool(budget_impact.get("can_change_budget", False)),
                confidence_score=confidence_score,
                confidence_method=confidence_method,
                quality_flags_json=list(dict.fromkeys(quality_flags)),
                evidence_payload_json=dict(profile),
                algorithm_version=algorithm_version,
                computed_at=now,
            )
        )
    db.flush()
    return {"run_id": run.id, "run_key": run.run_key, "status": run.status}


def materialize_virus_wave_truth(
    db: Session,
    *,
    virus_typ: str,
    region: str = "DE",
    lookback_weeks: int = 156,
) -> dict[str, Any]:
    """Build the runtime diagnostic and persist the resulting snapshot."""

    payload = build_virus_wave_truth(db, virus_typ=virus_typ, region=region, lookback_weeks=lookback_weeks)
    result = materialize_virus_wave_truth_payload(db, payload)
    return {**result, "virus": virus_typ, "region": region}


def materialize_all_virus_wave_truth(
    db: Session,
    *,
    virus_types: list[str] | None = None,
    region: str = "DE",
    lookback_weeks: int = 156,
) -> dict[str, Any]:
    """Manual trigger helper for the current supported cockpit virus scopes."""

    scopes = virus_types or ["Influenza A", "Influenza B", "RSV A", "SARS-CoV-2"]
    results = [
        materialize_virus_wave_truth(
            db,
            virus_typ=virus_typ,
            region=region,
            lookback_weeks=lookback_weeks,
        )
        for virus_typ in scopes
    ]
    return {"status": "success", "runs": results, "count": len(results)}


def read_latest_materialized_virus_wave_truth(
    db: Session,
    *,
    virus_typ: str,
    region: str = "DE",
    algorithm_version: str | None = None,
) -> dict[str, Any] | None:
    """Read the newest successful materialized snapshot for the API."""

    query = db.query(VirusWaveFeatureRun).filter(
        VirusWaveFeatureRun.pathogen == virus_typ,
        VirusWaveFeatureRun.region_code == region,
        VirusWaveFeatureRun.status == "success",
    )
    if algorithm_version:
        query = query.filter(VirusWaveFeatureRun.algorithm_version == algorithm_version)
    run = query.order_by(VirusWaveFeatureRun.finished_at.desc(), VirusWaveFeatureRun.id.desc()).first()
    if run is None or not isinstance(run.snapshot_json, Mapping):
        return None
    payload = dict(run.snapshot_json)
    payload["status"] = "materialized"
    payload["materialization"] = {
        "mode": "materialized",
        "run_id": run.id,
        "run_key": run.run_key,
        "status": run.status,
        "computed_at": run.finished_at.isoformat() if run.finished_at else None,
        "algorithm_version": run.algorithm_version,
    }
    source_status = payload.get("sourceStatus") if isinstance(payload.get("sourceStatus"), Mapping) else {}
    payload["sourceStatus"] = {
        **dict(source_status),
        "computation_mode": "materialized_latest_successful_run",
    }
    return payload
