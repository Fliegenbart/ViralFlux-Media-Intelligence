"""Media Cockpit Service: bündelt Bento, Karte, Empfehlungen, Backtest und Datenfrische."""

from __future__ import annotations

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
    "wastewater": 7,
    "are_konsultation": 14,
    "notaufnahme": 2,
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
            "source_status": source_status,
            "map": map_section,
            "recommendations": self._recommendation_section(),
            "backtest_summary": self._backtest_summary(
                virus_typ=virus_typ,
                target_source=target_source,
            ),
            "data_freshness": data_freshness,
            "timestamp": datetime.utcnow().isoformat(),
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
            recommendation_ref = region_recommendations.get(code)

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
                "intensity": round(float(row.avg_viruslast) / max_value, 3) if max_value else 0.0,
                "trend": trend,
                "change_pct": round(float(change_pct), 1),
                "peix_score": peix_entry.get("score_0_100"),
                "peix_band": peix_entry.get("risk_band"),
                "impact_probability": peix_entry.get("impact_probability"),
                "recommendation_ref": recommendation_ref,
            }
            regions[code] = payload
            ranking.append({"code": code, **payload})

        ranking.sort(
            key=lambda x: (
                float(x.get("impact_probability") or 0.0),
                float(x.get("avg_viruslast") or 0.0),
            ),
            reverse=True,
        )
        top_regions = ranking[:8]

        activation_suggestions = []
        for item in top_regions[:5]:
            if item["trend"] == "steigend" or (item.get("impact_probability") or 0) >= 60:
                activation_suggestions.append({
                    "region": item["code"],
                    "region_name": item["name"],
                    "priority": "high" if (item.get("impact_probability") or 0) >= 70 else "medium",
                    "budget_shift_pct": min(45.0, max(10.0, float(item.get("impact_probability") or 0) * 0.35)),
                    "channel_mix": {
                        "programmatic": 42,
                        "social": 30,
                        "search": 20,
                        "ctv": 8,
                    },
                    "reason": (
                        f"{item['name']} zeigt {item['change_pct']:+.1f}% Woche-zu-Woche "
                        f"und PeixEpiScore {item.get('peix_score', 0):.1f}."
                    ),
                    "recommendation_ref": item.get("recommendation_ref"),
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

        latest_surv = self.db.query(SurvstatWeeklyData).filter(
            SurvstatWeeklyData.disease == "All",
            SurvstatWeeklyData.bundesland == "Gesamt",
        ).order_by(SurvstatWeeklyData.week_start.desc()).first()

        trends_avg = self.db.query(func.avg(GoogleTrendsData.interest_score)).filter(
            GoogleTrendsData.datum >= datetime.utcnow() - timedelta(days=14),
        ).scalar()

        bfarm = get_cached_signals() or {}
        bfarm_score = float(bfarm.get("current_risk_score", 0.0) or 0.0)

        weather_rows = self.db.query(WeatherData).filter(
            WeatherData.datum >= datetime.utcnow() - timedelta(days=2),
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
        if latest_pollen_date:
            pollen_row = self.db.query(
                PollenData.pollen_type,
                func.max(PollenData.pollen_index).label("max_index"),
            ).filter(
                PollenData.datum == latest_pollen_date,
            ).group_by(PollenData.pollen_type).order_by(func.max(PollenData.pollen_index).desc()).first()
            if pollen_row:
                pollen_signal = min(100.0, max(0.0, float(pollen_row.max_index or 0.0) / 3.0 * 100.0))
                pollen_type = pollen_row.pollen_type or "Pollen"

        tiles = [
            {
                "id": "peix_national",
                "title": "PeixEpiScore Deutschland",
                "value": peix_score.get("national_score"),
                "unit": "/100",
                "subtitle": f"Band: {peix_score.get('national_band', 'n/a')}",
                "impact_probability": peix_score.get("national_impact_probability") or 0.0,
                "data_source": "Fusion",
            },
            {
                "id": "map_top_region",
                "title": "Top Chancenregion",
                "value": top_region.get("name") if top_region else "-",
                "unit": "",
                "subtitle": (
                    f"Impact {top_region.get('impact_probability', 0):.1f}%"
                    if top_region else "Keine Daten"
                ),
                "impact_probability": top_region.get("impact_probability") if top_region else 0.0,
                "data_source": "Karte + Score",
            },
            {
                "id": "wastewater",
                "title": f"Abwasserlast {virus_typ}",
                "value": map_section.get("max_viruslast"),
                "unit": "Genkopien/L",
                "subtitle": "AMELAG/RKI",
                "impact_probability": min(100.0, max(0.0, float((map_section.get("max_viruslast") or 0.0) / 1200000.0) * 100.0)),
                "data_source": "AMELAG",
            },
            {
                "id": "are",
                "title": "ARE Konsultationsinzidenz",
                "value": latest_are.konsultationsinzidenz if latest_are else None,
                "unit": "/100k",
                "subtitle": "RKI ARE",
                "impact_probability": min(100.0, max(0.0, float((latest_are.konsultationsinzidenz or 0) / 8000.0) * 100.0)) if latest_are else 0.0,
                "data_source": "RKI",
            },
            {
                "id": "notaufnahme",
                "title": f"Notaufnahme {syndrome}",
                "value": (
                    latest_notaufnahme.relative_cases_7day_ma
                    if latest_notaufnahme and latest_notaufnahme.relative_cases_7day_ma is not None
                    else (latest_notaufnahme.relative_cases if latest_notaufnahme else None)
                ),
                "unit": "%",
                "subtitle": "AKTIN/RKI",
                "impact_probability": min(100.0, max(0.0, float((latest_notaufnahme.relative_cases_7day_ma if latest_notaufnahme and latest_notaufnahme.relative_cases_7day_ma is not None else (latest_notaufnahme.relative_cases if latest_notaufnahme else 0.0)) or 0.0) / 20.0 * 100.0)),
                "data_source": "Notaufnahme",
            },
            {
                "id": "survstat",
                "title": "SURVSTAT (All)",
                "value": latest_surv.incidence if latest_surv else None,
                "unit": "Inzidenz",
                "subtitle": latest_surv.week_label if latest_surv else "RKI SURVSTAT",
                "impact_probability": min(100.0, max(0.0, float((latest_surv.incidence or 0.0) / 200.0) * 100.0)) if latest_surv else 0.0,
                "data_source": "SURVSTAT",
            },
            {
                "id": "bfarm",
                "title": "BfArM Engpass-Signal",
                "value": bfarm_score,
                "unit": "/100",
                "subtitle": (bfarm.get("wave_type") or "BfArM"),
                "impact_probability": bfarm_score,
                "data_source": "BfArM",
            },
            {
                "id": "weather",
                "title": "Wetter-Risikodruck",
                "value": round(weather_risk, 1),
                "unit": "/100",
                "subtitle": "DWD/BrightSky",
                "impact_probability": round(weather_risk, 1),
                "data_source": "Wetter",
            },
            {
                "id": "pollen",
                "title": "Pollen-Trigger",
                "value": round(pollen_signal, 1),
                "unit": "/100",
                "subtitle": f"DWD ({pollen_type})",
                "impact_probability": round(pollen_signal, 1),
                "data_source": "DWD Pollen",
            },
            {
                "id": "trends",
                "title": "Google Trends Infekt",
                "value": round(float(trends_avg or 0.0), 1),
                "unit": "/100",
                "subtitle": "14 Tage Mittel",
                "impact_probability": round(float(trends_avg or 0.0), 1),
                "data_source": "Google Trends",
            },
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

        tiles.sort(key=lambda row: (float(row.get("impact_probability") or 0.0), float(row.get("value") or 0.0) if isinstance(row.get("value"), (int, float)) else 0.0), reverse=True)

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

            cards.append({
                "id": row.opportunity_id,
                "status": status,
                "type": row.opportunity_type,
                "urgency_score": row.urgency_score,
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
                "reason": row.recommendation_reason or (row.trigger_event or "Epidemiologisches Trigger-Signal"),
                "confidence": min(0.98, max(0.45, (row.urgency_score or 50.0) / 100.0)),
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
                "detail_url": f"/dashboard/recommendations/{row.opportunity_id}",
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })

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
                "detail_url": f"/dashboard/recommendations/{row.opportunity_id}",
                "status": status,
                "urgency_score": row.urgency_score,
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
        latest_market = self.db.query(BacktestRun).filter(
            BacktestRun.mode == "MARKET_CHECK",
            BacktestRun.virus_typ == virus_typ,
        ).order_by(BacktestRun.created_at.desc()).first()

        latest_customer = self.db.query(BacktestRun).filter(
            BacktestRun.mode == "CUSTOMER_CHECK",
            BacktestRun.virus_typ == virus_typ,
        ).order_by(BacktestRun.created_at.desc()).first()

        def _pack(row: BacktestRun | None) -> dict | None:
            if not row:
                return None
            return {
                "run_id": row.run_id,
                "mode": row.mode,
                "target_source": row.target_source,
                "target_label": row.target_label,
                "metrics": row.metrics or {},
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
        def _max_date_for(model_cls, *col_names: str):
            for col_name in col_names:
                col = getattr(model_cls, col_name, None)
                if col is None:
                    continue
                value = self.db.query(func.max(col)).scalar()
                if value:
                    return value.isoformat()
            return None

        bfarm_freshness = None
        signals = get_cached_signals() or {}
        analysis_date = signals.get("analysis_date")
        if analysis_date:
            try:
                bfarm_freshness = datetime.fromisoformat(str(analysis_date)).isoformat()
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
        now = datetime.utcnow()
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
                "feed_status_color": "green" if feed_reachable else "red",
                "freshness_state": "live" if is_live else ("stale" if parsed else "no_data"),
                "is_live": is_live,
                "status_color": "green" if is_live else "red",
            })

        items.sort(key=lambda row: (not row["is_live"], row["source_key"]))

        return {
            "items": items,
            "live_count": live_count,
            "total": len(items),
            "live_ratio": round((live_count / len(items)) * 100.0, 1) if items else 0.0,
        }
