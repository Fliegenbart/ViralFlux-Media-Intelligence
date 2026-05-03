from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, GrippeWebData, SurvstatWeeklyData, WastewaterAggregated
from app.services.research.tri_layer.observation_panel import (
    build_tri_layer_observation_panel,
)


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


def test_wastewater_rows_are_loaded_and_normalized() -> None:
    db, engine = _session()
    try:
        db.add_all(
            [
                WastewaterAggregated(
                    datum=datetime(2024, 1, 1),
                    available_time=datetime(2024, 1, 2),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.50,
                    viruslast=10.0,
                ),
                WastewaterAggregated(
                    datum=datetime(2024, 1, 8),
                    available_time=datetime(2024, 1, 9),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.50,
                    viruslast=20.0,
                ),
                WastewaterAggregated(
                    datum=datetime(2024, 1, 15),
                    available_time=datetime(2024, 1, 16),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.50,
                    viruslast=40.0,
                ),
            ]
        )
        db.commit()

        panel = build_tri_layer_observation_panel(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 20),
        )

        wastewater = panel.loc[panel["source"] == "wastewater"].sort_values("signal_date")
        latest = wastewater.iloc[-1]
        assert len(wastewater) == 3
        assert latest["region_code"] == "DE"
        assert latest["value_raw"] == 40.0
        assert latest["baseline"] is not None
        assert latest["value_normalized"] > 0.0
        assert latest["intensity"] > 0.5
        assert latest["coverage"] == 0.5
        assert latest["is_point_in_time_safe"] is True
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_survstat_rows_use_conservative_available_at_when_missing() -> None:
    db, engine = _session()
    try:
        db.add(
            SurvstatWeeklyData(
                week_label="2024_01",
                week_start=datetime(2024, 1, 1),
                available_time=None,
                year=2024,
                week=1,
                bundesland="Hamburg",
                disease="influenza, saisonal",
                disease_cluster="RESPIRATORY",
                age_group="Gesamt",
                incidence=12.5,
            )
        )
        db.commit()

        panel = build_tri_layer_observation_panel(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 20),
        )

        survstat = panel.loc[panel["source"] == "survstat"]
        assert len(survstat) == 1
        row = survstat.iloc[0]
        assert row["region_code"] == "HH"
        assert row["available_at"] == datetime(2024, 1, 15)
        assert row["is_point_in_time_safe"] is False
        assert "inferred" in row["point_in_time_note"]
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_rows_after_cutoff_are_excluded() -> None:
    db, engine = _session()
    try:
        db.add_all(
            [
                WastewaterAggregated(
                    datum=datetime(2024, 1, 1),
                    available_time=datetime(2024, 1, 2),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.5,
                    viruslast=10.0,
                ),
                WastewaterAggregated(
                    datum=datetime(2024, 1, 8),
                    available_time=datetime(2024, 1, 30),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.5,
                    viruslast=99.0,
                ),
            ]
        )
        db.commit()

        panel = build_tri_layer_observation_panel(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 15),
        )

        wastewater = panel.loc[panel["source"] == "wastewater"]
        assert len(wastewater) == 1
        assert wastewater.iloc[0]["value_raw"] == 10.0
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_growth_7d_uses_past_data_only() -> None:
    db, engine = _session()
    try:
        db.add_all(
            [
                WastewaterAggregated(
                    datum=datetime(2024, 1, 1),
                    available_time=datetime(2024, 1, 1),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.5,
                    viruslast=10.0,
                ),
                WastewaterAggregated(
                    datum=datetime(2024, 1, 8),
                    available_time=datetime(2024, 1, 8),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.5,
                    viruslast=20.0,
                ),
                WastewaterAggregated(
                    datum=datetime(2024, 1, 15),
                    available_time=datetime(2024, 1, 30),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.5,
                    viruslast=999.0,
                ),
            ]
        )
        db.commit()

        panel = build_tri_layer_observation_panel(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 10),
        )

        wastewater = panel.loc[panel["source"] == "wastewater"].sort_values("signal_date")
        assert len(wastewater) == 2
        latest = wastewater.iloc[-1]
        assert latest["value_raw"] == 20.0
        assert 0.9 <= latest["growth_7d"] <= 1.1
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_missing_sources_return_empty_rows_not_fake_rows() -> None:
    db, engine = _session()
    try:
        panel = build_tri_layer_observation_panel(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 20),
        )

        assert panel.empty
        assert set(
            [
                "source",
                "source_detail",
                "virus_typ",
                "region_code",
                "signal_date",
                "available_at",
                "value_raw",
                "value_normalized",
                "is_point_in_time_safe",
            ]
        ).issubset(panel.columns)
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_survstat_prefers_state_rows_over_national_fallback_when_region_available() -> None:
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
                    incidence=12.5,
                ),
                SurvstatWeeklyData(
                    week_label="2024_01",
                    week_start=datetime(2024, 1, 1),
                    available_time=datetime(2024, 1, 8),
                    year=2024,
                    week=1,
                    bundesland="Gesamt",
                    disease="influenza, saisonal",
                    disease_cluster="RESPIRATORY",
                    age_group="Gesamt",
                    incidence=10.0,
                ),
            ]
        )
        db.commit()

        panel = build_tri_layer_observation_panel(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 20),
            region_codes=["HH"],
        )

        survstat = panel.loc[panel["source"] == "survstat"]
        assert list(survstat["region_code"]) == ["HH"]
        assert "national_fallback" not in str(survstat.iloc[0]["source_detail"])
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_grippeweb_prefers_regional_rows_over_national_fallback_when_available() -> None:
    db, engine = _session()
    try:
        db.add_all(
            [
                GrippeWebData(
                    datum=datetime(2024, 1, 1),
                    kalenderwoche=1,
                    erkrankung_typ="ARE",
                    altersgruppe="00+",
                    bundesland="Hamburg",
                    inzidenz=900.0,
                    anzahl_meldungen=50,
                    created_at=datetime(2024, 1, 8),
                ),
                GrippeWebData(
                    datum=datetime(2024, 1, 1),
                    kalenderwoche=1,
                    erkrankung_typ="ARE",
                    altersgruppe="00+",
                    bundesland=None,
                    inzidenz=750.0,
                    anzahl_meldungen=500,
                    created_at=datetime(2024, 1, 8),
                ),
            ]
        )
        db.commit()

        panel = build_tri_layer_observation_panel(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 20),
            region_codes=["HH"],
        )

        grippeweb = panel.loc[panel["source"] == "grippeweb"]
        assert list(grippeweb["region_code"]) == ["HH"]
        assert "national_fallback" not in str(grippeweb.iloc[0]["source_detail"])
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_grippeweb_late_backfill_created_at_uses_conservative_available_at() -> None:
    db, engine = _session()
    try:
        db.add(
            GrippeWebData(
                datum=datetime(2024, 1, 1),
                kalenderwoche=1,
                erkrankung_typ="ARE",
                altersgruppe="00+",
                bundesland="Hamburg",
                inzidenz=900.0,
                anzahl_meldungen=50,
                created_at=datetime(2026, 1, 1),
            )
        )
        db.commit()

        panel = build_tri_layer_observation_panel(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 20),
            region_codes=["HH"],
        )

        grippeweb = panel.loc[panel["source"] == "grippeweb"]
        assert len(grippeweb) == 1
        row = grippeweb.iloc[0]
        assert row["available_at"] == datetime(2024, 1, 8)
        assert row["is_point_in_time_safe"] is False
        assert "inferred" in row["point_in_time_note"]
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_national_wastewater_fallback_is_marked() -> None:
    db, engine = _session()
    try:
        db.add(
            WastewaterAggregated(
                datum=datetime(2024, 1, 1),
                available_time=datetime(2024, 1, 2),
                virus_typ="Influenza A",
                n_standorte=4,
                anteil_bev=0.40,
                viruslast=10.0,
            )
        )
        db.commit()

        panel = build_tri_layer_observation_panel(
            db,
            virus_typ="Influenza A",
            cutoff=datetime(2024, 1, 20),
            region_codes=["HH"],
        )

        row = panel.loc[panel["source"] == "wastewater"].iloc[0]
        assert row["region_code"] == "DE"
        assert "national_fallback" in row["source_detail"]
        assert row["coverage"] == 0.4
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
