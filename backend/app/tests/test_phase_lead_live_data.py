from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, AREKonsultation, SurvstatWeeklyData, WastewaterData
from app.services.research.phase_lead.live_data import (
    build_live_phase_lead_inputs,
    build_live_phase_lead_snapshot,
)


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal(), engine


def _seed_hamburg_respiratory_rows(db) -> None:
    start = datetime(2026, 1, 1)
    for day in range(24):
        db.add(
            WastewaterData(
                standort="HH-1",
                bundesland="HH",
                datum=start + timedelta(days=day),
                available_time=start + timedelta(days=day + 2),
                virus_typ="Influenza A",
                viruslast=900.0 + day * 35.0,
                viruslast_normalisiert=950.0 + day * 40.0,
                einwohner=1_900_000,
                unter_bg=False,
            )
        )

    for week in range(4):
        week_start = datetime(2026, 1, 5) + timedelta(days=week * 7)
        db.add(
            SurvstatWeeklyData(
                week_label=f"2026_{week + 2:02d}",
                week_start=week_start,
                available_time=week_start + timedelta(days=7),
                year=2026,
                week=week + 2,
                bundesland="Hamburg",
                disease="Influenza, saisonal",
                disease_cluster="RESPIRATORY",
                age_group="Gesamt",
                incidence=8.0 + week * 5.0,
            )
        )
        db.add(
            AREKonsultation(
                datum=week_start,
                available_time=week_start + timedelta(days=7),
                kalenderwoche=week + 2,
                saison="2025/26",
                altersgruppe="00+",
                bundesland="Hamburg",
                bundesland_id=2,
                konsultationsinzidenz=650 + week * 80,
            )
        )
    db.commit()


def test_live_phase_lead_inputs_are_built_from_real_surveillance_tables() -> None:
    db, engine = _session()
    try:
        _seed_hamburg_respiratory_rows(db)

        live_input = build_live_phase_lead_inputs(
            db,
            virus_typ="Influenza A",
            issue_date=date(2026, 1, 28),
            window_days=21,
            region_codes=["HH"],
        )

        sources = {row.source for row in live_input.observations}
        assert {"wastewater", "survstat", "are"}.issubset(sources)
        assert live_input.source_counts["wastewater"] >= 20
        assert live_input.source_counts["survstat"] == 3
        assert live_input.source_counts["are"] == 3
        assert live_input.mappings["wastewater"].observation_units == ["HH"]
        assert live_input.mappings["survstat"].observation_units == ["HH"]
        assert live_input.mappings["are"].observation_units == ["HH"]
        assert live_input.population["HH"] > 1_000_000
        assert live_input.config.sources["wastewater"].likelihood == "student_t"
        assert live_input.config.sources["survstat"].likelihood == "negative_binomial"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_live_phase_lead_snapshot_runs_forecast_from_real_tables() -> None:
    db, engine = _session()
    try:
        _seed_hamburg_respiratory_rows(db)

        snapshot = build_live_phase_lead_snapshot(
            db,
            virus_typ="Influenza A",
            issue_date=date(2026, 1, 28),
            window_days=21,
            region_codes=["HH"],
            horizons=[3, 7],
            n_samples=12,
            max_iter=8,
            seed=44,
        )

        assert snapshot["module"] == "phase_lead_graph_renewal_filter"
        assert snapshot["summary"]["data_source"] == "live_database"
        assert snapshot["summary"]["observation_count"] >= 28
        assert snapshot["sources"]["wastewater"]["rows"] >= 20
        assert snapshot["regions"][0]["region_code"] == "HH"
        assert 0.0 <= snapshot["regions"][0]["p_up_h7"] <= 1.0
        assert snapshot["rankings"]["Influenza A"][0]["region_id"] == "HH"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
