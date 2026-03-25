"""Transparent nowcast and revision-risk scoring for regional source signals."""

from __future__ import annotations
from app.core.time import utc_now

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import (
    AREKonsultation,
    GoogleTrendsData,
    GrippeWebData,
    InfluenzaData,
    KreisEinwohner,
    NotaufnahmeSyndromData,
    PollenData,
    RSVData,
    SourceNowcastSnapshot,
    SurvstatKreisData,
    SurvstatWeeklyData,
    WastewaterData,
    WeatherData,
)
from app.services.ml.nowcast_contracts import (
    NowcastObservation,
    NowcastResult,
    NowcastSnapshotRecord,
    NowcastSourceConfig,
    RevisionBucket,
)
from app.services.ml.regional_panel_utils import (
    CITY_TO_BUNDESLAND,
    SOURCE_LAG_DAYS,
    effective_available_time,
    normalize_state_code,
)

logger = logging.getLogger(__name__)


def _clamp(value: float, *, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(float(value), max_value))


NOWCAST_SOURCE_CONFIGS: dict[str, NowcastSourceConfig] = {
    "wastewater": NowcastSourceConfig(
        source_id="wastewater",
        regional_granularity="bundesland",
        availability_strategy="available_time",
        timing_provenance="explicit_available_time",
        correction_enabled=False,
        revision_window_days=0,
        revision_buckets=(),
        max_staleness_days=5,
        confidence_threshold=0.30,
        coverage_window_days=14,
        expected_cadence_days=1,
        snapshot_lookback_days=60,
    ),
    "survstat_weekly": NowcastSourceConfig(
        source_id="survstat_weekly",
        regional_granularity="bundesland",
        availability_strategy="available_time_or_fixed_lag",
        timing_provenance="weekly_publication_lag",
        correction_enabled=True,
        revision_window_days=14,
        revision_buckets=(
            RevisionBucket(max_age_days=0, completeness_factor=0.55, revision_risk=0.90),
            RevisionBucket(max_age_days=7, completeness_factor=0.75, revision_risk=0.60),
            RevisionBucket(max_age_days=14, completeness_factor=0.90, revision_risk=0.25),
        ),
        max_staleness_days=21,
        confidence_threshold=0.35,
        coverage_window_days=42,
        expected_cadence_days=7,
        snapshot_lookback_days=180,
    ),
    "survstat_kreis": NowcastSourceConfig(
        source_id="survstat_kreis",
        regional_granularity="bundesland",
        availability_strategy="synthetic_week_lag",
        timing_provenance="weekly_publication_lag",
        correction_enabled=True,
        revision_window_days=14,
        revision_buckets=(
            RevisionBucket(max_age_days=0, completeness_factor=0.55, revision_risk=0.95),
            RevisionBucket(max_age_days=7, completeness_factor=0.72, revision_risk=0.65),
            RevisionBucket(max_age_days=14, completeness_factor=0.88, revision_risk=0.30),
        ),
        max_staleness_days=21,
        confidence_threshold=0.35,
        coverage_window_days=42,
        expected_cadence_days=7,
        snapshot_lookback_days=180,
    ),
    "grippeweb": NowcastSourceConfig(
        source_id="grippeweb",
        regional_granularity="bundesland_or_national",
        availability_strategy="created_at_proxy_or_fixed_lag",
        timing_provenance="created_at_proxy",
        correction_enabled=True,
        revision_window_days=14,
        revision_buckets=(
            RevisionBucket(max_age_days=0, completeness_factor=0.60, revision_risk=0.85),
            RevisionBucket(max_age_days=7, completeness_factor=0.80, revision_risk=0.45),
            RevisionBucket(max_age_days=14, completeness_factor=0.92, revision_risk=0.20),
        ),
        max_staleness_days=21,
        confidence_threshold=0.35,
        coverage_window_days=42,
        expected_cadence_days=7,
        snapshot_lookback_days=180,
    ),
    "are_konsultation": NowcastSourceConfig(
        source_id="are_konsultation",
        regional_granularity="bundesland",
        availability_strategy="available_time_or_fixed_lag",
        timing_provenance="weekly_publication_lag",
        correction_enabled=True,
        revision_window_days=14,
        revision_buckets=(
            RevisionBucket(max_age_days=0, completeness_factor=0.65, revision_risk=0.80),
            RevisionBucket(max_age_days=7, completeness_factor=0.82, revision_risk=0.40),
            RevisionBucket(max_age_days=14, completeness_factor=0.94, revision_risk=0.15),
        ),
        max_staleness_days=21,
        confidence_threshold=0.35,
        coverage_window_days=42,
        expected_cadence_days=7,
        snapshot_lookback_days=180,
    ),
    "ifsg_influenza": NowcastSourceConfig(
        source_id="ifsg_influenza",
        regional_granularity="bundesland",
        availability_strategy="available_time_or_fixed_lag",
        timing_provenance="weekly_publication_lag",
        correction_enabled=True,
        revision_window_days=14,
        revision_buckets=(
            RevisionBucket(max_age_days=0, completeness_factor=0.70, revision_risk=0.75),
            RevisionBucket(max_age_days=7, completeness_factor=0.85, revision_risk=0.35),
            RevisionBucket(max_age_days=14, completeness_factor=0.95, revision_risk=0.12),
        ),
        max_staleness_days=21,
        confidence_threshold=0.35,
        coverage_window_days=42,
        expected_cadence_days=7,
        snapshot_lookback_days=180,
    ),
    "ifsg_rsv": NowcastSourceConfig(
        source_id="ifsg_rsv",
        regional_granularity="bundesland",
        availability_strategy="available_time_or_fixed_lag",
        timing_provenance="weekly_publication_lag",
        correction_enabled=True,
        revision_window_days=14,
        revision_buckets=(
            RevisionBucket(max_age_days=0, completeness_factor=0.72, revision_risk=0.70),
            RevisionBucket(max_age_days=7, completeness_factor=0.86, revision_risk=0.32),
            RevisionBucket(max_age_days=14, completeness_factor=0.95, revision_risk=0.10),
        ),
        max_staleness_days=21,
        confidence_threshold=0.35,
        coverage_window_days=42,
        expected_cadence_days=7,
        snapshot_lookback_days=180,
    ),
    "notaufnahme": NowcastSourceConfig(
        source_id="notaufnahme",
        regional_granularity="national",
        availability_strategy="created_at_proxy_or_fixed_lag",
        timing_provenance="created_at_proxy",
        correction_enabled=False,
        revision_window_days=0,
        revision_buckets=(),
        max_staleness_days=7,
        confidence_threshold=0.30,
        coverage_window_days=14,
        expected_cadence_days=1,
        snapshot_lookback_days=60,
    ),
    "google_trends": NowcastSourceConfig(
        source_id="google_trends",
        regional_granularity="national",
        availability_strategy="available_time_or_fixed_lag",
        timing_provenance="platform_delay",
        correction_enabled=False,
        revision_window_days=0,
        revision_buckets=(),
        max_staleness_days=7,
        confidence_threshold=0.30,
        coverage_window_days=21,
        expected_cadence_days=1,
        snapshot_lookback_days=60,
    ),
    "weather": NowcastSourceConfig(
        source_id="weather",
        regional_granularity="bundesland",
        availability_strategy="available_time",
        timing_provenance="forecast_run_timestamp",
        correction_enabled=False,
        revision_window_days=0,
        revision_buckets=(),
        max_staleness_days=5,
        confidence_threshold=0.25,
        coverage_window_days=14,
        expected_cadence_days=1,
        snapshot_lookback_days=30,
    ),
    "pollen": NowcastSourceConfig(
        source_id="pollen",
        regional_granularity="bundesland",
        availability_strategy="available_time_or_fixed_lag",
        timing_provenance="daily_publication_lag",
        correction_enabled=False,
        revision_window_days=0,
        revision_buckets=(),
        max_staleness_days=7,
        confidence_threshold=0.25,
        coverage_window_days=14,
        expected_cadence_days=1,
        snapshot_lookback_days=45,
    ),
    "school_holidays": NowcastSourceConfig(
        source_id="school_holidays",
        regional_granularity="bundesland",
        availability_strategy="static_calendar",
        timing_provenance="static_calendar",
        correction_enabled=False,
        revision_window_days=0,
        revision_buckets=(),
        max_staleness_days=3650,
        confidence_threshold=0.0,
        coverage_window_days=7,
        expected_cadence_days=7,
        snapshot_lookback_days=3650,
    ),
}


class NowcastRevisionService:
    """Apply transparent freshness and revision heuristics to source observations."""

    def __init__(self, source_configs: dict[str, NowcastSourceConfig] | None = None):
        self.source_configs = source_configs or NOWCAST_SOURCE_CONFIGS

    def get_config(self, source_id: str) -> NowcastSourceConfig:
        if source_id not in self.source_configs:
            raise KeyError(f"Unknown nowcast source config: {source_id}")
        return self.source_configs[source_id]

    def evaluate(self, observation: NowcastObservation) -> NowcastResult:
        config = self.get_config(observation.source_id)
        as_of = pd.Timestamp(observation.as_of_date)
        reference_date = pd.Timestamp(observation.reference_date)
        available_time = pd.Timestamp(observation.effective_available_time)
        age_days = max(int((as_of.normalize() - reference_date.normalize()).days), 0)
        freshness_days = max(int((as_of.normalize() - available_time.normalize()).days), 0)
        coverage_ratio = _clamp(observation.coverage_ratio)

        bucket = self._bucket_for_age(config=config, age_days=age_days)
        if bucket is None:
            completeness_factor = 1.0
            revision_risk = 0.0
        else:
            completeness_factor = _clamp(bucket.completeness_factor, min_value=0.05, max_value=1.0)
            revision_risk = _clamp(bucket.revision_risk)

        raw_value = float(observation.raw_value or 0.0)
        correction_applied = bool(config.correction_enabled and bucket is not None and raw_value >= 0.0)
        adjusted_value = float(raw_value / completeness_factor) if correction_applied else raw_value
        adjusted_value = max(adjusted_value, 0.0)

        freshness_score = self._freshness_score(config=config, freshness_days=freshness_days)
        confidence = _clamp(coverage_ratio * freshness_score * (1.0 - revision_risk))
        usable = bool(
            confidence >= float(config.confidence_threshold)
            and freshness_days <= max(int(config.max_staleness_days), 0)
        )

        return NowcastResult(
            source_id=observation.source_id,
            signal_id=observation.signal_id,
            region_code=observation.region_code,
            raw_observed_value=raw_value,
            revision_adjusted_value=adjusted_value,
            revision_risk_score=revision_risk,
            source_freshness_days=freshness_days,
            usable_confidence_score=confidence,
            usable_for_forecast=usable,
            coverage_ratio=coverage_ratio,
            correction_applied=correction_applied,
            metadata={
                "age_days": age_days,
                "timing_provenance": observation.timing_provenance,
                **dict(observation.metadata),
            },
        )

    def evaluate_missing(
        self,
        *,
        source_id: str,
        signal_id: str,
        region_code: str | None,
        as_of_date: datetime | pd.Timestamp,
        metadata: dict[str, Any] | None = None,
    ) -> NowcastResult:
        config = self.get_config(source_id)
        as_of = pd.Timestamp(as_of_date).to_pydatetime()
        return NowcastResult(
            source_id=source_id,
            signal_id=signal_id,
            region_code=region_code,
            raw_observed_value=0.0,
            revision_adjusted_value=0.0,
            revision_risk_score=1.0 if config.correction_enabled else 0.0,
            source_freshness_days=max(config.max_staleness_days, 0),
            usable_confidence_score=0.0,
            usable_for_forecast=False,
            coverage_ratio=0.0,
            correction_applied=False,
            metadata={"missing_observation": True, **(metadata or {})},
        )

    def evaluate_frame(
        self,
        *,
        source_id: str,
        signal_id: str,
        frame: pd.DataFrame | None,
        as_of_date: datetime | pd.Timestamp,
        value_column: str,
        reference_column: str = "datum",
        available_column: str = "available_time",
        region_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NowcastResult:
        config = self.get_config(source_id)
        if (
            frame is None
            or frame.empty
            or value_column not in frame.columns
            or reference_column not in frame.columns
        ):
            return self.evaluate_missing(
                source_id=source_id,
                signal_id=signal_id,
                region_code=region_code,
                as_of_date=as_of_date,
                metadata=metadata,
            )

        as_of = pd.Timestamp(as_of_date).normalize()
        visible = frame.loc[pd.to_datetime(frame[reference_column]).dt.normalize() <= as_of].copy()
        if available_column in visible.columns:
            visible = visible.loc[pd.to_datetime(visible[available_column]).dt.normalize() <= as_of].copy()
        if visible.empty:
            return self.evaluate_missing(
                source_id=source_id,
                signal_id=signal_id,
                region_code=region_code,
                as_of_date=as_of_date,
                metadata=metadata,
            )

        visible = visible.sort_values(reference_column).reset_index(drop=True)
        latest_row = visible.iloc[-1]
        reference_date = pd.Timestamp(latest_row[reference_column]).to_pydatetime()
        available_time = (
            pd.Timestamp(latest_row[available_column]).to_pydatetime()
            if available_column in visible.columns and pd.notna(latest_row.get(available_column))
            else reference_date
        )
        coverage_ratio = self._coverage_ratio(
            visible=visible,
            config=config,
            as_of=as_of,
            reference_column=reference_column,
        )
        observation = NowcastObservation(
            source_id=source_id,
            signal_id=signal_id,
            region_code=region_code,
            reference_date=reference_date,
            as_of_date=as_of.to_pydatetime(),
            raw_value=float(latest_row[value_column] or 0.0),
            effective_available_time=available_time,
            timing_provenance=config.timing_provenance,
            coverage_ratio=coverage_ratio,
            metadata=metadata or {},
        )
        return self.evaluate(observation)

    @staticmethod
    def preferred_value(result: NowcastResult, *, use_revision_adjusted: bool) -> float:
        if use_revision_adjusted and result.correction_applied:
            return float(result.revision_adjusted_value)
        return float(result.raw_observed_value)

    def _bucket_for_age(self, *, config: NowcastSourceConfig, age_days: int) -> RevisionBucket | None:
        if not config.correction_enabled or age_days > config.revision_window_days:
            return None
        for bucket in config.revision_buckets:
            if age_days <= int(bucket.max_age_days):
                return bucket
        return None

    @staticmethod
    def _freshness_score(*, config: NowcastSourceConfig, freshness_days: int) -> float:
        if config.max_staleness_days <= 0:
            return 1.0 if freshness_days <= 0 else 0.0
        penalty = freshness_days / max(float(config.max_staleness_days), 1.0)
        return _clamp(1.0 - penalty)

    @staticmethod
    def _coverage_ratio(
        *,
        visible: pd.DataFrame,
        config: NowcastSourceConfig,
        as_of: pd.Timestamp,
        reference_column: str,
    ) -> float:
        if visible.empty:
            return 0.0
        dates = pd.to_datetime(visible[reference_column]).dt.normalize()
        window_start = as_of - pd.Timedelta(days=max(config.coverage_window_days - 1, 0))
        window_visible = dates.loc[dates >= window_start]
        observed_points = int(window_visible.nunique())
        expected_points = max(
            1,
            math.ceil(float(config.coverage_window_days) / max(float(config.expected_cadence_days), 1.0)),
        )
        return _clamp(observed_points / float(expected_points))


class NowcastSnapshotService:
    """Persist append-only snapshots of source observations for revision auditing."""

    def __init__(
        self,
        db: Session,
        source_configs: dict[str, NowcastSourceConfig] | None = None,
    ) -> None:
        self.db = db
        self.source_configs = source_configs or NOWCAST_SOURCE_CONFIGS

    def capture_sources(
        self,
        source_ids: Iterable[str],
        *,
        snapshot_captured_at: datetime | None = None,
    ) -> dict[str, int]:
        captured_at = snapshot_captured_at or utc_now()
        summary: dict[str, int] = {}
        for source_id in source_ids:
            records = self._build_source_records(source_id=source_id, captured_at=captured_at)
            if not records:
                summary[source_id] = 0
                continue
            self.db.add_all(
                [
                    SourceNowcastSnapshot(
                        source_id=record.source_id,
                        signal_id=record.signal_id,
                        region_code=record.region_code,
                        reference_date=record.reference_date,
                        effective_available_time=record.effective_available_time,
                        raw_value=record.raw_value,
                        snapshot_captured_at=record.snapshot_captured_at,
                        timing_provenance=record.timing_provenance,
                        metadata_json=record.metadata,
                    )
                    for record in records
                ]
            )
            self.db.commit()
            summary[source_id] = len(records)
        return summary

    def _build_source_records(
        self,
        *,
        source_id: str,
        captured_at: datetime,
    ) -> list[NowcastSnapshotRecord]:
        builders = {
            "wastewater": self._snapshot_wastewater,
            "survstat_weekly": self._snapshot_survstat_weekly,
            "survstat_kreis": self._snapshot_survstat_kreis,
            "grippeweb": self._snapshot_grippeweb,
            "are_konsultation": self._snapshot_are_konsultation,
            "ifsg_influenza": self._snapshot_influenza,
            "ifsg_rsv": self._snapshot_rsv,
            "notaufnahme": self._snapshot_notaufnahme,
            "google_trends": self._snapshot_google_trends,
            "weather": self._snapshot_weather,
            "pollen": self._snapshot_pollen,
        }
        if source_id not in builders:
            return []
        return builders[source_id](captured_at=captured_at)

    def _snapshot_wastewater(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        config = self.source_configs["wastewater"]
        cutoff = utc_now() - timedelta(days=config.snapshot_lookback_days)
        rows = (
            self.db.query(
                WastewaterData.virus_typ,
                WastewaterData.bundesland,
                WastewaterData.datum,
                func.max(WastewaterData.available_time).label("available_time"),
                func.avg(WastewaterData.viruslast).label("raw_value"),
                func.count(WastewaterData.id).label("site_count"),
            )
            .filter(
                WastewaterData.datum >= cutoff,
                WastewaterData.viruslast.isnot(None),
            )
            .group_by(WastewaterData.virus_typ, WastewaterData.bundesland, WastewaterData.datum)
            .all()
        )
        return [
            NowcastSnapshotRecord(
                source_id="wastewater",
                signal_id=str(row.virus_typ),
                region_code=normalize_state_code(row.bundesland),
                reference_date=row.datum,
                effective_available_time=effective_available_time(row.datum, row.available_time, 0).to_pydatetime(),
                raw_value=float(row.raw_value or 0.0),
                snapshot_captured_at=captured_at,
                timing_provenance=config.timing_provenance,
                metadata={"site_count": int(row.site_count or 0)},
            )
            for row in rows
            if normalize_state_code(row.bundesland)
        ]

    def _snapshot_survstat_weekly(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        config = self.source_configs["survstat_weekly"]
        cutoff = utc_now() - timedelta(days=config.snapshot_lookback_days)
        rows = (
            self.db.query(
                SurvstatWeeklyData.disease,
                SurvstatWeeklyData.bundesland,
                SurvstatWeeklyData.week_start,
                func.max(SurvstatWeeklyData.available_time).label("available_time"),
                func.sum(SurvstatWeeklyData.incidence).label("raw_value"),
            )
            .filter(
                SurvstatWeeklyData.week_start >= cutoff,
                SurvstatWeeklyData.bundesland != "Gesamt",
            )
            .group_by(
                SurvstatWeeklyData.disease,
                SurvstatWeeklyData.bundesland,
                SurvstatWeeklyData.week_start,
            )
            .all()
        )
        return [
            NowcastSnapshotRecord(
                source_id="survstat_weekly",
                signal_id=str(row.disease),
                region_code=normalize_state_code(row.bundesland),
                reference_date=row.week_start,
                effective_available_time=effective_available_time(
                    row.week_start,
                    row.available_time,
                    SOURCE_LAG_DAYS["survstat_weekly"],
                ).to_pydatetime(),
                raw_value=float(row.raw_value or 0.0),
                snapshot_captured_at=captured_at,
                timing_provenance=config.timing_provenance,
            )
            for row in rows
            if normalize_state_code(row.bundesland)
        ]

    def _snapshot_survstat_kreis(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        config = self.source_configs["survstat_kreis"]
        cutoff_year = max(utc_now().year - 1, 2000)
        population_rows = (
            self.db.query(
                KreisEinwohner.bundesland,
                func.sum(KreisEinwohner.einwohner).label("population"),
            )
            .filter(KreisEinwohner.einwohner > 0)
            .group_by(KreisEinwohner.bundesland)
            .all()
        )
        populations = {
            normalize_state_code(row.bundesland): float(row.population or 0.0)
            for row in population_rows
            if normalize_state_code(row.bundesland)
        }
        rows = (
            self.db.query(
                SurvstatKreisData.week_label,
                SurvstatKreisData.disease,
                KreisEinwohner.bundesland,
                func.sum(SurvstatKreisData.fallzahl).label("cases"),
            )
            .join(KreisEinwohner, KreisEinwohner.kreis_name == SurvstatKreisData.kreis)
            .filter(SurvstatKreisData.year >= cutoff_year)
            .group_by(SurvstatKreisData.week_label, SurvstatKreisData.disease, KreisEinwohner.bundesland)
            .all()
        )
        records: list[NowcastSnapshotRecord] = []
        for row in rows:
            region_code = normalize_state_code(row.bundesland)
            population = float(populations.get(region_code or "", 0.0))
            if not region_code or population <= 0.0:
                continue
            reference_date = self._week_start_from_label(row.week_label)
            records.append(
                NowcastSnapshotRecord(
                    source_id="survstat_kreis",
                    signal_id=str(row.disease),
                    region_code=region_code,
                    reference_date=reference_date,
                    effective_available_time=effective_available_time(
                        reference_date,
                        None,
                        SOURCE_LAG_DAYS["survstat_kreis"],
                    ).to_pydatetime(),
                    raw_value=(float(row.cases or 0.0) / population) * 100_000.0,
                    snapshot_captured_at=captured_at,
                    timing_provenance=config.timing_provenance,
                    metadata={"cases": float(row.cases or 0.0)},
                )
            )
        return records

    def _snapshot_grippeweb(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        config = self.source_configs["grippeweb"]
        cutoff = utc_now() - timedelta(days=config.snapshot_lookback_days)
        rows = (
            self.db.query(
                GrippeWebData.erkrankung_typ,
                GrippeWebData.bundesland,
                GrippeWebData.datum,
                func.max(GrippeWebData.created_at).label("created_at"),
                func.avg(GrippeWebData.inzidenz).label("raw_value"),
            )
            .filter(
                GrippeWebData.datum >= cutoff,
                GrippeWebData.altersgruppe.in_(["00+", "Gesamt"]),
                GrippeWebData.erkrankung_typ.in_(["ARE", "ILI"]),
            )
            .group_by(GrippeWebData.erkrankung_typ, GrippeWebData.bundesland, GrippeWebData.datum)
            .all()
        )
        records: list[NowcastSnapshotRecord] = []
        for row in rows:
            region_code = normalize_state_code(row.bundesland) or "DE"
            available_time = self._created_proxy_available_time(
                datum=row.datum,
                created_at=row.created_at,
                fallback_lag_days=SOURCE_LAG_DAYS["grippeweb"],
            )
            records.append(
                NowcastSnapshotRecord(
                    source_id="grippeweb",
                    signal_id=str(row.erkrankung_typ).upper(),
                    region_code=region_code,
                    reference_date=row.datum,
                    effective_available_time=available_time.to_pydatetime(),
                    raw_value=float(row.raw_value or 0.0),
                    snapshot_captured_at=captured_at,
                    timing_provenance=config.timing_provenance,
                )
            )
        return records

    def _snapshot_are_konsultation(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        config = self.source_configs["are_konsultation"]
        cutoff = utc_now() - timedelta(days=config.snapshot_lookback_days)
        rows = (
            self.db.query(
                AREKonsultation.bundesland,
                AREKonsultation.datum,
                func.max(AREKonsultation.available_time).label("available_time"),
                func.avg(AREKonsultation.konsultationsinzidenz).label("raw_value"),
            )
            .filter(
                AREKonsultation.datum >= cutoff,
                AREKonsultation.altersgruppe == "00+",
            )
            .group_by(AREKonsultation.bundesland, AREKonsultation.datum)
            .all()
        )
        return [
            NowcastSnapshotRecord(
                source_id="are_konsultation",
                signal_id="ARE",
                region_code=normalize_state_code(row.bundesland),
                reference_date=row.datum,
                effective_available_time=effective_available_time(
                    row.datum,
                    row.available_time,
                    SOURCE_LAG_DAYS["are_konsultation"],
                ).to_pydatetime(),
                raw_value=float(row.raw_value or 0.0),
                snapshot_captured_at=captured_at,
                timing_provenance=config.timing_provenance,
            )
            for row in rows
            if normalize_state_code(row.bundesland)
        ]

    def _snapshot_influenza(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        return self._snapshot_ifsg_source(
            source_id="ifsg_influenza",
            model=InfluenzaData,
            captured_at=captured_at,
            signal_id="Influenza",
        )

    def _snapshot_rsv(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        return self._snapshot_ifsg_source(
            source_id="ifsg_rsv",
            model=RSVData,
            captured_at=captured_at,
            signal_id="RSV",
        )

    def _snapshot_ifsg_source(
        self,
        *,
        source_id: str,
        model,
        captured_at: datetime,
        signal_id: str,
    ) -> list[NowcastSnapshotRecord]:
        config = self.source_configs[source_id]
        cutoff = utc_now() - timedelta(days=config.snapshot_lookback_days)
        lag_key = "influenza_ifsg" if source_id == "ifsg_influenza" else "rsv_ifsg"
        rows = (
            self.db.query(
                model.region,
                model.datum,
                func.max(model.available_time).label("available_time"),
                func.avg(model.inzidenz).label("raw_value"),
            )
            .filter(
                model.datum >= cutoff,
                model.altersgruppe.in_(["00+", "Gesamt"]),
            )
            .group_by(model.region, model.datum)
            .all()
        )
        return [
            NowcastSnapshotRecord(
                source_id=source_id,
                signal_id=signal_id,
                region_code=normalize_state_code(row.region),
                reference_date=row.datum,
                effective_available_time=effective_available_time(
                    row.datum,
                    row.available_time,
                    SOURCE_LAG_DAYS[lag_key],
                ).to_pydatetime(),
                raw_value=float(row.raw_value or 0.0),
                snapshot_captured_at=captured_at,
                timing_provenance=config.timing_provenance,
            )
            for row in rows
            if normalize_state_code(row.region)
        ]

    def _snapshot_notaufnahme(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        config = self.source_configs["notaufnahme"]
        cutoff = utc_now() - timedelta(days=config.snapshot_lookback_days)
        rows = (
            self.db.query(NotaufnahmeSyndromData)
            .filter(
                NotaufnahmeSyndromData.datum >= cutoff,
                NotaufnahmeSyndromData.ed_type == "all",
                NotaufnahmeSyndromData.age_group == "00+",
            )
            .all()
        )
        return [
            NowcastSnapshotRecord(
                source_id="notaufnahme",
                signal_id=str(row.syndrome),
                region_code="DE",
                reference_date=row.datum,
                effective_available_time=self._created_proxy_available_time(
                    datum=row.datum,
                    created_at=row.created_at,
                    fallback_lag_days=SOURCE_LAG_DAYS["notaufnahme"],
                ).to_pydatetime(),
                raw_value=float(
                    row.relative_cases_7day_ma
                    if row.relative_cases_7day_ma is not None
                    else row.relative_cases
                    or 0.0
                ),
                snapshot_captured_at=captured_at,
                timing_provenance=config.timing_provenance,
                metadata={"expected_upperbound": float(row.expected_upperbound or 0.0)},
            )
            for row in rows
        ]

    def _snapshot_google_trends(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        config = self.source_configs["google_trends"]
        cutoff = utc_now() - timedelta(days=config.snapshot_lookback_days)
        rows = (
            self.db.query(
                GoogleTrendsData.keyword,
                GoogleTrendsData.region,
                GoogleTrendsData.datum,
                func.max(GoogleTrendsData.available_time).label("available_time"),
                func.avg(GoogleTrendsData.interest_score).label("raw_value"),
            )
            .filter(GoogleTrendsData.datum >= cutoff)
            .group_by(GoogleTrendsData.keyword, GoogleTrendsData.region, GoogleTrendsData.datum)
            .all()
        )
        return [
            NowcastSnapshotRecord(
                source_id="google_trends",
                signal_id=str(row.keyword),
                region_code=str(row.region or "DE"),
                reference_date=row.datum,
                effective_available_time=effective_available_time(
                    row.datum,
                    row.available_time,
                    SOURCE_LAG_DAYS["google_trends"],
                ).to_pydatetime(),
                raw_value=float(row.raw_value or 0.0),
                snapshot_captured_at=captured_at,
                timing_provenance=config.timing_provenance,
            )
            for row in rows
        ]

    def _snapshot_weather(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        config = self.source_configs["weather"]
        cutoff = utc_now() - timedelta(days=config.snapshot_lookback_days)
        rows = (
            self.db.query(
                WeatherData.city,
                WeatherData.datum,
                WeatherData.data_type,
                func.max(WeatherData.available_time).label("available_time"),
                func.avg(WeatherData.temperatur).label("raw_value"),
                func.avg(WeatherData.luftfeuchtigkeit).label("humidity"),
            )
            .filter(
                WeatherData.datum >= cutoff,
                WeatherData.city.in_(list(CITY_TO_BUNDESLAND.keys())),
            )
            .group_by(WeatherData.city, WeatherData.datum, WeatherData.data_type)
            .all()
        )
        records: list[NowcastSnapshotRecord] = []
        for row in rows:
            region_code = CITY_TO_BUNDESLAND.get(row.city)
            if not region_code:
                continue
            records.append(
                NowcastSnapshotRecord(
                    source_id="weather",
                    signal_id=str(row.data_type or "CURRENT"),
                    region_code=region_code,
                    reference_date=row.datum,
                    effective_available_time=effective_available_time(
                        row.datum,
                        row.available_time,
                        0,
                    ).to_pydatetime(),
                    raw_value=float(row.raw_value or 0.0),
                    snapshot_captured_at=captured_at,
                    timing_provenance=config.timing_provenance,
                    metadata={"humidity": float(row.humidity or 0.0), "city": str(row.city)},
                )
            )
        return records

    def _snapshot_pollen(self, *, captured_at: datetime) -> list[NowcastSnapshotRecord]:
        config = self.source_configs["pollen"]
        cutoff = utc_now() - timedelta(days=config.snapshot_lookback_days)
        rows = (
            self.db.query(
                PollenData.region_code,
                PollenData.datum,
                func.max(PollenData.available_time).label("available_time"),
                func.max(PollenData.pollen_index).label("raw_value"),
            )
            .filter(PollenData.datum >= cutoff)
            .group_by(PollenData.region_code, PollenData.datum)
            .all()
        )
        return [
            NowcastSnapshotRecord(
                source_id="pollen",
                signal_id="max_pollen_index",
                region_code=normalize_state_code(row.region_code),
                reference_date=row.datum,
                effective_available_time=effective_available_time(
                    row.datum,
                    row.available_time,
                    SOURCE_LAG_DAYS["pollen"],
                ).to_pydatetime(),
                raw_value=float(row.raw_value or 0.0),
                snapshot_captured_at=captured_at,
                timing_provenance=config.timing_provenance,
            )
            for row in rows
            if normalize_state_code(row.region_code)
        ]

    @staticmethod
    def _week_start_from_label(week_label: str) -> datetime:
        year_text, week_text = str(week_label).split("_", 1)
        return pd.Timestamp.fromisocalendar(int(year_text), max(int(week_text), 1), 1).to_pydatetime()

    @staticmethod
    def _created_proxy_available_time(
        *,
        datum: datetime | pd.Timestamp,
        created_at: datetime | pd.Timestamp | None,
        fallback_lag_days: int = 0,
        max_created_delay_days: int = 14,
    ) -> pd.Timestamp:
        base = effective_available_time(datum, None, fallback_lag_days)
        if created_at is None or pd.isna(created_at):
            return base
        created_ts = pd.Timestamp(created_at)
        if created_ts <= base + pd.Timedelta(days=max_created_delay_days):
            return created_ts
        return base


def capture_nowcast_snapshots(
    db: Session,
    source_ids: Iterable[str],
    *,
    snapshot_captured_at: datetime | None = None,
) -> dict[str, int]:
    """Convenience wrapper used by ingestion services after successful imports."""
    return NowcastSnapshotService(db).capture_sources(
        source_ids,
        snapshot_captured_at=snapshot_captured_at,
    )
