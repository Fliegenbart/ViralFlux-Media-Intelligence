"""Live database adapter for phase-lead research runs."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import numpy as np
from scipy import sparse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.database import (
    AREKonsultation,
    KreisEinwohner,
    NotaufnahmeSyndromData,
    SurvstatWeeklyData,
    WastewaterData,
)
from app.services.ml.regional_panel_utils import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    REGIONAL_NEIGHBORS,
    SOURCE_LAG_DAYS,
    normalize_state_code,
)
from app.services.research.phase_lead.config import (
    ForecastConfig,
    OptimizationConfig,
    PhaseLeadConfig,
    RenewalConfig,
    SourceConfig,
)
from app.services.research.phase_lead.data_schema import ObservationRow
from app.services.research.phase_lead.graph import RegionalGraph
from app.services.research.phase_lead.joint_model import PhaseLeadGraphRenewalFilter
from app.services.research.phase_lead.kernels import ObservationKernel
from app.services.research.phase_lead.mappings import SourceMapping


PHASE_LEAD_LIVE_VERSION = "plgrf_live_v0"
DEFAULT_LIVE_HORIZONS = [3, 5, 7, 10, 14]
SURVSTAT_DISEASES_BY_VIRUS: dict[str, list[str]] = {
    "Influenza A": ["influenza, saisonal"],
    "Influenza B": ["influenza, saisonal"],
    "SARS-CoV-2": ["covid-19"],
    "RSV A": ["rsv (meldepflicht gem\u00e4\u00df ifsg)"],
}
DEFAULT_STATE_POPULATION: dict[str, float] = {
    "BW": 11_280_000.0,
    "BY": 13_430_000.0,
    "BE": 3_880_000.0,
    "BB": 2_570_000.0,
    "HB": 690_000.0,
    "HH": 1_900_000.0,
    "HE": 6_420_000.0,
    "MV": 1_630_000.0,
    "NI": 8_160_000.0,
    "NW": 18_190_000.0,
    "RP": 4_180_000.0,
    "SL": 990_000.0,
    "SN": 4_090_000.0,
    "ST": 2_180_000.0,
    "SH": 2_950_000.0,
    "TH": 2_130_000.0,
}


@dataclass(frozen=True)
class _RawLiveObservation:
    source: str
    source_type: str
    observation_unit: str
    region_id: str | None
    pathogen: str
    event_date: date
    publication_date: date
    raw_value: float
    unit: str
    denominator: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class LivePhaseLeadInput:
    issue_date: date
    observations: list[ObservationRow]
    mappings: dict[str, SourceMapping]
    graph: RegionalGraph
    population: dict[str, float]
    config: PhaseLeadConfig
    kernels: dict[str, ObservationKernel]
    source_counts: dict[str, int]
    source_units: dict[str, list[str]]
    latest_event_dates: dict[str, date]


def _coerce_date(value: date | datetime | str | None) -> date:
    if value is None:
        return datetime.utcnow().date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _to_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def _normalise_region(value: str | None) -> str | None:
    if not value:
        return None
    direct = normalize_state_code(value)
    if direct:
        return direct
    folded = str(value).strip().casefold()
    aliases = {
        "baden-wuerttemberg": "BW",
        "baden-wurttemberg": "BW",
        "thueringen": "TH",
        "bundesweit": "DE",
        "gesamt": "DE",
        "deutschland": "DE",
        "de": "DE",
    }
    return aliases.get(folded)


def _region_order(region: str) -> tuple[int, str]:
    if region == "DE":
        return (len(ALL_BUNDESLAENDER), region)
    try:
        return (ALL_BUNDESLAENDER.index(region), region)
    except ValueError:
        return (len(ALL_BUNDESLAENDER) + 1, region)


def _available_date(
    *,
    event_date: date | datetime,
    available_time: date | datetime | None,
    fallback_days: int,
) -> date:
    if available_time is not None:
        return _to_date(available_time)
    return _to_date(event_date) + timedelta(days=max(0, int(fallback_days)))


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _allowed_regions(region_codes: Iterable[str] | None) -> set[str] | None:
    if region_codes is None:
        return None
    allowed = {
        code
        for raw in region_codes
        if (code := _normalise_region(raw)) and code in ALL_BUNDESLAENDER
    }
    return allowed or set()


def _region_allowed(region: str | None, allowed: set[str] | None) -> bool:
    if not region:
        return False
    if region == "DE":
        return True
    return allowed is None or region in allowed


def _load_wastewater_observations(
    db: Session,
    *,
    virus_typ: str,
    issue_date: date,
    start_date: date,
    allowed_regions: set[str] | None,
) -> list[_RawLiveObservation]:
    value_expr = func.avg(func.coalesce(WastewaterData.viruslast_normalisiert, WastewaterData.viruslast))
    rows = (
        db.query(
            WastewaterData.datum.label("event_date"),
            WastewaterData.bundesland.label("region"),
            func.max(WastewaterData.available_time).label("available_time"),
            value_expr.label("value"),
            func.sum(WastewaterData.einwohner).label("denominator"),
            func.count(func.distinct(WastewaterData.standort)).label("site_count"),
        )
        .filter(
            WastewaterData.virus_typ == virus_typ,
            WastewaterData.datum >= datetime.combine(start_date, datetime.min.time()),
            WastewaterData.datum <= datetime.combine(issue_date, datetime.max.time()),
            or_(WastewaterData.unter_bg.is_(False), WastewaterData.unter_bg.is_(None)),
        )
        .group_by(WastewaterData.datum, WastewaterData.bundesland)
        .order_by(WastewaterData.datum.asc())
        .all()
    )
    observations: list[_RawLiveObservation] = []
    for row in rows:
        region = _normalise_region(row.region)
        if not _region_allowed(region, allowed_regions):
            continue
        event = _to_date(row.event_date)
        publication = _available_date(
            event_date=event,
            available_time=row.available_time,
            fallback_days=7,
        )
        raw_value = _safe_float(row.value)
        if raw_value is None or raw_value <= 0.0 or publication > issue_date:
            continue
        observations.append(
            _RawLiveObservation(
                source="wastewater",
                source_type="wastewater_level",
                observation_unit=str(region),
                region_id=str(region),
                pathogen=virus_typ,
                event_date=event,
                publication_date=publication,
                raw_value=raw_value,
                denominator=_safe_float(row.denominator),
                unit="amelag_normalized_viral_load",
                metadata={"site_count": int(row.site_count or 0)},
            )
        )
    return observations


def _load_survstat_observations(
    db: Session,
    *,
    virus_typ: str,
    issue_date: date,
    start_date: date,
    allowed_regions: set[str] | None,
) -> list[_RawLiveObservation]:
    diseases = tuple(SURVSTAT_DISEASES_BY_VIRUS.get(virus_typ, []))
    if not diseases:
        return []
    rows = (
        db.query(
            SurvstatWeeklyData.week_start.label("event_date"),
            SurvstatWeeklyData.bundesland.label("region"),
            func.max(SurvstatWeeklyData.available_time).label("available_time"),
            func.sum(SurvstatWeeklyData.incidence).label("value"),
        )
        .filter(
            func.lower(SurvstatWeeklyData.disease).in_(diseases),
            SurvstatWeeklyData.week_start >= datetime.combine(start_date, datetime.min.time()),
            SurvstatWeeklyData.week_start <= datetime.combine(issue_date, datetime.max.time()),
            or_(
                SurvstatWeeklyData.age_group.in_(["00+", "Gesamt"]),
                SurvstatWeeklyData.age_group.is_(None),
            ),
        )
        .group_by(SurvstatWeeklyData.week_start, SurvstatWeeklyData.bundesland)
        .order_by(SurvstatWeeklyData.week_start.asc())
        .all()
    )
    observations: list[_RawLiveObservation] = []
    for row in rows:
        region = _normalise_region(row.region)
        if region == "DE" or not _region_allowed(region, allowed_regions):
            continue
        event = _to_date(row.event_date)
        publication = _available_date(
            event_date=event,
            available_time=row.available_time,
            fallback_days=14,
        )
        raw_value = _safe_float(row.value)
        if raw_value is None or raw_value < 0.0 or publication > issue_date:
            continue
        observations.append(
            _RawLiveObservation(
                source="survstat",
                source_type="count",
                observation_unit=str(region),
                region_id=str(region),
                pathogen=virus_typ,
                event_date=event,
                publication_date=publication,
                raw_value=raw_value,
                unit="survstat_incidence_per_100k",
            )
        )
    return observations


def _load_are_observations(
    db: Session,
    *,
    virus_typ: str,
    issue_date: date,
    start_date: date,
    allowed_regions: set[str] | None,
) -> list[_RawLiveObservation]:
    rows = (
        db.query(
            AREKonsultation.datum.label("event_date"),
            AREKonsultation.bundesland.label("region"),
            func.max(AREKonsultation.available_time).label("available_time"),
            func.avg(AREKonsultation.konsultationsinzidenz).label("value"),
        )
        .filter(
            AREKonsultation.altersgruppe == "00+",
            AREKonsultation.datum >= datetime.combine(start_date, datetime.min.time()),
            AREKonsultation.datum <= datetime.combine(issue_date, datetime.max.time()),
        )
        .group_by(AREKonsultation.datum, AREKonsultation.bundesland)
        .order_by(AREKonsultation.datum.asc())
        .all()
    )
    observations: list[_RawLiveObservation] = []
    for row in rows:
        region = _normalise_region(row.region)
        if region == "DE" or not _region_allowed(region, allowed_regions):
            continue
        event = _to_date(row.event_date)
        publication = _available_date(
            event_date=event,
            available_time=row.available_time,
            fallback_days=SOURCE_LAG_DAYS["are_konsultation"],
        )
        raw_value = _safe_float(row.value)
        if raw_value is None or raw_value < 0.0 or publication > issue_date:
            continue
        observations.append(
            _RawLiveObservation(
                source="are",
                source_type="are_count",
                observation_unit=str(region),
                region_id=str(region),
                pathogen=virus_typ,
                event_date=event,
                publication_date=publication,
                raw_value=raw_value,
                unit="are_consultation_incidence",
            )
        )
    return observations


def _notaufnahme_syndrome(virus_typ: str) -> str | None:
    if virus_typ in {"Influenza A", "Influenza B"}:
        return "ILI"
    if virus_typ == "RSV A":
        return "ARI"
    if virus_typ == "SARS-CoV-2":
        return "COVID"
    return None


def _load_notaufnahme_observations(
    db: Session,
    *,
    virus_typ: str,
    issue_date: date,
    start_date: date,
) -> list[_RawLiveObservation]:
    syndrome = _notaufnahme_syndrome(virus_typ)
    if not syndrome:
        return []
    rows = (
        db.query(NotaufnahmeSyndromData)
        .filter(
            NotaufnahmeSyndromData.syndrome == syndrome,
            NotaufnahmeSyndromData.ed_type == "all",
            NotaufnahmeSyndromData.age_group == "00+",
            NotaufnahmeSyndromData.datum >= datetime.combine(start_date, datetime.min.time()),
            NotaufnahmeSyndromData.datum <= datetime.combine(issue_date, datetime.max.time()),
        )
        .order_by(NotaufnahmeSyndromData.datum.asc())
        .all()
    )
    observations: list[_RawLiveObservation] = []
    for row in rows:
        event = _to_date(row.datum)
        publication = _available_date(
            event_date=event,
            available_time=row.created_at,
            fallback_days=SOURCE_LAG_DAYS["notaufnahme"],
        )
        raw_value = _safe_float(row.relative_cases_7day_ma)
        if raw_value is None:
            raw_value = _safe_float(row.relative_cases)
        if raw_value is None or raw_value < 0.0 or publication > issue_date:
            continue
        observations.append(
            _RawLiveObservation(
                source="notaufnahme",
                source_type="hospital_count",
                observation_unit="DE",
                region_id=None,
                pathogen=virus_typ,
                event_date=event,
                publication_date=publication,
                raw_value=raw_value,
                unit=f"notaufnahme_{syndrome.lower()}_relative_cases",
                metadata={"syndrome": syndrome},
            )
        )
    return observations


def _normalise_values(raw_rows: list[_RawLiveObservation]) -> list[ObservationRow]:
    by_series: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in raw_rows:
        if row.raw_value >= 0.0:
            by_series[(row.source, row.observation_unit)].append(float(row.raw_value))

    baselines = {
        key: max(float(np.median(values)), 1.0e-6)
        for key, values in by_series.items()
        if values
    }
    observations: list[ObservationRow] = []
    for row in raw_rows:
        baseline = baselines.get((row.source, row.observation_unit), max(row.raw_value, 1.0))
        scaled_value = max((float(row.raw_value) / baseline) * 10.0, 1.0e-6)
        metadata = dict(row.metadata or {})
        metadata.update(
            {
                "raw_value": float(row.raw_value),
                "baseline_value": float(baseline),
                "normalization": "raw_over_window_median_times_10",
            }
        )
        observations.append(
            ObservationRow(
                source=row.source,
                source_type=row.source_type,
                observation_unit=row.observation_unit,
                region_id=row.region_id,
                pathogen=row.pathogen,
                event_date=row.event_date,
                report_date=row.publication_date,
                publication_date=row.publication_date,
                revision_date=row.publication_date,
                value=scaled_value,
                denominator=row.denominator,
                unit=row.unit,
                metadata=metadata,
            )
        )
    return observations


def default_live_phase_lead_kernels() -> dict[str, ObservationKernel]:
    return {
        "wastewater_early": ObservationKernel.from_values(
            "wastewater_early",
            [0.50, 0.30, 0.15, 0.05],
        ),
        "are_mid": ObservationKernel.from_values(
            "are_mid",
            [0.08, 0.18, 0.28, 0.24, 0.14, 0.08],
        ),
        "survstat_late": ObservationKernel.from_values(
            "survstat_late",
            [0.02, 0.04, 0.08, 0.14, 0.20, 0.22, 0.18, 0.12],
        ),
        "notaufnahme_lag": ObservationKernel.from_values(
            "notaufnahme_lag",
            [0.05, 0.10, 0.20, 0.25, 0.20, 0.12, 0.08],
        ),
    }


def _default_source_configs(observed_sources: set[str]) -> dict[str, SourceConfig]:
    configs = {
        "wastewater": SourceConfig(
            source_type="wastewater_level",
            likelihood="student_t",
            kernel="wastewater_early",
            sigma=0.45,
            df=5.0,
        ),
        "are": SourceConfig(
            source_type="are_count",
            likelihood="negative_binomial",
            kernel="are_mid",
            phi=35.0,
        ),
        "survstat": SourceConfig(
            source_type="count",
            likelihood="negative_binomial",
            kernel="survstat_late",
            phi=45.0,
        ),
        "notaufnahme": SourceConfig(
            source_type="hospital_count",
            likelihood="negative_binomial",
            kernel="notaufnahme_lag",
            phi=30.0,
        ),
    }
    return {source: configs[source] for source in configs if source in observed_sources}


def _population_from_db(db: Session, regions: list[str]) -> dict[str, float]:
    population = {region: DEFAULT_STATE_POPULATION.get(region, 1_000_000.0) for region in regions}
    rows = (
        db.query(KreisEinwohner.bundesland, func.sum(KreisEinwohner.einwohner).label("population"))
        .filter(KreisEinwohner.einwohner > 0)
        .group_by(KreisEinwohner.bundesland)
        .all()
    )
    for row in rows:
        region = _normalise_region(row.bundesland)
        value = _safe_float(row.population)
        if region in population and value and value > 0.0:
            population[region] = value
    return population


def _build_graph(regions: list[str]) -> RegionalGraph:
    index = {region: idx for idx, region in enumerate(regions)}
    matrix = np.zeros((len(regions), len(regions)), dtype=float)
    for region in regions:
        row_idx = index[region]
        matrix[row_idx, row_idx] = 0.65
        neighbors = [neighbor for neighbor in REGIONAL_NEIGHBORS.get(region, []) if neighbor in index]
        if not neighbors:
            matrix[row_idx, row_idx] = 1.0
            continue
        share = 0.35 / len(neighbors)
        for neighbor in neighbors:
            matrix[row_idx, index[neighbor]] += share
    return RegionalGraph(regions=regions, T=matrix)


def _build_mappings(
    observations: list[ObservationRow],
    regions: list[str],
) -> dict[str, SourceMapping]:
    units_by_source: dict[str, set[str]] = defaultdict(set)
    for row in observations:
        units_by_source[row.source].add(row.observation_unit)

    mappings: dict[str, SourceMapping] = {}
    region_index = {region: idx for idx, region in enumerate(regions)}
    for source, units in units_by_source.items():
        ordered_units = sorted(units, key=_region_order)
        rows: list[list[float]] = []
        for unit in ordered_units:
            row = [0.0] * len(regions)
            if unit == "DE":
                weight = 1.0 / max(len(regions), 1)
                row = [weight] * len(regions)
            elif unit in region_index:
                row[region_index[unit]] = 1.0
            else:
                continue
            rows.append(row)
        if rows:
            mappings[source] = SourceMapping(
                source=source,
                observation_units=ordered_units,
                latent_regions=regions,
                H=sparse.csr_matrix(rows),
            )
    return mappings


def build_live_phase_lead_inputs(
    db: Session,
    *,
    virus_typ: str,
    issue_date: date | datetime | str | None = None,
    window_days: int = 70,
    region_codes: list[str] | None = None,
    horizons: list[int] | None = None,
    n_samples: int = 160,
    max_iter: int = 60,
    seed: int = 123,
) -> LivePhaseLeadInput:
    issue = _coerce_date(issue_date)
    start = issue - timedelta(days=max(int(window_days) + 28, 56))
    allowed = _allowed_regions(region_codes)

    raw_rows: list[_RawLiveObservation] = []
    raw_rows.extend(
        _load_wastewater_observations(
            db,
            virus_typ=virus_typ,
            issue_date=issue,
            start_date=start,
            allowed_regions=allowed,
        )
    )
    raw_rows.extend(
        _load_survstat_observations(
            db,
            virus_typ=virus_typ,
            issue_date=issue,
            start_date=start,
            allowed_regions=allowed,
        )
    )
    raw_rows.extend(
        _load_are_observations(
            db,
            virus_typ=virus_typ,
            issue_date=issue,
            start_date=start,
            allowed_regions=allowed,
        )
    )
    raw_rows.extend(
        _load_notaufnahme_observations(
            db,
            virus_typ=virus_typ,
            issue_date=issue,
            start_date=start,
        )
    )
    if not raw_rows:
        raise ValueError(f"No live surveillance observations available for {virus_typ} as of {issue.isoformat()}")

    observations = _normalise_values(raw_rows)
    regional_units = {
        row.observation_unit
        for row in observations
        if row.observation_unit in ALL_BUNDESLAENDER
    }
    if allowed is not None:
        regions = [region for region in ALL_BUNDESLAENDER if region in allowed]
    else:
        regions = [region for region in ALL_BUNDESLAENDER if region in regional_units]
    if not regions:
        raise ValueError("No regional phase-lead observations are available after filtering")

    source_counts = Counter(row.source for row in observations)
    observed_sources = set(source_counts)
    config = PhaseLeadConfig(
        window_days=int(window_days),
        horizons=list(horizons or DEFAULT_LIVE_HORIZONS),
        pathogens=[virus_typ],
        sources=_default_source_configs(observed_sources),
        renewal=RenewalConfig(
            generation_interval=[0.45, 0.35, 0.20],
            eta_import=0.08,
            sigma_log_renewal=0.75,
            kappa_forecast=30.0,
            beta_pi=0.05,
            beta_omega=0.05,
        ),
        optimization=OptimizationConfig(max_iter=int(max_iter), tolerance=1.0e-5),
        forecast=ForecastConfig(n_samples=int(n_samples), seed=int(seed), state_noise=0.06),
        graph_lambda_x=1.0e-3,
        graph_lambda_q=1.0e-3,
        graph_lambda_c=1.0e-3,
    )
    mappings = _build_mappings(observations, regions)
    observations = [row for row in observations if row.source in mappings]
    if not observations:
        raise ValueError("No observations can be mapped onto the regional phase-lead graph")

    source_units = {
        source: list(mapping.observation_units)
        for source, mapping in mappings.items()
    }
    latest_event_dates: dict[str, date] = {}
    for source in source_counts:
        dates = [row.event_date for row in observations if row.source == source]
        if dates:
            latest_event_dates[source] = max(dates)

    return LivePhaseLeadInput(
        issue_date=issue,
        observations=observations,
        mappings=mappings,
        graph=_build_graph(regions),
        population=_population_from_db(db, regions),
        config=config,
        kernels=default_live_phase_lead_kernels(),
        source_counts=dict(Counter(row.source for row in observations)),
        source_units=source_units,
        latest_event_dates=latest_event_dates,
    )


def _json_float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        return 0.0
    return number


def _horizon_position(horizons: list[int], preferred: int = 7) -> int:
    if preferred in horizons:
        return horizons.index(preferred)
    return min(range(len(horizons)), key=lambda idx: abs(horizons[idx] - preferred))


def build_live_phase_lead_snapshot(
    db: Session,
    *,
    virus_typ: str,
    issue_date: date | datetime | str | None = None,
    window_days: int = 70,
    region_codes: list[str] | None = None,
    horizons: list[int] | None = None,
    n_samples: int = 160,
    max_iter: int = 60,
    seed: int = 123,
) -> dict[str, Any]:
    live_input = build_live_phase_lead_inputs(
        db,
        virus_typ=virus_typ,
        issue_date=issue_date,
        window_days=window_days,
        region_codes=region_codes,
        horizons=horizons,
        n_samples=n_samples,
        max_iter=max_iter,
        seed=seed,
    )
    model = PhaseLeadGraphRenewalFilter(
        config=live_input.config,
        kernels=live_input.kernels,
    )
    fit = model.fit(
        observations=live_input.observations,
        mappings=live_input.mappings,
        graph=live_input.graph,
        population=live_input.population,
        issue_date=live_input.issue_date,
    )
    forecast = model.forecast(
        fit,
        horizons=list(horizons or live_input.config.horizons),
        n_samples=n_samples,
        seed=seed,
    )
    h_idx = _horizon_position(forecast.horizons, preferred=7)
    pathogen_idx = 0
    rows_by_region: Counter[str] = Counter(
        row.region_id or row.observation_unit
        for row in live_input.observations
        if (row.region_id or row.observation_unit) in fit.regions
    )
    regions_payload: list[dict[str, Any]] = []
    for region_idx, region in enumerate(fit.regions):
        regions_payload.append(
            {
                "region_code": region,
                "region": BUNDESLAND_NAMES.get(region, region),
                "current_level": _json_float(fit.n_map[-1, region_idx, pathogen_idx]),
                "current_growth": _json_float(fit.q_map[-1, region_idx, pathogen_idx]),
                "p_up_h7": _json_float(forecast.p_up[h_idx, region_idx, pathogen_idx]),
                "p_surge_h7": _json_float(forecast.p_surge[h_idx, region_idx, pathogen_idx]),
                "p_front": _json_float(forecast.p_front[region_idx, pathogen_idx]),
                "eeb": _json_float(forecast.eeb[region_idx, pathogen_idx]),
                "gegb": _json_float(forecast.gegb[region_idx, pathogen_idx]),
                "source_rows": int(rows_by_region.get(region, 0)),
            }
        )
    regions_payload.sort(key=lambda item: float(item["gegb"]), reverse=True)

    sources_payload = {
        source: {
            "rows": int(live_input.source_counts.get(source, 0)),
            "latest_event_date": live_input.latest_event_dates.get(source).isoformat()
            if live_input.latest_event_dates.get(source)
            else None,
            "units": live_input.source_units.get(source, []),
        }
        for source in sorted(live_input.source_counts)
    }

    return {
        "module": "phase_lead_graph_renewal_filter",
        "version": PHASE_LEAD_LIVE_VERSION,
        "mode": "research",
        "as_of": live_input.issue_date.isoformat(),
        "virus_typ": virus_typ,
        "horizons": forecast.horizons,
        "summary": {
            "data_source": "live_database",
            "observation_count": len(live_input.observations),
            "window_start": fit.window_start.isoformat(),
            "window_end": fit.window_end.isoformat(),
            "converged": bool(fit.converged),
            "objective_value": _json_float(fit.objective_value),
            "data_vintage_hash": fit.data_vintage_hash,
            "config_hash": fit.config_hash,
            "top_region": regions_payload[0]["region_code"] if regions_payload else None,
            "warning_count": len(fit.warnings),
        },
        "sources": sources_payload,
        "regions": regions_payload,
        "rankings": forecast.region_rankings,
        "warnings": list(forecast.warnings),
    }
