from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, NotaufnahmeSyndromData, SurvstatWeeklyData
from app.services.research.tri_layer.clinical_evidence import build_clinical_evidence_by_region


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    return db, engine


def test_survstat_only_evidence_produces_clinical_source_evidence() -> None:
    db, engine = _session()
    try:
        db.add_all(
            [
                SurvstatWeeklyData(
                    week_label="2024_01",
                    week_start=datetime(2024, 1, 1),
                    available_time=datetime(2024, 1, 8),
                    year=2024,
                    week=1,
                    bundesland="Hamburg",
                    disease="influenza, saisonal",
                    disease_cluster="RESPIRATORY",
                    age_group="Gesamt",
                    incidence=10.0,
                ),
                SurvstatWeeklyData(
                    week_label="2024_02",
                    week_start=datetime(2024, 1, 8),
                    available_time=datetime(2024, 1, 15),
                    year=2024,
                    week=2,
                    bundesland="Hamburg",
                    disease="influenza, saisonal",
                    disease_cluster="RESPIRATORY",
                    age_group="Gesamt",
                    incidence=20.0,
                ),
                SurvstatWeeklyData(
                    week_label="2024_03",
                    week_start=datetime(2024, 1, 15),
                    available_time=datetime(2024, 1, 22),
                    year=2024,
                    week=3,
                    bundesland="Hamburg",
                    disease="influenza, saisonal",
                    disease_cluster="RESPIRATORY",
                    age_group="Gesamt",
                    incidence=45.0,
                ),
            ]
        )
        db.commit()

        evidence = build_clinical_evidence_by_region(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 30),
            region_codes=["HH"],
        )["HH"]

        assert evidence.status == "connected"
        assert evidence.signal is not None
        assert evidence.signal > 0.65
        assert evidence.intensity is not None
        assert evidence.intensity > 0.65
        assert evidence.growth is not None
        assert evidence.growth > 0.5
        assert evidence.coverage == 1.0
        assert evidence.reliability is not None
        assert evidence.reliability > 0.4
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_notaufnahme_national_only_is_weak_regional_context() -> None:
    db, engine = _session()
    try:
        db.add_all(
            [
                NotaufnahmeSyndromData(
                    datum=datetime(2024, 1, 1),
                    ed_type="all",
                    age_group="00+",
                    syndrome="ILI",
                    relative_cases=1.0,
                    relative_cases_7day_ma=1.0,
                    expected_value=1.0,
                    created_at=datetime(2024, 1, 2),
                ),
                NotaufnahmeSyndromData(
                    datum=datetime(2024, 1, 8),
                    ed_type="all",
                    age_group="00+",
                    syndrome="ILI",
                    relative_cases=2.5,
                    relative_cases_7day_ma=2.5,
                    expected_value=1.0,
                    created_at=datetime(2024, 1, 9),
                ),
            ]
        )
        db.commit()

        evidence = build_clinical_evidence_by_region(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 12),
            region_codes=["HH"],
        )["HH"]

        assert evidence.status == "partial"
        assert evidence.signal is not None
        assert evidence.coverage is not None
        assert evidence.coverage < 0.5
        assert evidence.reliability is not None
        assert evidence.reliability < 0.5
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_stale_clinical_signal_is_connected_but_low_reliability() -> None:
    db, engine = _session()
    try:
        db.add(
            SurvstatWeeklyData(
                week_label="2024_01",
                week_start=datetime(2024, 1, 1),
                available_time=datetime(2024, 1, 8),
                year=2024,
                week=1,
                bundesland="Hamburg",
                disease="influenza, saisonal",
                disease_cluster="RESPIRATORY",
                age_group="Gesamt",
                incidence=12.0,
            )
        )
        db.commit()

        evidence = build_clinical_evidence_by_region(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 3, 15),
            region_codes=["HH"],
        )["HH"]

        assert evidence.status == "connected"
        assert evidence.freshness is not None
        assert evidence.freshness < 0.2
        assert evidence.reliability is not None
        assert evidence.reliability < 0.3
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

