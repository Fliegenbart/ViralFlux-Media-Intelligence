from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import WastewaterData
from app.services.media.cockpit.constants import BUNDESLAND_NAMES
from app.services.media.cockpit.signals import (
    build_ranking_signal_fields,
    normalize_recommendation_ref,
    primary_signal_score,
)
from app.services.media.region_tooltip_service import build_region_tooltip
from app.services.media.semantic_contracts import priority_score_contract, ranking_signal_contract


def build_map_section(
    db: Session,
    *,
    virus_typ: str,
    peix_score: dict[str, Any],
    region_recommendations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    latest_date = db.query(func.max(WastewaterData.datum)).filter(
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

    current_rows = db.query(
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
    prev_rows = db.query(
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
    regions: dict[str, dict[str, Any]] = {}
    ranking: list[dict[str, Any]] = []

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
        recommendation_ref = normalize_recommendation_ref(region_recommendations.get(code))
        signal_fields = build_ranking_signal_fields(
            signal_score=peix_entry.get("score_0_100"),
            legacy_alias=peix_entry.get("impact_probability"),
            source="RankingSignal",
        )
        tooltip_signal_score = primary_signal_score(signal_fields)

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
            "ranking_signal_score": peix_entry.get("score_0_100"),
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

    for code, name in BUNDESLAND_NAMES.items():
        if code in regions:
            continue
        peix_entry = peix_regions.get(code)
        if not peix_entry:
            continue
        signal_fields = build_ranking_signal_fields(
            signal_score=peix_entry.get("score_0_100"),
            legacy_alias=peix_entry.get("impact_probability"),
            source="RankingSignal",
        )
        tooltip_signal_score = primary_signal_score(signal_fields)
        fallback_payload = {
            "name": name,
            "avg_viruslast": 0.0,
            "avg_normalisiert": None,
            "n_standorte": 0,
            "einwohner": 0,
            "intensity": round(primary_signal_score(peix_entry) / 100.0, 2),
            "trend": "stabil",
            "change_pct": 0.0,
            "ranking_signal_score": peix_entry.get("score_0_100"),
            "peix_score": peix_entry.get("score_0_100"),
            "peix_band": peix_entry.get("risk_band"),
            "recommendation_ref": normalize_recommendation_ref(region_recommendations.get(code)),
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
        key=lambda item: (
            primary_signal_score(item),
            float(item.get("avg_viruslast") or 0.0),
        ),
        reverse=True,
    )
    top_regions = ranking[:8]

    activation_suggestions = []
    for item in top_regions[:5]:
        signal_score = primary_signal_score(item)
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
                "field_contracts": {
                    "signal_score": ranking_signal_contract(source="RankingSignal"),
                    "priority_score": priority_score_contract(source="MediaCockpitService"),
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
