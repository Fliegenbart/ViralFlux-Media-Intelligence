from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.database import (
    AREKonsultation,
    GoogleTrendsData,
    NotaufnahmeSyndromData,
    PollenData,
    SurvstatWeeklyData,
    WeatherData,
)
from app.services.data_ingest.bfarm_service import get_cached_signals
from app.services.media.cockpit.signals import build_ranking_signal_fields, primary_signal_score

NOTAUFNAHME_BY_VIRUS = {
    "Influenza A": "ILI",
    "Influenza B": "ILI",
    "SARS-CoV-2": "COVID",
    "RSV A": "ARI",
}

SOURCE_KEY_MAP = {
    "wastewater": "wastewater",
    "are": "are_konsultation",
    "notaufnahme": "notaufnahme",
    "survstat": "survstat",
    "bfarm": "bfarm_shortage",
    "weather": "weather",
    "pollen": "pollen",
    "trends": "google_trends",
    "peix_national": "wastewater",
    "map_top_region": "wastewater",
}


def build_bento_section(
    db: Session,
    *,
    virus_typ: str,
    map_section: dict[str, Any],
    peix_score: dict[str, Any],
    source_status: dict[str, Any],
) -> dict[str, Any]:
    top_region = (map_section.get("top_regions") or [None])[0]
    latest_are = db.query(AREKonsultation).filter(
        AREKonsultation.altersgruppe == "00+",
        AREKonsultation.bundesland == "Bundesweit",
    ).order_by(AREKonsultation.datum.desc()).first()

    syndrome = NOTAUFNAHME_BY_VIRUS.get(virus_typ, "ARI")
    latest_notaufnahme = db.query(NotaufnahmeSyndromData).filter(
        NotaufnahmeSyndromData.syndrome == syndrome,
        NotaufnahmeSyndromData.ed_type == "all",
        NotaufnahmeSyndromData.age_group == "00+",
    ).order_by(NotaufnahmeSyndromData.datum.desc()).first()

    surv_latest_week = (
        db.query(func.max(SurvstatWeeklyData.week_start))
        .filter(
            SurvstatWeeklyData.disease_cluster == "RESPIRATORY",
            SurvstatWeeklyData.bundesland == "Gesamt",
            SurvstatWeeklyData.week > 0,
        )
        .scalar()
    )
    surv_incidence = 0.0
    surv_week_label = "RKI SURVSTAT"
    if surv_latest_week:
        surv_agg = (
            db.query(func.sum(SurvstatWeeklyData.incidence))
            .filter(
                SurvstatWeeklyData.disease_cluster == "RESPIRATORY",
                SurvstatWeeklyData.bundesland == "Gesamt",
                SurvstatWeeklyData.week_start == surv_latest_week,
            )
            .scalar()
        )
        surv_incidence = float(surv_agg or 0.0)
        surv_lbl = db.query(SurvstatWeeklyData.week_label).filter(
            SurvstatWeeklyData.week_start == surv_latest_week,
        ).first()
        surv_week_label = surv_lbl[0] if surv_lbl else "RKI SURVSTAT"

    trends_avg = db.query(func.avg(GoogleTrendsData.interest_score)).filter(
        GoogleTrendsData.datum >= utc_now() - timedelta(days=14),
    ).scalar()

    bfarm = get_cached_signals() or {}
    bfarm_score = float(bfarm.get("current_risk_score", 0.0) or 0.0)

    weather_rows = db.query(WeatherData).filter(
        WeatherData.datum >= utc_now() - timedelta(days=2),
    ).all()
    weather_risk = 0.0
    if weather_rows:
        values = []
        for row in weather_rows:
            temp = float(row.temperatur) if row.temperatur is not None else 7.0
            uv = float(row.uv_index) if row.uv_index is not None else 2.5
            humidity = float(row.luftfeuchtigkeit) if row.luftfeuchtigkeit is not None else 70.0
            temp_factor = max(0.0, min(1.0, (15.0 - temp) / 20.0))
            uv_factor = max(0.0, min(1.0, (5.0 - uv) / 5.0))
            hum_factor = max(0.0, min(1.0, humidity / 100.0))
            values.append(temp_factor * 0.45 + uv_factor * 0.35 + hum_factor * 0.20)
        weather_risk = (sum(values) / len(values)) * 100.0

    latest_pollen_date = db.query(func.max(PollenData.datum)).scalar()
    pollen_signal = 0.0
    pollen_type = "Pollen"
    pollen_is_stale = True
    if latest_pollen_date and (utc_now() - latest_pollen_date) <= timedelta(days=3):
        pollen_is_stale = False
        pollen_row = db.query(
            PollenData.pollen_type,
            func.max(PollenData.pollen_index).label("max_index"),
        ).filter(
            PollenData.datum == latest_pollen_date,
        ).group_by(PollenData.pollen_type).order_by(func.max(PollenData.pollen_index).desc()).first()
        if pollen_row:
            raw_pollen = min(100.0, max(0.0, float(pollen_row.max_index or 0.0) / 3.0 * 100.0))
            pollen_type = pollen_row.pollen_type or "Pollen"
            are_factor = min(1.0, float((latest_are.konsultationsinzidenz or 0) / 4000.0)) if latest_are else 0.0
            pollen_signal = round(raw_pollen * (0.15 + 0.30 * are_factor), 1)
    else:
        pollen_type = "Saison-Pause"

    def build_tile(
        *,
        tile_id: str,
        title: str,
        value: Any,
        unit: str,
        subtitle: str,
        signal_score: Any,
        source: str,
        data_source: str,
        product_scope: str | None = None,
    ) -> dict[str, Any]:
        tile = {
            "id": tile_id,
            "title": title,
            "value": value,
            "unit": unit,
            "subtitle": subtitle,
            "data_source": data_source,
        }
        if product_scope:
            tile["product_scope"] = product_scope
        tile.update(build_ranking_signal_fields(
            signal_score=signal_score,
            source=source,
        ))
        return tile

    tiles = [
        build_tile(
            tile_id="peix_national",
            title="Signalscore Deutschland",
            value=peix_score.get("national_score"),
            unit="/100",
            subtitle=f"Band: {peix_score.get('national_band', 'n/a')}",
            signal_score=peix_score.get("national_score"),
            source="RankingSignal",
            data_source="Fusion",
        ),
        build_tile(
            tile_id="map_top_region",
            title="Top Chancenregion",
            value=top_region.get("name") if top_region else "-",
            unit="",
            subtitle=(
                f"Signalwert {primary_signal_score(top_region):.1f}/100"
                if top_region else "Keine Daten"
            ),
            signal_score=top_region.get("signal_score") if top_region else 0.0,
            source="RankingSignal",
            data_source="Karte + Score",
        ),
        build_tile(
            tile_id="wastewater",
            title=f"Abwasserlast {virus_typ}",
            value=map_section.get("max_viruslast"),
            unit="Genkopien/L",
            subtitle="AMELAG/RKI",
            signal_score=min(100.0, max(0.0, float((map_section.get("max_viruslast") or 0.0) / 1200000.0) * 100.0)),
            source="AMELAG",
            data_source="AMELAG",
        ),
        build_tile(
            tile_id="are",
            title="ARE Konsultationsinzidenz",
            value=latest_are.konsultationsinzidenz if latest_are else None,
            unit="/100k",
            subtitle="RKI ARE",
            signal_score=(
                min(100.0, max(0.0, float((latest_are.konsultationsinzidenz or 0) / 8000.0) * 100.0))
                if latest_are else 0.0
            ),
            source="RKI ARE",
            data_source="RKI",
        ),
        build_tile(
            tile_id="notaufnahme",
            title=f"Notaufnahme {syndrome}",
            value=(
                latest_notaufnahme.relative_cases_7day_ma
                if latest_notaufnahme and latest_notaufnahme.relative_cases_7day_ma is not None
                else (latest_notaufnahme.relative_cases if latest_notaufnahme else None)
            ),
            unit="%",
            subtitle="AKTIN/RKI",
            signal_score=min(
                100.0,
                max(
                    0.0,
                    float(
                        (
                            latest_notaufnahme.relative_cases_7day_ma
                            if latest_notaufnahme and latest_notaufnahme.relative_cases_7day_ma is not None
                            else (latest_notaufnahme.relative_cases if latest_notaufnahme else 0.0)
                        ) or 0.0
                    ) / 20.0 * 100.0,
                ),
            ),
            source="AKTIN/RKI",
            data_source="Notaufnahme",
        ),
        build_tile(
            tile_id="survstat",
            title="SURVSTAT Respiratory",
            value=round(surv_incidence, 1) if surv_incidence > 0 else None,
            unit="/100k",
            subtitle=surv_week_label,
            signal_score=min(100.0, max(0.0, surv_incidence / 150.0 * 100.0)),
            source="RKI SURVSTAT",
            data_source="SURVSTAT",
        ),
        build_tile(
            tile_id="bfarm",
            title="BfArM Engpass-Signal",
            value=bfarm_score,
            unit="/100",
            subtitle=(bfarm.get("wave_type") or "BfArM"),
            signal_score=round(
                bfarm_score * (
                    0.40 + 0.60 * min(
                        1.0,
                        float((latest_are.konsultationsinzidenz or 0) / 4000.0)
                        if latest_are else 0.0,
                    )
                ),
                1,
            ),
            source="BfArM",
            data_source="BfArM",
        ),
        build_tile(
            tile_id="weather",
            title="Wetter-Risikodruck",
            value=round(weather_risk, 1),
            unit="/100",
            subtitle="DWD/BrightSky",
            signal_score=round(weather_risk, 1),
            source="DWD/BrightSky",
            data_source="Wetter",
        ),
        build_tile(
            tile_id="pollen",
            title="Pollen-Trigger",
            value=round(pollen_signal, 1),
            unit="/100",
            subtitle=(
                "Keine aktuellen Daten (Saison-Pause)"
                if pollen_is_stale
                else f"DWD ({pollen_type}) - Relevant für GeloSitin"
            ),
            signal_score=round(pollen_signal, 1),
            source="DWD Pollen",
            data_source="DWD Pollen",
            product_scope="GeloSitin",
        ),
        build_tile(
            tile_id="trends",
            title="Google Trends Infekt",
            value=round(float(trends_avg or 0.0), 1),
            unit="/100",
            subtitle="14 Tage Mittel",
            signal_score=round(float(trends_avg or 0.0), 1),
            source="Google Trends",
            data_source="Google Trends",
        ),
    ]

    live_map = {item["source_key"]: item for item in source_status.get("items", [])}
    for tile in tiles:
        key = SOURCE_KEY_MAP.get(tile["id"])
        status_item = live_map.get(key) if key else None
        tile["is_live"] = bool(status_item.get("is_live")) if status_item else False
        tile["last_updated"] = status_item.get("last_updated") if status_item else None

    tiles.sort(
        key=lambda row: (
            float(row.get("signal_score") or row.get("impact_probability") or 0.0),
            float(row.get("value") or 0.0) if isinstance(row.get("value"), (int, float)) else 0.0,
        ),
        reverse=True,
    )

    return {
        "tiles": tiles,
        "count": len(tiles),
    }
