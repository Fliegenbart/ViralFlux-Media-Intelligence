"""Candidate generation helpers for playbook-based regional recommendations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func

from app.models.database import SurvstatWeeklyData
from app.services.data_ingest.bfarm_service import get_cached_signals
from app.services.media.playbook_engine import REGION_NAME_TO_CODE


def mycoplasma_candidates(
    engine,
    *,
    peix_regions: dict[str, Any],
    allowed_regions: list[str],
) -> list[dict[str, Any]]:
    rows = engine.db.query(SurvstatWeeklyData).filter(
        func.lower(SurvstatWeeklyData.disease).like("%mycoplas%"),
        SurvstatWeeklyData.bundesland != "Gesamt",
    ).order_by(SurvstatWeeklyData.week_start.desc()).all()
    if not rows:
        return []

    grouped: dict[str, list[SurvstatWeeklyData]] = {}
    for row in rows:
        code = REGION_NAME_TO_CODE.get(str(row.bundesland or "").strip().lower())
        if not code or code not in allowed_regions:
            continue
        grouped.setdefault(code, []).append(row)

    candidates: list[dict[str, Any]] = []
    for code, values in grouped.items():
        series = sorted(values, key=lambda item: item.week_start)
        if len(series) < 2:
            continue

        latest = float(series[-1].incidence or 0.0)
        prev = float(series[-2].incidence or 0.0)
        wow = ((latest - prev) / prev) if prev > 0 else (1.0 if latest > 0 else 0.0)
        history = [float(v.incidence or 0.0) for v in series if v.incidence is not None]
        p75 = engine._p75(history)
        seasonal_hit = latest >= p75 and latest > 0

        peix_entry = peix_regions.get(code) or {}
        peix_score = float(peix_entry.get("score_0_100") or 0.0)
        damp = 0.78 if peix_score > 85 else 1.0

        trigger_active = wow >= 0.30 or seasonal_hit
        if not trigger_active:
            continue

        strength = min(
            100.0,
            max(
                0.0,
                ((45.0 + max(0.0, wow) * 70.0 + (15.0 if seasonal_hit else 0.0)) * damp),
            ),
        )
        confidence = min(96.0, 62.0 + min(22.0, len(history) / 4.0))
        priority = engine._priority_score(trigger_strength=strength, confidence=confidence)
        shift_pct = engine._shift_from_strength("MYCOPLASMA_JAEGER", strength)

        candidates.append(
            engine._candidate_payload(
                playbook_key="MYCOPLASMA_JAEGER",
                region_code=code,
                peix_entry=peix_entry,
                trigger_strength=strength,
                confidence=confidence,
                priority_score=priority,
                budget_shift_pct=shift_pct,
                trigger_snapshot={
                    "source": "RKI SURVSTAT",
                    "event": "MYCOPLASMA_WOW_SPIKE",
                    "details": (
                        f"Mycoplasma-Inzidenz {latest:.1f} vs. {prev:.1f} Vorwoche "
                        f"({wow * 100:+.1f}% WoW, p75={p75:.1f})."
                    ),
                    "lead_time_days": 10,
                    "values": {
                        "latest_incidence": round(latest, 3),
                        "previous_incidence": round(prev, 3),
                        "wow_pct": round(wow * 100.0, 2),
                        "p75": round(p75, 3),
                    },
                },
            )
        )
    return candidates


def supply_candidates(
    engine,
    *,
    peix_regions: dict[str, Any],
    allowed_regions: list[str],
) -> list[dict[str, Any]]:
    signals = get_cached_signals() or {}
    risk = float(signals.get("current_risk_score") or 0.0)
    if risk < 70.0:
        return []

    by_category = signals.get("by_category") or {}
    respiratory_shortage = float((by_category.get("Atemwege") or {}).get("high_demand") or 0.0)
    pediatric_shortage = float((by_category.get("Antibiotika") or {}).get("pediatric") or 0.0)
    pediatric_alert = bool(signals.get("pediatric_alert"))
    wave_type = str(signals.get("wave_type") or "n/a")

    are_growth = engine._are_growth_by_region()
    candidates: list[dict[str, Any]] = []
    for code in allowed_regions:
        peix_entry = peix_regions.get(code) or {}
        growth = are_growth.get(code, 0.0)
        growth_score = min(100.0, max(0.0, growth * 100.0))
        if growth_score < 10.0 and respiratory_shortage <= 0:
            continue
        bonus = 8.0 if pediatric_alert else 0.0
        if respiratory_shortage <= 0 and pediatric_shortage <= 0:
            bonus -= 10.0
        strength = min(100.0, max(0.0, risk * 0.65 + growth_score * 0.35 + bonus))
        if strength < 40.0:
            continue
        confidence = min(95.0, 68.0 + min(20.0, respiratory_shortage * 3.0) + (5.0 if pediatric_alert else 0.0))
        priority = engine._priority_score(trigger_strength=strength, confidence=confidence)
        shift_pct = engine._shift_from_strength("SUPPLY_SHOCK_ATTACK", strength)

        candidates.append(
            engine._candidate_payload(
                playbook_key="SUPPLY_SHOCK_ATTACK",
                region_code=code,
                peix_entry=peix_entry,
                trigger_strength=strength,
                confidence=confidence,
                priority_score=priority,
                budget_shift_pct=shift_pct,
                trigger_snapshot={
                    "source": "BfArM + RKI",
                    "event": "SUPPLY_SHOCK_WINDOW",
                    "details": (
                        f"BfArM Risiko {risk:.1f}/100 (Welle: {wave_type}), "
                        f"Atemwegs-Engpässe={respiratory_shortage:.0f}, "
                        f"ARE-Wachstum {growth * 100.0:+.1f}%."
                    ),
                    "lead_time_days": 7,
                    "values": {
                        "bfarm_risk_score": round(risk, 2),
                        "respiratory_shortage_count": respiratory_shortage,
                        "pediatric_alert": pediatric_alert,
                        "are_growth_pct": round(growth * 100.0, 2),
                    },
                },
            )
        )
    return candidates


def weather_candidates(
    engine,
    *,
    peix_regions: dict[str, Any],
    allowed_regions: list[str],
) -> list[dict[str, Any]]:
    weather_burden = engine._weather_burden_by_region()
    if not weather_burden:
        return []
    psycho = engine._google_signal_score(["immunsystem", "erkältung", "husten", "bronchitis"])

    candidates: list[dict[str, Any]] = []
    for code in allowed_regions:
        burden = float(weather_burden.get(code) or 0.0)
        peix_entry = peix_regions.get(code) or {}
        if burden < 45.0:
            continue

        psycho_level = float(psycho.get("current") or 0.0)
        psycho_delta = float(psycho.get("delta") or 0.0)
        psycho_score = max(0.0, min(100.0, psycho_level + max(0.0, psycho_delta) * 1.2))
        strength = min(100.0, max(0.0, burden * 0.65 + psycho_score * 0.35))
        if strength < 42.0:
            continue

        confidence = min(92.0, 60.0 + (12.0 if burden >= 60 else 5.0) + (8.0 if psycho_delta > 0 else 0.0))
        priority = engine._priority_score(trigger_strength=strength, confidence=confidence)
        shift_pct = engine._shift_from_strength("WETTER_REFLEX", strength)

        candidates.append(
            engine._candidate_payload(
                playbook_key="WETTER_REFLEX",
                region_code=code,
                peix_entry=peix_entry,
                trigger_strength=strength,
                confidence=confidence,
                priority_score=priority,
                budget_shift_pct=shift_pct,
                trigger_snapshot={
                    "source": "DWD/BrightSky + Google Trends",
                    "event": "WETTER_BELASTUNG_PLUS_PSYCHO",
                    "details": (
                        f"8-Tage Wetterdruck {burden:.1f}/100, "
                        f"Psycho-Signal {psycho_level:.1f}/100 ({psycho_delta:+.1f} Delta)."
                    ),
                    "lead_time_days": 8,
                    "values": {
                        "weather_burden": round(burden, 2),
                        "psycho_level": round(psycho_level, 2),
                        "psycho_delta": round(psycho_delta, 2),
                    },
                },
            )
        )
    return candidates


def allergy_candidates(
    engine,
    *,
    peix_regions: dict[str, Any],
    allowed_regions: list[str],
) -> list[dict[str, Any]]:
    pollen = engine._pollen_by_region()
    if not pollen:
        return []
    allergy = engine._google_signal_score(["heuschnupfen", "pollenallergie", "augen jucken", "laufende nase"])

    candidates: list[dict[str, Any]] = []
    for code in allowed_regions:
        pollen_score = float(pollen.get(code) or 0.0)
        if pollen_score < 45.0:
            continue

        peix_entry = peix_regions.get(code) or {}
        peix_score = float(peix_entry.get("score_0_100") or 0.0)
        allergy_level = float(allergy.get("current") or 0.0)
        allergy_delta = float(allergy.get("delta") or 0.0)
        allergy_score = max(0.0, min(100.0, allergy_level + max(0.0, allergy_delta) * 1.2))
        if peix_score >= 60.0 and allergy_score < 60.0:
            continue

        strength = min(
            100.0,
            max(0.0, pollen_score * 0.45 + allergy_score * 0.35 + (100.0 - peix_score) * 0.20),
        )
        if strength < 50.0:
            continue

        confidence = min(94.0, 66.0 + (12.0 if pollen_score >= 60 else 4.0) + (8.0 if allergy_delta > 0 else 0.0))
        priority = engine._priority_score(trigger_strength=strength, confidence=confidence)
        shift_pct = engine._shift_from_strength("ALLERGIE_BREMSE", strength)

        candidates.append(
            engine._candidate_payload(
                playbook_key="ALLERGIE_BREMSE",
                region_code=code,
                peix_entry=peix_entry,
                trigger_strength=strength,
                confidence=confidence,
                priority_score=priority,
                budget_shift_pct=shift_pct,
                trigger_snapshot={
                    "source": "DWD Pollen + Google Trends + Peix",
                    "event": "ALLERGY_FALSE_POSITIVE_FILTER",
                    "details": (
                        f"Pollen {pollen_score:.1f}/100, Allergie-Suche {allergy_level:.1f}/100 "
                        f"({allergy_delta:+.1f}), Peix {peix_score:.1f}/100."
                    ),
                    "lead_time_days": 2,
                    "values": {
                        "pollen_score": round(pollen_score, 2),
                        "allergy_search_level": round(allergy_level, 2),
                        "allergy_search_delta": round(allergy_delta, 2),
                        "peix_score": round(peix_score, 2),
                    },
                },
            )
        )
    return candidates


def halsschmerz_candidates(
    engine,
    *,
    peix_regions: dict[str, Any],
    allowed_regions: list[str],
) -> list[dict[str, Any]]:
    rows = engine.db.query(SurvstatWeeklyData).filter(
        SurvstatWeeklyData.disease_cluster == "RESPIRATORY",
        SurvstatWeeklyData.bundesland != "Gesamt",
    ).order_by(SurvstatWeeklyData.week_start.desc()).limit(2000).all()
    if not rows:
        return []

    grouped: dict[str, list[float]] = {}
    for row in rows:
        code = REGION_NAME_TO_CODE.get(str(row.bundesland or "").strip().lower())
        if not code or code not in allowed_regions:
            continue
        grouped.setdefault(code, []).append(float(row.incidence or 0.0))

    candidates: list[dict[str, Any]] = []
    for code, values in grouped.items():
        if len(values) < 2:
            continue
        avg_recent = sum(values[:4]) / min(4, len(values))
        avg_old = sum(values[4:8]) / max(1, min(4, len(values[4:8]))) if len(values) > 4 else avg_recent * 0.8
        growth = (avg_recent - avg_old) / max(1.0, avg_old)

        if growth < 0.10 and avg_recent < 50:
            continue

        peix_entry = peix_regions.get(code) or {}
        strength = min(100.0, max(0.0, 40.0 + growth * 80.0 + min(20.0, avg_recent / 10.0)))
        confidence = min(90.0, 55.0 + min(25.0, len(values) / 3.0))
        priority = engine._priority_score(trigger_strength=strength, confidence=confidence)
        shift_pct = engine._shift_from_strength("HALSSCHMERZ_HUNTER", strength)

        candidates.append(
            engine._candidate_payload(
                playbook_key="HALSSCHMERZ_HUNTER",
                region_code=code,
                peix_entry=peix_entry,
                trigger_strength=strength,
                confidence=confidence,
                priority_score=priority,
                budget_shift_pct=shift_pct,
                trigger_snapshot={
                    "source": "RKI SURVSTAT",
                    "event": "RESPIRATORY_GROWTH_HALSSCHMERZ",
                    "details": (
                        f"Atemwegs-Inzidenz Ø{avg_recent:.1f} (Wachstum {growth * 100:+.1f}%), "
                        f"Halsschmerz-Kampagne empfohlen."
                    ),
                    "lead_time_days": 7,
                    "values": {
                        "avg_recent_incidence": round(avg_recent, 2),
                        "growth_pct": round(growth * 100, 2),
                    },
                },
            )
        )
    return candidates


def erkaeltungswelle_candidates(
    engine,
    *,
    peix_regions: dict[str, Any],
    allowed_regions: list[str],
) -> list[dict[str, Any]]:
    rows = engine.db.query(SurvstatWeeklyData).filter(
        SurvstatWeeklyData.bundesland != "Gesamt",
        SurvstatWeeklyData.disease_cluster.in_(["RESPIRATORY", "GASTROINTESTINAL"]),
    ).order_by(SurvstatWeeklyData.week_start.desc()).limit(3000).all()
    if not rows:
        return []

    grouped: dict[str, float] = {}
    for row in rows:
        code = REGION_NAME_TO_CODE.get(str(row.bundesland or "").strip().lower())
        if not code or code not in allowed_regions:
            continue
        grouped[code] = grouped.get(code, 0.0) + float(row.incidence or 0.0)

    candidates: list[dict[str, Any]] = []
    if not grouped:
        return []
    median_load = sorted(grouped.values())[len(grouped) // 2]

    for code, total_load in grouped.items():
        if total_load < median_load * 1.1:
            continue

        peix_entry = peix_regions.get(code) or {}
        relative = total_load / max(1.0, median_load)
        strength = min(100.0, max(0.0, 35.0 + (relative - 1.0) * 140.0))
        confidence = min(88.0, 60.0 + min(20.0, total_load / 50.0))
        priority = engine._priority_score(trigger_strength=strength, confidence=confidence)
        shift_pct = engine._shift_from_strength("ERKAELTUNGSWELLE", strength)

        candidates.append(
            engine._candidate_payload(
                playbook_key="ERKAELTUNGSWELLE",
                region_code=code,
                peix_entry=peix_entry,
                trigger_strength=strength,
                confidence=confidence,
                priority_score=priority,
                budget_shift_pct=shift_pct,
                trigger_snapshot={
                    "source": "RKI SURVSTAT",
                    "event": "BROAD_INFECTION_WAVE",
                    "details": (
                        f"Gesamtlast {total_load:.0f} (Median {median_load:.0f}, "
                        f"{relative:.1f}x), breite Erkältungswelle."
                    ),
                    "lead_time_days": 5,
                    "values": {
                        "total_infection_load": round(total_load, 1),
                        "median_load": round(median_load, 1),
                        "relative_to_median": round(relative, 2),
                    },
                },
            )
        )
    return candidates


def sinus_candidates(
    engine,
    *,
    peix_regions: dict[str, Any],
    allowed_regions: list[str],
) -> list[dict[str, Any]]:
    rows = engine.db.query(SurvstatWeeklyData).filter(
        func.lower(SurvstatWeeklyData.disease).in_([
            "rsv (meldepflicht gemäß ifsg)",
            "pneumokokken (meldepflicht gemäß ifsg)",
        ]),
        SurvstatWeeklyData.bundesland != "Gesamt",
    ).order_by(SurvstatWeeklyData.week_start.desc()).limit(1500).all()
    if not rows:
        return []

    grouped: dict[str, list[float]] = {}
    for row in rows:
        code = REGION_NAME_TO_CODE.get(str(row.bundesland or "").strip().lower())
        if not code or code not in allowed_regions:
            continue
        grouped.setdefault(code, []).append(float(row.incidence or 0.0))

    candidates: list[dict[str, Any]] = []
    for code, values in grouped.items():
        if len(values) < 2:
            continue
        avg_recent = sum(values[:4]) / min(4, len(values))
        if avg_recent < 5.0:
            continue

        peix_entry = peix_regions.get(code) or {}
        strength = min(100.0, max(0.0, 30.0 + min(70.0, avg_recent * 0.7)))
        confidence = min(85.0, 50.0 + min(25.0, len(values) / 3.0))
        priority = engine._priority_score(trigger_strength=strength, confidence=confidence)
        shift_pct = engine._shift_from_strength("SINUS_DEFENDER", strength)

        candidates.append(
            engine._candidate_payload(
                playbook_key="SINUS_DEFENDER",
                region_code=code,
                peix_entry=peix_entry,
                trigger_strength=strength,
                confidence=confidence,
                priority_score=priority,
                budget_shift_pct=shift_pct,
                trigger_snapshot={
                    "source": "RKI SURVSTAT",
                    "event": "RSV_PNEUMO_SINUS_SIGNAL",
                    "details": (
                        f"RSV/Pneumokokken Ø-Inzidenz {avg_recent:.1f}, "
                        f"Nasennebenhöhlen-Kampagne empfohlen."
                    ),
                    "lead_time_days": 10,
                    "values": {
                        "avg_recent_incidence": round(avg_recent, 2),
                    },
                },
            )
        )
    return candidates
