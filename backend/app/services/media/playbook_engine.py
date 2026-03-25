"""Playbook Engine für KI-gestützte Kampagnenkarten.

Erzeugt regionalspezifische Playbook-Kandidaten aus:
- PeixEpiScore (safe projection)
- SURVSTAT (Mycoplasma)
- BfArM Lieferengpass-Signalen
- Wetter + Google Trends
- DWD Pollen
"""

from __future__ import annotations
from app.core.time import utc_now

from datetime import datetime, timedelta
from statistics import quantiles
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import (
    AREKonsultation,
    GoogleTrendsData,
    PollenData,
    SurvstatWeeklyData,
    WeatherData,
)
from app.services.data_ingest.bfarm_service import get_cached_signals
from app.services.data_ingest.weather_service import CITY_STATE_MAP
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


PLAYBOOK_CATALOG: dict[str, dict[str, Any]] = {
    "MYCOPLASMA_JAEGER": {
        "title": "Mycoplasma-Jäger",
        "description": "Spezifisches Husten-Targeting bei Mycoplasma-Sprung.",
        "channels": ["search", "youtube", "social"],
        "default_mix": {"search": 45.0, "youtube": 30.0, "social": 25.0},
        "shift_min": 20.0,
        "shift_max": 45.0,
        "condition_key": "bronchitis_husten",
        "message_direction": "Hartnäckiger Dauerhusten / festsitzender Schleim",
        "kind": "offensive",
    },
    "SUPPLY_SHOCK_ATTACK": {
        "title": "Supply-Shock Attack",
        "description": "Konkurrenzknappheit nutzen und Verfügbarkeit ausspielen.",
        "channels": ["mobile", "social", "programmatic"],
        "default_mix": {"mobile": 35.0, "social": 35.0, "programmatic": 30.0},
        "shift_min": 25.0,
        "shift_max": 55.0,
        "condition_key": "bronchitis_husten",
        "message_direction": "Verfügbarkeit jetzt / Alternative bei Engpass",
        "kind": "offensive",
    },
    "WETTER_REFLEX": {
        "title": "Wetter-Reflex",
        "description": "Präventive Aktivierung bei belastender Wetterlage.",
        "channels": ["dooh", "social", "programmatic"],
        "default_mix": {"dooh": 40.0, "social": 35.0, "programmatic": 25.0},
        "shift_min": 10.0,
        "shift_max": 30.0,
        "condition_key": "rhinitis_trockene_nase",
        "message_direction": "Präventive Positionierung vor Welle",
        "kind": "offensive",
    },
    "ALLERGIE_BREMSE": {
        "title": "Allergie-Bremse",
        "description": "False Positives vermeiden und Budget einfrieren.",
        "channels": ["search", "social"],
        "default_mix": {"search": 55.0, "social": 45.0},
        "shift_min": -100.0,
        "shift_max": -80.0,
        "condition_key": "rhinitis_trockene_nase",
        "message_direction": "Budget sparen bei Allergie-getriebenen Signalen",
        "kind": "efficiency",
    },
    "HALSSCHMERZ_HUNTER": {
        "title": "Halsschmerz-Hunter",
        "description": "Halsschmerz-Targeting bei steigenden Atemwegsinfekten.",
        "channels": ["search", "social", "programmatic"],
        "default_mix": {"search": 40.0, "social": 35.0, "programmatic": 25.0},
        "shift_min": 15.0,
        "shift_max": 40.0,
        "condition_key": "halsschmerz_heiserkeit",
        "message_direction": "Halsschmerzen lindern / Stimme schützen",
        "kind": "offensive",
    },
    "ERKAELTUNGSWELLE": {
        "title": "Erkältungswelle",
        "description": "Breites Erkältungs-Targeting bei hoher Infektionslast.",
        "channels": ["programmatic", "social", "dooh"],
        "default_mix": {"programmatic": 40.0, "social": 35.0, "dooh": 25.0},
        "shift_min": 20.0,
        "shift_max": 50.0,
        "condition_key": "erkaltung_akut",
        "message_direction": "Schnelle Hilfe bei Erkältung / Symptomlinderung",
        "kind": "offensive",
    },
    "SINUS_DEFENDER": {
        "title": "Sinus-Defender",
        "description": "Nasennebenhöhlen-Targeting bei RSV/Pneumokokken-Signalen.",
        "channels": ["search", "programmatic", "social"],
        "default_mix": {"search": 45.0, "programmatic": 30.0, "social": 25.0},
        "shift_min": 15.0,
        "shift_max": 35.0,
        "condition_key": "sinusitis_nebenhoehlen",
        "message_direction": "Nasennebenhöhlen befreien / Durchatmen",
        "kind": "offensive",
    },
}


class PlaybookEngine:
    """Playbook-Selektion mit festen Triggern und Priorisierungslogik."""

    def __init__(self, db: Session):
        self.db = db

    def get_catalog(self) -> list[dict[str, Any]]:
        items = []
        for key, cfg in PLAYBOOK_CATALOG.items():
            items.append(
                {
                    "key": key,
                    "title": cfg["title"],
                    "description": cfg["description"],
                    "channels": cfg["channels"],
                    "default_mix": cfg["default_mix"],
                    "shift_min": cfg["shift_min"],
                    "shift_max": cfg["shift_max"],
                    "condition_key": cfg["condition_key"],
                    "message_direction": cfg["message_direction"],
                    "kind": cfg["kind"],
                }
            )
        return items

    def select_candidates(
        self,
        *,
        virus_typ: str = "Influenza A",
        region_scope: list[str] | None = None,
        max_cards: int = 4,
    ) -> dict[str, Any]:
        peix = PeixEpiScoreService(self.db).build(virus_typ=virus_typ)
        normalized_scope = self._normalize_region_scope(region_scope)
        allowed_regions = normalized_scope or sorted(BUNDESLAND_NAMES.keys())

        myco = self._mycoplasma_candidates(peix_regions=peix.get("regions") or {}, allowed_regions=allowed_regions)
        supply = self._supply_candidates(peix_regions=peix.get("regions") or {}, allowed_regions=allowed_regions)
        weather = self._wetter_candidates(peix_regions=peix.get("regions") or {}, allowed_regions=allowed_regions)
        allergy = self._allergy_candidates(peix_regions=peix.get("regions") or {}, allowed_regions=allowed_regions)
        hals = self._halsschmerz_candidates(peix_regions=peix.get("regions") or {}, allowed_regions=allowed_regions)
        erkaelt = self._erkaeltungswelle_candidates(peix_regions=peix.get("regions") or {}, allowed_regions=allowed_regions)
        sinus = self._sinus_candidates(peix_regions=peix.get("regions") or {}, allowed_regions=allowed_regions)
        all_candidates = myco + supply + weather + allergy + hals + erkaelt + sinus
        if not all_candidates:
            return {
                "selected": [],
                "all_candidates": [],
                "peix_generated_at": peix.get("generated_at"),
                "debug": {"reason": "no_trigger_data"},
            }

        # Eindeutig nach (region, playbook), höchster priority_score gewinnt.
        dedup: dict[tuple[str, str], dict[str, Any]] = {}
        for item in all_candidates:
            key = (item["region_code"], item["playbook_key"])
            current = dedup.get(key)
            if current is None or float(item["priority_score"]) > float(current["priority_score"]):
                dedup[key] = item
        ranked = sorted(
            dedup.values(),
            key=lambda row: float(row.get("priority_score") or 0.0),
            reverse=True,
        )

        offensive = [row for row in ranked if PLAYBOOK_CATALOG[row["playbook_key"]]["kind"] == "offensive"]
        efficiency = [row for row in ranked if PLAYBOOK_CATALOG[row["playbook_key"]]["kind"] == "efficiency"]

        # Diversitäts-Auswahl: ein Candidate pro Condition (= Produkt),
        # dann auffüllen mit den stärksten Signalen.
        selected: list[dict[str, Any]] = []
        seen_conditions: set[str] = set()
        for row in offensive:
            cond = row.get("condition_key", "")
            if cond not in seen_conditions:
                selected.append(row)
                seen_conditions.add(cond)
        # Auffüllen: Top-Offensive die noch nicht drin sind
        for row in offensive:
            if row not in selected:
                selected.append(row)
        # Maximal 1 Efficiency-Playbook anhängen
        if efficiency:
            selected.append(efficiency[0])

        selected = selected[: max(1, int(max_cards or 8))]
        return {
            "selected": selected,
            "all_candidates": ranked,
            "peix_generated_at": peix.get("generated_at"),
            "debug": {
                "counts": {
                    "mycoplasma": len(myco),
                    "supply": len(supply),
                    "wetter": len(weather),
                    "allergie": len(allergy),
                    "halsschmerz": len(hals),
                    "erkaeltung": len(erkaelt),
                    "sinus": len(sinus),
                }
            },
        }

    def _mycoplasma_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        rows = self.db.query(SurvstatWeeklyData).filter(
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
            p75 = self._p75(history)
            seasonal_hit = latest >= p75 and latest > 0

            peix_entry = peix_regions.get(code) or {}
            peix_score = float(peix_entry.get("score_0_100") or 0.0)
            if peix_score > 85:
                # Zu breite Gesamtwelle: spezifischer Mycoplasma-Playbook-Wert sinkt.
                damp = 0.78
            else:
                damp = 1.0

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
            priority = self._priority_score(trigger_strength=strength, confidence=confidence)
            shift_pct = self._shift_from_strength("MYCOPLASMA_JAEGER", strength)

            candidates.append(
                self._candidate_payload(
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

    def _supply_candidates(
        self,
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

        are_growth = self._are_growth_by_region()
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
            priority = self._priority_score(trigger_strength=strength, confidence=confidence)
            shift_pct = self._shift_from_strength("SUPPLY_SHOCK_ATTACK", strength)

            candidates.append(
                self._candidate_payload(
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

    def _wetter_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        weather_burden = self._weather_burden_by_region()
        if not weather_burden:
            return []
        psycho = self._google_signal_score(["immunsystem", "erkältung", "husten", "bronchitis"])

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
            priority = self._priority_score(trigger_strength=strength, confidence=confidence)
            shift_pct = self._shift_from_strength("WETTER_REFLEX", strength)

            candidates.append(
                self._candidate_payload(
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

    def _allergy_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        pollen = self._pollen_by_region()
        if not pollen:
            return []
        allergy = self._google_signal_score(["heuschnupfen", "pollenallergie", "augen jucken", "laufende nase"])

        candidates: list[dict[str, Any]] = []
        for code in allowed_regions:
            pollen_score = float(pollen.get(code) or 0.0)
            if pollen_score < 45.0:
                continue

            peix_entry = peix_regions.get(code) or {}
            peix_score = float(peix_entry.get("score_0_100") or 0.0)
            impact = float(peix_entry.get("impact_probability") or 0.0)
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
            priority = self._priority_score(trigger_strength=strength, confidence=confidence)
            shift_pct = self._shift_from_strength("ALLERGIE_BREMSE", strength)

            candidates.append(
                self._candidate_payload(
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

    def _halsschmerz_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        """Triggert bei steigenden Keuchhusten/Influenza-Inzidenzen (Halsschmerz-Proxy)."""
        rows = self.db.query(SurvstatWeeklyData).filter(
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
            priority = self._priority_score(trigger_strength=strength, confidence=confidence)
            shift_pct = self._shift_from_strength("HALSSCHMERZ_HUNTER", strength)

            candidates.append(
                self._candidate_payload(
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

    def _erkaeltungswelle_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        """Triggert bei breiter Infektionslast (COVID + Influenza + Noro kombiniert)."""
        rows = self.db.query(SurvstatWeeklyData).filter(
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
            priority = self._priority_score(trigger_strength=strength, confidence=confidence)
            shift_pct = self._shift_from_strength("ERKAELTUNGSWELLE", strength)

            candidates.append(
                self._candidate_payload(
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

    def _sinus_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        """Triggert bei RSV/Pneumokokken-Signalen (Sinusitis/Nasennebenhöhlen-Proxy)."""
        rows = self.db.query(SurvstatWeeklyData).filter(
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
            priority = self._priority_score(trigger_strength=strength, confidence=confidence)
            shift_pct = self._shift_from_strength("SINUS_DEFENDER", strength)

            candidates.append(
                self._candidate_payload(
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

    def _candidate_payload(
        self,
        *,
        playbook_key: str,
        region_code: str,
        peix_entry: dict[str, Any],
        trigger_strength: float,
        confidence: float,
        priority_score: float,
        budget_shift_pct: float,
        trigger_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        cfg = PLAYBOOK_CATALOG[playbook_key]
        return {
            "playbook_key": playbook_key,
            "playbook_title": cfg["title"],
            "playbook_kind": cfg["kind"],
            "condition_key": cfg["condition_key"],
            "message_direction": cfg["message_direction"],
            "region_code": region_code,
            "region_name": BUNDESLAND_NAMES.get(region_code, region_code),
            "impact_probability": round(float(peix_entry.get("impact_probability") or 0.0), 2),
            "peix_score": round(float(peix_entry.get("score_0_100") or 0.0), 2),
            "peix_band": peix_entry.get("risk_band"),
            "peix_drivers": peix_entry.get("top_drivers") or [],
            "trigger_strength": round(trigger_strength, 2),
            "confidence": round(confidence, 2),
            "priority_score": round(priority_score, 2),
            "budget_shift_pct": round(budget_shift_pct, 1),
            "channel_mix": cfg["default_mix"],
            "channels": cfg["channels"],
            "shift_bounds": {"min": cfg["shift_min"], "max": cfg["shift_max"]},
            "trigger_snapshot": trigger_snapshot,
        }

    @staticmethod
    def _priority_score(*, trigger_strength: float, confidence: float) -> float:
        """Priorität nur aus unabhängigen Signalen — PeixEpiScore fließt nicht ein."""
        return (
            0.6 * float(trigger_strength or 0.0)
            + 0.4 * float(confidence or 0.0)
        )

    @staticmethod
    def _shift_from_strength(playbook_key: str, strength: float) -> float:
        cfg = PLAYBOOK_CATALOG[playbook_key]
        low = float(cfg["shift_min"])
        high = float(cfg["shift_max"])
        norm = max(0.0, min(1.0, float(strength) / 100.0))
        if low <= high:
            return low + (high - low) * norm
        return low - (low - high) * norm

    def _are_growth_by_region(self) -> dict[str, float]:
        rows = self.db.query(AREKonsultation).filter(
            AREKonsultation.altersgruppe == "00+",
            AREKonsultation.bundesland != "Bundesweit",
        ).order_by(AREKonsultation.datum.desc()).all()
        grouped: dict[str, list[AREKonsultation]] = {}
        for row in rows:
            code = REGION_NAME_TO_CODE.get(str(row.bundesland or "").strip().lower())
            if not code:
                continue
            grouped.setdefault(code, []).append(row)

        growth: dict[str, float] = {}
        for code, values in grouped.items():
            series = sorted(values, key=lambda item: item.datum)
            if len(series) < 2:
                continue
            latest = float(series[-1].konsultationsinzidenz or 0.0)
            prev = float(series[-2].konsultationsinzidenz or 0.0)
            if prev <= 0:
                growth[code] = 0.0 if latest <= 0 else 1.0
            else:
                growth[code] = (latest - prev) / prev
        return growth

    def _weather_burden_by_region(self) -> dict[str, float]:
        now = utc_now()
        until = now + timedelta(days=8)
        rows = self.db.query(WeatherData).filter(
            WeatherData.data_type == "DAILY_FORECAST",
            WeatherData.datum >= now,
            WeatherData.datum <= until,
        ).all()
        if not rows:
            return {}

        per_region: dict[str, list[float]] = {}
        for row in rows:
            state = CITY_STATE_MAP.get(str(row.city or ""))
            if not state:
                continue
            code = REGION_NAME_TO_CODE.get(state.lower())
            if not code:
                continue

            temp = float(row.temperatur) if row.temperatur is not None else 7.0
            uv = float(row.uv_index) if row.uv_index is not None else 2.0
            rain_prob = float(row.niederschlag_wahrscheinlichkeit) if row.niederschlag_wahrscheinlichkeit is not None else 35.0
            rain_prob = rain_prob / 100.0 if rain_prob > 1.0 else rain_prob
            temp_factor = max(0.0, min(1.0, (10.0 - temp) / 12.0))
            uv_factor = max(0.0, min(1.0, (2.0 - uv) / 2.0))
            rain_factor = max(0.0, min(1.0, rain_prob))
            burden = (temp_factor * 0.45 + uv_factor * 0.20 + rain_factor * 0.35) * 100.0
            per_region.setdefault(code, []).append(burden)

        return {
            code: round(sum(values) / max(len(values), 1), 2)
            for code, values in per_region.items()
        }

    def _pollen_by_region(self) -> dict[str, float]:
        latest = self.db.query(func.max(PollenData.datum)).scalar()
        if not latest:
            return {}
        # Frische-Check: Keine Pollen-Daten älter als 3 Tage verwenden
        if (utc_now() - latest) > timedelta(days=3):
            return {}
        rows = self.db.query(
            PollenData.region_code,
            func.max(PollenData.pollen_index).label("max_index"),
        ).filter(
            PollenData.datum == latest,
        ).group_by(PollenData.region_code).all()
        return {
            str(row.region_code).upper(): round(max(0.0, min(100.0, (float(row.max_index or 0.0) / 3.0) * 100.0)), 2)
            for row in rows
        }

    def _google_signal_score(self, keywords: list[str]) -> dict[str, float]:
        now = utc_now()
        recent_start = now - timedelta(days=14)
        prev_start = now - timedelta(days=28)
        prev_end = recent_start

        base = self.db.query(func.avg(GoogleTrendsData.interest_score))
        recent = (
            base.filter(
                GoogleTrendsData.datum >= recent_start,
                GoogleTrendsData.datum <= now,
                self._keyword_filter(keywords),
            ).scalar()
            or 0.0
        )
        previous = (
            base.filter(
                GoogleTrendsData.datum >= prev_start,
                GoogleTrendsData.datum < prev_end,
                self._keyword_filter(keywords),
            ).scalar()
            or 0.0
        )
        return {
            "current": float(recent),
            "previous": float(previous),
            "delta": float(recent) - float(previous),
        }

    @staticmethod
    def _keyword_filter(keywords: list[str]):
        clause = None
        for keyword in keywords:
            item = func.lower(GoogleTrendsData.keyword).like(f"%{keyword.lower()}%")
            clause = item if clause is None else (clause | item)
        if clause is None:
            clause = func.lower(GoogleTrendsData.keyword).like("%")
        return clause

    @staticmethod
    def _p75(values: list[float]) -> float:
        clean = [float(v) for v in values if v is not None]
        if not clean:
            return 0.0
        if len(clean) == 1:
            return clean[0]
        try:
            return float(quantiles(clean, n=4)[2])
        except Exception:
            clean_sorted = sorted(clean)
            idx = int(0.75 * (len(clean_sorted) - 1))
            return float(clean_sorted[idx])

    @staticmethod
    def _normalize_region_scope(region_scope: list[str] | None) -> list[str]:
        if not region_scope:
            return []
        out: list[str] = []
        for item in region_scope:
            token = str(item or "").strip()
            if not token:
                continue
            upper = token.upper()
            if upper in BUNDESLAND_NAMES:
                out.append(upper)
                continue
            if token.lower() in {"gesamt", "all", "de", "national", "deutschland"}:
                return sorted(BUNDESLAND_NAMES.keys())
            mapped = REGION_NAME_TO_CODE.get(token.lower())
            if mapped:
                out.append(mapped)
        return sorted(set(out))
