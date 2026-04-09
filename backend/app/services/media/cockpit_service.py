"""Media Cockpit Service: bündelt Bento, Karte, Empfehlungen, Backtest und Datenfrische."""

from __future__ import annotations
from app.core.time import utc_now

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import (
    AREKonsultation,
    BacktestRun,
    GoogleTrendsData,
    MarketingOpportunity,
    NotaufnahmeSyndromData,
    PollenData,
    SurvstatWeeklyData,
    WastewaterAggregated,
    WastewaterData,
    WeatherData,
)
from app.services.data_ingest.bfarm_service import get_cached_signals
from app.services.media.peix_score_service import PeixEpiScoreService
from app.services.media.recommendation_contracts import to_card_response
from app.services.media.region_tooltip_service import build_region_tooltip
from app.services.media.semantic_contracts import (
    normalize_confidence_pct,
    priority_score_contract,
    ranking_signal_contract,
    signal_confidence_contract,
)


BUNDESLAND_NAMES = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}
REGION_NAME_TO_CODE = {name.lower(): code for code, name in BUNDESLAND_NAMES.items()}

LEGACY_TO_WORKFLOW = {
    "NEW": "DRAFT",
    "URGENT": "DRAFT",
    "SENT": "APPROVED",
    "CONVERTED": "ACTIVATED",
}

SOURCE_SLA_DAYS = {
    "wastewater": 10,
    "are_konsultation": 14,
    "notaufnahme": 3,
    "survstat": 14,
    "weather": 2,
    "pollen": 2,
    "google_trends": 4,
    "bfarm_shortage": 7,
}

_NOTAUFNAHME_BY_VIRUS = {
    "Influenza A": "ILI",
    "Influenza B": "ILI",
    "SARS-CoV-2": "COVID",
    "RSV A": "ARI",
}


class MediaCockpitService:
    """Aggregierter Read-Service für das map-first Media Cockpit."""

    def __init__(self, db: Session):
        self.db = db

    def get_cockpit_payload(
        self,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
    ) -> dict:
        """Liefert einen einzigen Payload für Dashboard-Tabstruktur."""
        peix = PeixEpiScoreService(self.db).build(virus_typ=virus_typ)
        data_freshness = self._data_freshness()
        source_status = self._source_status(data_freshness)
        region_refs = self._region_recommendation_refs()

        map_section = self._map_section(
            virus_typ=virus_typ,
            peix_score=peix,
            region_recommendations=region_refs,
        )
        signal_snapshot = self._signal_snapshot_section(
            virus_typ=virus_typ,
            peix_score=peix,
            map_section=map_section,
        )

        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "bento": self._bento_section(
                virus_typ=virus_typ,
                map_section=map_section,
                peix_score=peix,
                source_status=source_status,
            ),
            "peix_epi_score": peix,
            "signal_snapshot": signal_snapshot,
            "source_status": source_status,
            "source_freshness": self._source_freshness_summary(source_status),
            "map": map_section,
            "campaign_refs": self._campaign_refs_section(region_refs),
            "recommendations": self._recommendation_section(),
            "backtest_summary": self._backtest_summary(
                virus_typ=virus_typ,
                target_source=target_source,
            ),
            "data_freshness": data_freshness,
            "timestamp": utc_now().isoformat(),
        }

    @staticmethod
    def _normalize_freshness_timestamp(
        value: datetime | None,
        *,
        now: datetime | None = None,
    ) -> str | None:
        """Return an ISO timestamp that never points into the future."""
        if value is None:
            return None

        effective_now = now or utc_now()
        normalized = value
        if normalized.tzinfo is not None:
            normalized = normalized.replace(tzinfo=None)
        if normalized > effective_now:
            normalized = effective_now
        return normalized.isoformat()

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _primary_signal_score(cls, item: dict[str, Any] | None) -> float:
        payload = item or {}
        for key in ("signal_score", "peix_score", "score_0_100", "impact_probability"):
            score = cls._coerce_float(payload.get(key))
            if score is not None:
                return round(score, 1)
        return 0.0

    def _ranking_signal_fields(
        self,
        *,
        signal_score: Any,
        source: str,
        legacy_alias: Any = None,
        label: str = "Signal-Score",
    ) -> dict[str, Any]:
        normalized_signal = self._coerce_float(signal_score)
        normalized_alias = self._coerce_float(legacy_alias)
        if normalized_signal is None:
            normalized_signal = normalized_alias
        if normalized_alias is None:
            normalized_alias = normalized_signal

        payload: dict[str, Any] = {
            "score_semantics": "ranking_signal",
            "impact_probability_semantics": "ranking_signal",
            "impact_probability_deprecated": True,
            "field_contracts": {
                "signal_score": ranking_signal_contract(source=source, label=label),
                "impact_probability": ranking_signal_contract(
                    source=source,
                    label="Legacy Signal-Score",
                ),
            },
        }
        if normalized_signal is not None:
            payload["signal_score"] = round(normalized_signal, 1)
        if normalized_alias is not None:
            payload["impact_probability"] = round(normalized_alias, 1)
        return payload

    @staticmethod
    def _normalize_recommendation_ref(
        recommendation_ref: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not recommendation_ref:
            return None
        return {
            "card_id": recommendation_ref.get("card_id"),
            "detail_url": recommendation_ref.get("detail_url"),
            "status": recommendation_ref.get("status"),
            "urgency_score": recommendation_ref.get("urgency_score"),
            "brand": recommendation_ref.get("brand"),
            "product": recommendation_ref.get("product"),
            "priority_score": recommendation_ref.get("priority_score"),
        }

    def _signal_snapshot_section(
        self,
        *,
        virus_typ: str,
        peix_score: dict[str, Any],
        map_section: dict[str, Any],
    ) -> dict[str, Any]:
        national = {
            "virus_typ": virus_typ,
            "band": peix_score.get("national_band"),
            "top_drivers": peix_score.get("top_drivers") or [],
        }
        national.update(self._ranking_signal_fields(
            signal_score=peix_score.get("national_score"),
            legacy_alias=peix_score.get("national_impact_probability"),
            source="PeixEpiScore",
        ))

        top_region = (map_section.get("top_regions") or [None])[0]
        top_region_snapshot = None
        if top_region:
            top_region_snapshot = {
                "code": top_region.get("code"),
                "name": top_region.get("name"),
                "trend": top_region.get("trend"),
            }
            top_region_snapshot.update(self._ranking_signal_fields(
                signal_score=top_region.get("signal_score") or top_region.get("peix_score"),
                legacy_alias=top_region.get("impact_probability"),
                source="PeixEpiScore",
            ))

        return {
            "national": national,
            "top_region": top_region_snapshot,
        }

    def _source_freshness_summary(self, source_status: dict[str, Any]) -> dict[str, Any]:
        items = source_status.get("items") or []
        core_source_keys = ("wastewater", "survstat", "are_konsultation", "notaufnahme")
        core_sources = [item for item in items if item.get("source_key") in core_source_keys]
        degraded_sources = [
            item for item in items
            if item.get("freshness_state") in {"stale", "no_data"}
        ]
        return {
            "live_ratio": source_status.get("live_ratio"),
            "live_count": source_status.get("live_count"),
            "total": source_status.get("total"),
            "core_sources": core_sources,
            "degraded_sources": degraded_sources,
        }

    def _campaign_refs_section(
        self,
        region_recommendations: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        refs = []
        for region_code, recommendation_ref in region_recommendations.items():
            normalized = self._normalize_recommendation_ref(recommendation_ref)
            if not normalized:
                continue
            refs.append({"region_code": region_code, **normalized})
        refs.sort(
            key=lambda item: float(item.get("priority_score") or item.get("urgency_score") or 0.0),
            reverse=True,
        )
        return {
            "regions_with_recommendations": len(refs),
            "items": refs[:12],
        }

    def _map_section(
        self,
        *,
        virus_typ: str,
        peix_score: dict[str, Any],
        region_recommendations: dict[str, dict[str, Any]],
    ) -> dict:
        latest_date = self.db.query(func.max(WastewaterData.datum)).filter(
            WastewaterData.virus_typ == virus_typ
        ).scalar()

        if not latest_date:
            return {
                "virus_typ": virus_typ,
                "has_data": False,
                "date": None,
                "regions": {},
                "top_regions": [],
                "activation_suggestions": [],
            }

        current_rows = self.db.query(
            WastewaterData.bundesland,
            func.avg(WastewaterData.viruslast).label("avg_viruslast"),
            func.avg(WastewaterData.viruslast_normalisiert).label("avg_normalized"),
            func.count(WastewaterData.standort.distinct()).label("n_standorte"),
            func.sum(WastewaterData.einwohner).label("einwohner"),
            func.avg(WastewaterData.vorhersage).label("avg_vorhersage"),
        ).filter(
            WastewaterData.virus_typ == virus_typ,
            WastewaterData.datum == latest_date,
        ).group_by(WastewaterData.bundesland).all()

        prev_date = latest_date - timedelta(days=7)
        prev_rows = self.db.query(
            WastewaterData.bundesland,
            func.avg(WastewaterData.viruslast).label("avg_viruslast"),
        ).filter(
            WastewaterData.virus_typ == virus_typ,
            WastewaterData.datum >= prev_date - timedelta(days=2),
            WastewaterData.datum <= prev_date + timedelta(days=2),
        ).group_by(WastewaterData.bundesland).all()

        prev_map = {row.bundesland: row.avg_viruslast for row in prev_rows}
        values = [row.avg_viruslast for row in current_rows if row.avg_viruslast is not None]
        max_value = max(values) if values else 1.0

        peix_regions = peix_score.get("regions", {})
        regions: dict[str, dict] = {}
        ranking: list[dict] = []

        for row in current_rows:
            code = str(row.bundesland or "").strip().upper()
            if not code or row.avg_viruslast is None:
                continue

            previous = prev_map.get(code)
            if previous and previous > 0:
                change_pct = ((row.avg_viruslast - previous) / previous) * 100.0
            else:
                change_pct = 0.0

            trend = "steigend" if change_pct > 10 else "fallend" if change_pct < -10 else "stabil"
            peix_entry = peix_regions.get(code, {})
            recommendation_ref = self._normalize_recommendation_ref(region_recommendations.get(code))
            signal_fields = self._ranking_signal_fields(
                signal_score=peix_entry.get("score_0_100"),
                legacy_alias=peix_entry.get("impact_probability"),
                source="PeixEpiScore",
            )
            tooltip_signal_score = self._primary_signal_score(signal_fields)

            # Vorhersage-Delta berechnen
            vorhersage_delta_pct = None
            if (
                row.avg_vorhersage is not None
                and row.avg_viruslast is not None
                and row.avg_viruslast > 0
            ):
                vorhersage_delta_pct = (
                    (row.avg_vorhersage - row.avg_viruslast) / row.avg_viruslast
                ) * 100.0

            payload = {
                "name": BUNDESLAND_NAMES.get(code, code),
                "avg_viruslast": round(float(row.avg_viruslast), 1),
                "avg_normalisiert": (
                    round(float(row.avg_normalized), 1)
                    if row.avg_normalized is not None
                    else None
                ),
                "n_standorte": int(row.n_standorte or 0),
                "einwohner": int(row.einwohner or 0),
                "intensity": round(float(row.avg_viruslast) / max_value, 2) if max_value else 0.0,
                "trend": trend,
                "change_pct": round(float(change_pct), 1),
                "peix_score": peix_entry.get("score_0_100"),
                "peix_band": peix_entry.get("risk_band"),
                "recommendation_ref": recommendation_ref,
                "tooltip": build_region_tooltip(
                    region_name=BUNDESLAND_NAMES.get(code, code),
                    virus_typ=virus_typ,
                    trend=trend,
                    change_pct=round(float(change_pct), 1),
                    peix_score=peix_entry.get("score_0_100"),
                    peix_band=peix_entry.get("risk_band", "low"),
                    impact_probability=tooltip_signal_score,
                    top_drivers=peix_entry.get("top_drivers"),
                    vorhersage_delta_pct=vorhersage_delta_pct,
                ),
            }
            payload.update(signal_fields)
            regions[code] = payload
            ranking.append({"code": code, **payload})

        # Fehlende Bundesländer (z.B. Stadtstaaten ohne Kläranlagen) aus PeixEpiScore ergänzen
        for code, name in BUNDESLAND_NAMES.items():
            if code in regions:
                continue
            peix_entry = peix_regions.get(code)
            if not peix_entry:
                continue
            signal_fields = self._ranking_signal_fields(
                signal_score=peix_entry.get("score_0_100"),
                legacy_alias=peix_entry.get("impact_probability"),
                source="PeixEpiScore",
            )
            tooltip_signal_score = self._primary_signal_score(signal_fields)
            fallback_payload = {
                "name": name,
                "avg_viruslast": 0.0,
                "avg_normalisiert": None,
                "n_standorte": 0,
                "einwohner": 0,
                "intensity": round(self._primary_signal_score(peix_entry) / 100.0, 2),
                "trend": "stabil",
                "change_pct": 0.0,
                "peix_score": peix_entry.get("score_0_100"),
                "peix_band": peix_entry.get("risk_band"),
                "recommendation_ref": self._normalize_recommendation_ref(region_recommendations.get(code)),
                "tooltip": build_region_tooltip(
                    region_name=name,
                    virus_typ=virus_typ,
                    trend="stabil",
                    change_pct=0.0,
                    peix_score=peix_entry.get("score_0_100"),
                    peix_band=peix_entry.get("risk_band", "low"),
                    impact_probability=tooltip_signal_score,
                    top_drivers=peix_entry.get("top_drivers"),
                ),
            }
            fallback_payload.update(signal_fields)
            regions[code] = fallback_payload
            ranking.append({"code": code, **fallback_payload})

        ranking.sort(
            key=lambda x: (
                self._primary_signal_score(x),
                float(x.get("avg_viruslast") or 0.0),
            ),
            reverse=True,
        )
        top_regions = ranking[:8]

        activation_suggestions = []
        for item in top_regions[:5]:
            signal_score = self._primary_signal_score(item)
            if item["trend"] == "steigend" or signal_score >= 60:
                priority_score = round(
                    min(
                        100.0,
                        max(
                            signal_score,
                            signal_score * 0.65 + (12.0 if item["trend"] == "steigend" else 0.0),
                        ),
                    ),
                    1,
                )
                activation_suggestions.append({
                    "region": item["code"],
                    "region_name": item["name"],
                    "priority": "high" if signal_score >= 70 else "medium",
                    "signal_score": round(signal_score, 1),
                    "priority_score": priority_score,
                    "impact_probability": round(signal_score, 1),
                    "budget_shift_pct": min(45.0, max(10.0, signal_score * 0.35)),
                    "channel_mix": {
                        "programmatic": 42,
                        "social": 30,
                        "search": 20,
                        "ctv": 8,
                    },
                    "reason": (
                        f"{item['name']} zeigt {item['change_pct']:+.1f}% Woche-zu-Woche "
                        f"und einen Signalscore von {signal_score:.1f}."
                    ),
                    "recommendation_ref": item.get("recommendation_ref"),
                    "score_semantics": "ranking_signal",
                    "impact_probability_semantics": "ranking_signal",
                    "impact_probability_deprecated": True,
                    "field_contracts": {
                        "signal_score": ranking_signal_contract(source="PeixEpiScore"),
                        "priority_score": priority_score_contract(source="MediaCockpitService"),
                        "impact_probability": ranking_signal_contract(
                            source="PeixEpiScore",
                            label="Legacy Signal-Score",
                        ),
                    },
                })

        return {
            "virus_typ": virus_typ,
            "has_data": len(regions) > 0,
            "date": latest_date.isoformat(),
            "max_viruslast": round(float(max_value), 1),
            "regions": regions,
            "top_regions": top_regions,
            "activation_suggestions": activation_suggestions,
        }

    def _bento_section(
        self,
        *,
        virus_typ: str,
        map_section: dict[str, Any],
        peix_score: dict[str, Any],
        source_status: dict[str, Any],
    ) -> dict[str, Any]:
        top_region = (map_section.get("top_regions") or [None])[0]
        latest_are = self.db.query(AREKonsultation).filter(
            AREKonsultation.altersgruppe == "00+",
            AREKonsultation.bundesland == "Bundesweit",
        ).order_by(AREKonsultation.datum.desc()).first()

        syndrome = _NOTAUFNAHME_BY_VIRUS.get(virus_typ, "ARI")
        latest_notaufnahme = self.db.query(NotaufnahmeSyndromData).filter(
            NotaufnahmeSyndromData.syndrome == syndrome,
            NotaufnahmeSyndromData.ed_type == "all",
            NotaufnahmeSyndromData.age_group == "00+",
        ).order_by(NotaufnahmeSyndromData.datum.desc()).first()

        # SurvStat: Aggregierte RESPIRATORY-Cluster-Inzidenz (Gesamt)
        _surv_latest_week = (
            self.db.query(func.max(SurvstatWeeklyData.week_start))
            .filter(
                SurvstatWeeklyData.disease_cluster == "RESPIRATORY",
                SurvstatWeeklyData.bundesland == "Gesamt",
                SurvstatWeeklyData.week > 0,
            )
            .scalar()
        )
        surv_incidence = 0.0
        surv_week_label = "RKI SURVSTAT"
        if _surv_latest_week:
            _surv_agg = (
                self.db.query(func.sum(SurvstatWeeklyData.incidence))
                .filter(
                    SurvstatWeeklyData.disease_cluster == "RESPIRATORY",
                    SurvstatWeeklyData.bundesland == "Gesamt",
                    SurvstatWeeklyData.week_start == _surv_latest_week,
                )
                .scalar()
            )
            surv_incidence = float(_surv_agg or 0.0)
            _surv_lbl = self.db.query(SurvstatWeeklyData.week_label).filter(
                SurvstatWeeklyData.week_start == _surv_latest_week,
            ).first()
            surv_week_label = _surv_lbl[0] if _surv_lbl else "RKI SURVSTAT"

        trends_avg = self.db.query(func.avg(GoogleTrendsData.interest_score)).filter(
            GoogleTrendsData.datum >= utc_now() - timedelta(days=14),
        ).scalar()

        bfarm = get_cached_signals() or {}
        bfarm_score = float(bfarm.get("current_risk_score", 0.0) or 0.0)

        weather_rows = self.db.query(WeatherData).filter(
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

        latest_pollen_date = self.db.query(func.max(PollenData.datum)).scalar()
        pollen_signal = 0.0
        pollen_type = "Pollen"
        pollen_is_stale = True
        if latest_pollen_date and (utc_now() - latest_pollen_date) <= timedelta(days=3):
            pollen_is_stale = False
            pollen_row = self.db.query(
                PollenData.pollen_type,
                func.max(PollenData.pollen_index).label("max_index"),
            ).filter(
                PollenData.datum == latest_pollen_date,
            ).group_by(PollenData.pollen_type).order_by(func.max(PollenData.pollen_index).desc()).first()
            if pollen_row:
                raw_pollen = min(100.0, max(0.0, float(pollen_row.max_index or 0.0) / 3.0 * 100.0))
                pollen_type = pollen_row.pollen_type or "Pollen"
                # Pollen ist ein Kontextsignal, nur relevant für GeloSitin.
                # Standalone max 15%, mit ARE-Belastung max 45%.
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
            tile.update(self._ranking_signal_fields(
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
                source="PeixEpiScore",
                data_source="Fusion",
            ),
            build_tile(
                tile_id="map_top_region",
                title="Top Chancenregion",
                value=top_region.get("name") if top_region else "-",
                unit="",
                subtitle=(
                    f"Signalwert {self._primary_signal_score(top_region):.1f}/100"
                    if top_region else "Keine Daten"
                ),
                signal_score=top_region.get("signal_score") if top_region else 0.0,
                source="PeixEpiScore",
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
        source_key_map = {
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
        for tile in tiles:
            key = source_key_map.get(tile["id"])
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

    def _recommendation_section(self) -> dict:
        rows = self.db.query(MarketingOpportunity).order_by(
            MarketingOpportunity.urgency_score.desc(),
            MarketingOpportunity.created_at.desc(),
        ).limit(20).all()

        cards: list[dict] = []
        for row in rows:
            region_codes = self._extract_region_codes_from_row(row)
            primary_region = region_codes[0] if region_codes else "Gesamt"
            channel_mix = row.channel_mix or {"programmatic": 35, "social": 30, "search": 20, "ctv": 15}
            campaign_payload = row.campaign_payload or {}
            campaign = campaign_payload.get("campaign") or {}
            budget = campaign_payload.get("budget_plan") or {}
            measurement = campaign_payload.get("measurement_plan") or {}
            activation = campaign_payload.get("activation_window") or {}
            product_mapping = campaign_payload.get("product_mapping") or {}
            peix_context = campaign_payload.get("peix_context") or {}
            playbook = campaign_payload.get("playbook") or {}
            ai_meta = campaign_payload.get("ai_meta") or {}
            status = LEGACY_TO_WORKFLOW.get(str(row.status or "").upper(), row.status or "DRAFT")
            recommended_product = product_mapping.get("recommended_product") or row.product or "Atemwegslinie"
            decision_expectation = (campaign_payload.get("decision_brief") or {}).get("expectation") or {}
            signal_confidence_pct = (
                normalize_confidence_pct(decision_expectation.get("signal_confidence_pct"))
                or normalize_confidence_pct(decision_expectation.get("confidence_pct"))
                or normalize_confidence_pct(
                    ((campaign_payload.get("forecast_assessment") or {}).get("event_forecast") or {}).get("confidence")
                )
            )
            signal_score = (
                self._coerce_float((peix_context or {}).get("signal_score"))
                or self._coerce_float((peix_context or {}).get("score"))
                or self._coerce_float((peix_context or {}).get("impact_probability"))
            )
            opp_payload = {
                "id": row.opportunity_id,
                "status": status,
                "type": row.opportunity_type,
                "urgency_score": row.urgency_score,
                "priority_score": row.urgency_score,
                "brand": row.brand or "PEIX Partner",
                "product": recommended_product,
                "recommended_product": recommended_product,
                "region": primary_region,
                "region_codes": region_codes,
                "budget_shift_pct": row.budget_shift_pct if row.budget_shift_pct is not None else 15.0,
                "channel_mix": channel_mix,
                "activation_window": {
                    "start": (
                        row.activation_start.isoformat() if row.activation_start
                        else activation.get("start")
                    ),
                    "end": (
                        row.activation_end.isoformat() if row.activation_end
                        else activation.get("end")
                    ),
                },
                "recommendation_reason": row.recommendation_reason or (row.trigger_event or "Epidemiologisches Trigger-Signal"),
                "confidence": (
                    round(float(signal_confidence_pct) / 100.0, 2)
                    if signal_confidence_pct is not None
                    else None
                ),
                "signal_score": signal_score,
                "signal_confidence_pct": signal_confidence_pct,
                "mapping_status": product_mapping.get("mapping_status"),
                "mapping_confidence": product_mapping.get("mapping_confidence"),
                "mapping_reason": product_mapping.get("mapping_reason"),
                "condition_key": product_mapping.get("condition_key"),
                "condition_label": product_mapping.get("condition_label"),
                "mapping_candidate_product": product_mapping.get("candidate_product"),
                "playbook_key": row.playbook_key or playbook.get("key"),
                "playbook_title": playbook.get("title"),
                "strategy_mode": row.strategy_mode or campaign_payload.get("strategy_mode"),
                "trigger_snapshot": campaign_payload.get("trigger_snapshot"),
                "guardrail_notes": (campaign_payload.get("guardrail_report") or {}).get("applied_fixes") or [],
                "ai_generation_status": ai_meta.get("status"),
                "campaign_name": campaign.get("campaign_name"),
                "primary_kpi": measurement.get("primary_kpi"),
                "peix_context": peix_context,
                "campaign_payload": campaign_payload,
                "campaign_preview": {
                    "campaign_name": campaign.get("campaign_name"),
                    "activation_window": {
                        "start": activation.get("start"),
                        "end": activation.get("end"),
                    },
                    "budget": {
                        "weekly_budget_eur": budget.get("weekly_budget_eur"),
                        "shift_pct": budget.get("budget_shift_pct"),
                        "shift_value_eur": budget.get("budget_shift_value_eur"),
                        "total_flight_budget_eur": budget.get("total_flight_budget_eur"),
                    },
                    "primary_kpi": measurement.get("primary_kpi"),
                    "recommended_product": recommended_product,
                    "mapping_status": product_mapping.get("mapping_status"),
                },
                "detail_url": f"/kampagnen/{row.opportunity_id}",
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            card = to_card_response(opp_payload, include_preview=True)
            card.setdefault("field_contracts", {})
            card["field_contracts"]["signal_confidence_pct"] = signal_confidence_contract(
                source=str(
                    (campaign_payload.get("trigger_snapshot") or {}).get("source")
                    or "Signal-Fusion"
                ),
                derived_from="trigger_evidence.confidence",
            )
            cards.append(card)

        return {
            "total": len(cards),
            "cards": cards,
        }

    def _region_recommendation_refs(self) -> dict[str, dict[str, Any]]:
        refs: dict[str, dict[str, Any]] = {}
        rows = self.db.query(MarketingOpportunity).order_by(
            MarketingOpportunity.urgency_score.desc(),
            MarketingOpportunity.created_at.desc(),
        ).limit(250).all()

        for row in rows:
            status = LEGACY_TO_WORKFLOW.get(str(row.status or "").upper(), str(row.status or "DRAFT").upper())
            if status in {"DISMISSED", "EXPIRED"}:
                continue

            region_codes = self._extract_region_codes_from_row(row)
            if not region_codes:
                region_codes = sorted(BUNDESLAND_NAMES.keys())

            payload = {
                "card_id": row.opportunity_id,
                "detail_url": f"/kampagnen/{row.opportunity_id}",
                "status": status,
                "urgency_score": row.urgency_score,
                "priority_score": row.urgency_score,
                "brand": row.brand,
                "product": row.product,
            }

            for code in region_codes:
                if code not in refs:
                    refs[code] = payload

        return refs

    def _extract_region_codes_from_row(self, row: MarketingOpportunity) -> list[str]:
        region_target = row.region_target or {}
        campaign_payload = row.campaign_payload or {}
        targeting = campaign_payload.get("targeting") or {}

        tokens: list[str] = []
        states = region_target.get("states")
        if isinstance(states, list):
            tokens.extend(str(item) for item in states)

        scope = targeting.get("region_scope")
        if isinstance(scope, list):
            tokens.extend(str(item) for item in scope)
        elif isinstance(scope, str):
            tokens.append(scope)

        normalized: set[str] = set()
        for token in tokens:
            lower = token.strip().lower()
            if lower in {"gesamt", "all", "de", "national", "deutschland"}:
                return []

            code = token.strip().upper()
            if code in BUNDESLAND_NAMES:
                normalized.add(code)
                continue

            mapped = REGION_NAME_TO_CODE.get(lower)
            if mapped:
                normalized.add(mapped)

        return sorted(normalized)

    def _backtest_summary(self, virus_typ: str, target_source: str) -> dict:
        latest_market_query = self.db.query(BacktestRun).filter(
            BacktestRun.mode == "MARKET_CHECK",
            BacktestRun.virus_typ == virus_typ,
        )
        if target_source:
            latest_market_query = latest_market_query.filter(
                func.upper(BacktestRun.target_source) == str(target_source).strip().upper()
            )
        latest_market = latest_market_query.order_by(BacktestRun.created_at.desc()).first()

        latest_customer = self.db.query(BacktestRun).filter(
            BacktestRun.mode == "CUSTOMER_CHECK",
            BacktestRun.virus_typ == virus_typ,
        ).order_by(BacktestRun.created_at.desc()).first()

        def _pack(row: BacktestRun | None) -> dict | None:
            if not row:
                return None
            metrics = row.metrics or {}
            return {
                "run_id": row.run_id,
                "mode": row.mode,
                "target_source": row.target_source,
                "target_label": row.target_label,
                "metrics": metrics,
                "decision_metrics": metrics.get("decision_metrics"),
                "interval_coverage": metrics.get("interval_coverage"),
                "event_calibration": metrics.get("event_calibration"),
                "quality_gate": metrics.get("quality_gate"),
                "timing_metrics": metrics.get("timing_metrics"),
                "lead_lag": row.lead_lag or {},
                "proof_text": row.proof_text,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

        recent_runs = self.db.query(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(8).all()

        return {
            "target_source": target_source,
            "latest_market": _pack(latest_market),
            "latest_customer": _pack(latest_customer),
            "recent_runs": [
                {
                    "run_id": row.run_id,
                    "mode": row.mode,
                    "target_source": row.target_source,
                    "virus_typ": row.virus_typ,
                    "metrics": row.metrics or {},
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in recent_runs
            ],
        }

    def _data_freshness(self) -> dict:
        now = utc_now()

        def _max_date_for(model_cls, *col_names: str):
            for col_name in col_names:
                col = getattr(model_cls, col_name, None)
                if col is None:
                    continue
                value = self.db.query(func.max(col)).scalar()
                if value:
                    return self._normalize_freshness_timestamp(value, now=now)
            return None

        bfarm_freshness = None
        signals = get_cached_signals() or {}
        analysis_date = signals.get("analysis_date")
        if analysis_date:
            try:
                bfarm_freshness = self._normalize_freshness_timestamp(
                    datetime.fromisoformat(str(analysis_date)),
                    now=now,
                )
            except ValueError:
                bfarm_freshness = None

        return {
            "wastewater": _max_date_for(WastewaterAggregated, "available_time", "datum", "created_at"),
            "are_konsultation": _max_date_for(AREKonsultation, "available_time", "datum", "created_at"),
            "survstat": _max_date_for(SurvstatWeeklyData, "available_time", "week_start", "created_at"),
            "notaufnahme": _max_date_for(NotaufnahmeSyndromData, "datum", "created_at"),
            "weather": _max_date_for(WeatherData, "available_time", "datum", "created_at"),
            "pollen": _max_date_for(PollenData, "available_time", "datum", "created_at"),
            "google_trends": _max_date_for(GoogleTrendsData, "available_time", "datum", "created_at"),
            "bfarm_shortage": bfarm_freshness,
            "marketing": _max_date_for(MarketingOpportunity, "updated_at", "created_at"),
            "backtest": _max_date_for(BacktestRun, "created_at"),
        }

    def _source_status(self, data_freshness: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        labels = {
            "wastewater": "AMELAG Abwasser",
            "are_konsultation": "RKI ARE",
            "notaufnahme": "RKI/AKTIN Notaufnahme",
            "survstat": "RKI SURVSTAT",
            "weather": "DWD/BrightSky Wetter",
            "pollen": "DWD Pollen",
            "google_trends": "Google Trends",
            "bfarm_shortage": "BfArM Engpässe",
        }

        items = []
        live_count = 0
        for source_key, sla_days in SOURCE_SLA_DAYS.items():
            raw_ts = data_freshness.get(source_key)
            parsed = None
            if raw_ts:
                try:
                    parsed = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                    if parsed.tzinfo is not None:
                        parsed = parsed.replace(tzinfo=None)
                except ValueError:
                    parsed = None

            age_days = None
            if parsed is not None:
                age_days = max(0.0, (now - parsed).total_seconds() / 86400.0)

            is_live = bool(parsed is not None and age_days is not None and age_days <= float(sla_days))
            freshness_state = "live" if is_live else ("stale" if parsed else "no_data")
            if freshness_state == "live":
                status_color = "green"
            else:
                status_color = "amber"
            feed_reachable = parsed is not None
            if is_live:
                live_count += 1

            items.append({
                "source_key": source_key,
                "label": labels.get(source_key, source_key),
                "last_updated": parsed.isoformat() if parsed else None,
                "age_days": round(age_days, 2) if age_days is not None else None,
                "sla_days": sla_days,
                "feed_reachable": feed_reachable,
                "feed_status_color": "green" if feed_reachable else "amber",
                "freshness_state": freshness_state,
                "is_live": is_live,
                "status_color": status_color,
            })

        items.sort(key=lambda row: (not row["is_live"], row["source_key"]))

        return {
            "items": items,
            "live_count": live_count,
            "total": len(items),
            "live_ratio": round((live_count / len(items)) * 100.0, 1) if items else 0.0,
        }
