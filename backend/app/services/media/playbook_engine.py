"""Playbook Engine für KI-gestützte Kampagnenkarten.

Erzeugt regionalspezifische Playbook-Kandidaten aus:
- Ranking-Signal (safe projection)
- SURVSTAT (Mycoplasma)
- BfArM Lieferengpass-Signalen
- Wetter + Google Trends
- DWD Pollen
"""

from __future__ import annotations

from statistics import quantiles
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.media.ranking_signal_service import RankingSignalService


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
        peix = RankingSignalService(self.db).build(virus_typ=virus_typ)
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
                "ranking_signal_generated_at": peix.get("generated_at"),
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
            "ranking_signal_generated_at": peix.get("generated_at"),
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
        from app.services.media import playbook_engine_candidates

        return playbook_engine_candidates.mycoplasma_candidates(
            self,
            peix_regions=peix_regions,
            allowed_regions=allowed_regions,
        )

    def _supply_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        from app.services.media import playbook_engine_candidates

        return playbook_engine_candidates.supply_candidates(
            self,
            peix_regions=peix_regions,
            allowed_regions=allowed_regions,
        )

    def _wetter_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        from app.services.media import playbook_engine_candidates

        return playbook_engine_candidates.weather_candidates(
            self,
            peix_regions=peix_regions,
            allowed_regions=allowed_regions,
        )

    def _allergy_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        from app.services.media import playbook_engine_candidates

        return playbook_engine_candidates.allergy_candidates(
            self,
            peix_regions=peix_regions,
            allowed_regions=allowed_regions,
        )

    def _halsschmerz_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        from app.services.media import playbook_engine_candidates

        return playbook_engine_candidates.halsschmerz_candidates(
            self,
            peix_regions=peix_regions,
            allowed_regions=allowed_regions,
        )

    def _erkaeltungswelle_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        from app.services.media import playbook_engine_candidates

        return playbook_engine_candidates.erkaeltungswelle_candidates(
            self,
            peix_regions=peix_regions,
            allowed_regions=allowed_regions,
        )

    def _sinus_candidates(
        self,
        *,
        peix_regions: dict[str, Any],
        allowed_regions: list[str],
    ) -> list[dict[str, Any]]:
        from app.services.media import playbook_engine_candidates

        return playbook_engine_candidates.sinus_candidates(
            self,
            peix_regions=peix_regions,
            allowed_regions=allowed_regions,
        )

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
            "ranking_signal_score": round(float(peix_entry.get("score_0_100") or 0.0), 2),
            "peix_score": round(float(peix_entry.get("score_0_100") or 0.0), 2),
            "signal_band": peix_entry.get("risk_band"),
            "peix_band": peix_entry.get("risk_band"),
            "signal_drivers": peix_entry.get("top_drivers") or [],
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
        from app.services.media import playbook_engine_signals

        return playbook_engine_signals.are_growth_by_region(self)

    def _weather_burden_by_region(self) -> dict[str, float]:
        from app.services.media import playbook_engine_signals

        return playbook_engine_signals.weather_burden_by_region(self)

    def _pollen_by_region(self) -> dict[str, float]:
        from app.services.media import playbook_engine_signals

        return playbook_engine_signals.pollen_by_region(self)

    def _google_signal_score(self, keywords: list[str]) -> dict[str, float]:
        from app.services.media import playbook_engine_signals

        return playbook_engine_signals.google_signal_score(self, keywords)

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
