import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class EpidemiologicalRiskEngine:

    @staticmethod
    def apply_nowcasting(reported_cases: float, days_ago: int, source_type: str) -> float:
        """
        Differenziertes Nowcasting: Leading Indicator (Abwasser) vs. Lagging Indicator (Behörden).
        """
        source_type = source_type.lower()

        if source_type == 'amelag':
            # Abwasserdaten: Sehr nah an der Realität, kaum Meldeverzug
            # Spiegelt asymptomatische und präsymptomatische Fälle wider.
            if days_ago <= 7:
                return reported_cases * 1.05  # Nur minimaler Aufschlag für aktuellen Laborverzug
            return reported_cases

        elif source_type in ['survstat', 'grippeweb']:
            # RKI-Meldedaten: Extremer Meldeverzug (Krank -> Arzt -> Labor -> Amt -> RKI)
            if days_ago == 0:
                return reported_cases * 2.5
            elif days_ago <= 3:
                return reported_cases * 1.8
            elif days_ago <= 7:
                return reported_cases * 1.3
            elif days_ago <= 14:
                return reported_cases * 1.1
            return reported_cases

        return reported_cases

    @staticmethod
    def calculate_environmental_catalyst(
        temp_c: float,
        humidity_pct: float,
        pm25: float,
        pollen_index: float,
        is_winter: bool
    ) -> float:
        """
        Environmental Vulnerability Index (EVI).
        Katalysator basierend auf Aerosol-Physik und Schleimhaut-Integrität.
        """
        multiplier = 1.0

        # 1. Feinstaub (PM2.5) reizt ganzjährig die Atemwege und dient als Virus-Vehikel
        if pm25 > 15.0:  # WHO Richtwert überschritten
            multiplier += (pm25 - 15.0) * 0.005

        if is_winter:
            # WINTER: Kälte + Trockene Luft (Aerosole schweben länger, Schleimhaut trocknet aus)
            if temp_c < 5.0:
                multiplier += 0.10
            # Trockene Heizungsluft ist der stärkste Treiber für Aerosol-Stabilität
            if humidity_pct < 40.0:
                multiplier += 0.15
        else:
            # SOMMER: Pollen nicht mehr im allgemeinen PeixEpiScore —
            # wirkt nur noch produktspezifisch über das ALLERGIE_BREMSE-Playbook (GeloSitin).
            # Hohe Luftfeuchtigkeit + Hitze belasten das Herz-Kreislauf-System (Sommergrippe)
            if temp_c > 25.0 and humidity_pct > 60.0:
                multiplier += 0.05

        return min(multiplier, 2.5)  # Cap auf maximal +150% Impact, um Ausreißer zu vermeiden

    @staticmethod
    def calculate_outbreak_score(
        base_incidence: float,
        temp_c: float,
        humidity_pct: float,
        pm25: float,
        pollen_index: float,
        competitor_stockout: bool,
        is_winter: bool = True
    ) -> Dict[str, Any]:
        """
        MULTIPLIKATIVE Logik: Basisrisiko * Umwelt-Katalysator * Marktchance.
        """
        # 1. Base Risk (Normalisiert auf 0-100)
        base_risk = min(100.0, (base_incidence / 500.0) * 100)

        # 2. Synergistische Multiplikatoren (EVI)
        env_multiplier = EpidemiologicalRiskEngine.calculate_environmental_catalyst(
            temp_c, humidity_pct, pm25, pollen_index, is_winter
        )

        # 3. Markt-Multiplikator (Wettbewerber-Lieferengpass = Massive Chance)
        market_multiplier = 1.4 if competitor_stockout else 1.0

        # Finale Berechnung
        raw_score = base_risk * env_multiplier * market_multiplier
        final_score = min(100.0, raw_score)

        # Explainable AI (XAI) Output für das Dashboard
        return {
            "total_score": round(final_score, 1),
            "factors": {
                "base_viral_risk_pct": round(base_risk, 1),
                "environmental_catalyst_bonus_pct": round((env_multiplier - 1) * 100, 1),
                "competitor_opportunity_bonus_pct": round((market_multiplier - 1) * 100, 1)
            }
        }

