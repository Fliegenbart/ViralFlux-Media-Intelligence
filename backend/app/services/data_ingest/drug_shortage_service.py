"""
DrugShortageAnalyzer — BfArM Lieferengpass-Analyse als Frühindikator für Infektionswellen.

These: Wenn Medikamente für Atemwegserkrankungen oder Antibiotika aufgrund
"Erhöhter Nachfrage" knapp werden, ist das ein Frühindikator für hohe Fallzahlen.

Datenquelle: BfArM LEMeldungen CSV (Semikolon-getrennt, Latin-1 Encoding).
"""

import pandas as pd
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


# ─── Keyword-Listen für Kategorisierung ──────────────────────────────────────

ANTIBIOTIKA_KEYWORDS = [
    'amoxicillin', 'penicillin', 'doxycyclin', 'azithromycin', 'cefuroxim',
    'ciprofloxacin', 'clarithromycin', 'erythromycin', 'metronidazol',
    'clindamycin', 'cotrimoxazol', 'trimethoprim', 'sulfamethoxazol',
    'moxifloxacin', 'levofloxacin', 'ceftriaxon', 'ampicillin',
    'piperacillin', 'tazobactam', 'vancomycin', 'linezolid',
    'isoniazid', 'rifampicin',
]

ATEMWEGE_KEYWORDS = [
    'xylometazolin', 'oxymetazolin', 'salbutamol', 'budesonid',
    'fluticason', 'beclometason', 'ipratropium', 'tiotropium',
    'montelukast', 'theophyllin', 'codein', 'dextromethorphan',
    'acetylcystein', 'ambroxol', 'bromhexin', 'noscapin',
    'nasenspray', 'inhalat', 'husten', 'bronch',
    'formoterol', 'salmeterol',
]

FIEBER_SCHMERZ_KEYWORDS = [
    'ibuprofen', 'paracetamol', 'acetylsalicyl', 'metamizol',
    'diclofenac', 'naproxen', 'dexketoprofen',
]

PEDIATRIC_KEYWORDS = [
    'saft', 'suspension', 'sirup', 'zäpfchen', 'suppositor',
    'tropfen zum einnehmen', 'granulat zum einnehmen',
    'kinder', 'junior', 'baby', 'pädiat', 'paediat',
]


class DrugShortageAnalyzer:
    """Analysiert BfArM-Lieferengpassmeldungen als Infektionswellen-Frühindikator."""

    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.df_filtered: Optional[pd.DataFrame] = None
        self._today = datetime.now().date()

    def load_and_clean(self, file_path: str) -> pd.DataFrame:
        """Lädt CSV, parst Datum, filtert nach Aktualität.

        Args:
            file_path: Pfad zur LEMeldungen CSV-Datei.

        Returns:
            Gefilterter DataFrame mit nur aktuell relevanten Meldungen.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV-Datei nicht gefunden: {file_path}")

        logger.info(f"Lade BfArM-Daten aus {file_path}")

        # Encoding: BfArM liefert Latin-1
        self.df = pd.read_csv(
            file_path,
            sep=';',
            encoding='latin-1',
            dtype=str,
            on_bad_lines='warn',
        )

        logger.info(f"Rohdaten geladen: {len(self.df)} Zeilen, {len(self.df.columns)} Spalten")

        # Datum parsen (DD.MM.YYYY)
        for col in ['Beginn', 'Ende', 'Datum der Erstmeldung', 'Datum der letzten Meldung']:
            if col in self.df.columns:
                self.df[col] = pd.to_datetime(
                    self.df[col], format='%d.%m.%Y', errors='coerce'
                )
                invalid = self.df[col].isna().sum()
                if invalid > 0:
                    logger.warning(f"Spalte '{col}': {invalid} ungültige Datumsformate")

        # ── Zeitliche Filterung ──
        today = pd.Timestamp(self._today)
        horizon = today + pd.Timedelta(days=28)

        # Ende in der Vergangenheit → raus
        has_end = self.df['Ende'].notna()
        past_end = has_end & (self.df['Ende'] < today)

        # A) Aktuell aktiv: Beginn <= heute AND (Ende >= heute OR Ende leer)
        active = (self.df['Beginn'] <= today) & (~past_end)

        # B) Startet bald: Beginn > heute AND Beginn <= heute + 28 Tage
        upcoming = (self.df['Beginn'] > today) & (self.df['Beginn'] <= horizon)

        self.df_filtered = self.df[active | upcoming].copy()
        logger.info(
            f"Nach Zeitfilter: {len(self.df_filtered)} relevante Meldungen "
            f"(von {len(self.df)} gesamt, {past_end.sum()} abgelaufen)"
        )

        # ── Kategorisierung ──
        self._add_signal_type()
        self._add_category()
        self._add_pediatric_flag()

        return self.df_filtered

    def _add_signal_type(self):
        """Setzt signal_type basierend auf dem Grund der Meldung."""
        grund = self.df_filtered['Grund'].fillna('').str.lower()
        self.df_filtered['signal_type'] = grund.apply(
            lambda g: 'High_Infection_Signal' if 'nachfrage' in g else 'Supply_Shock'
        )

    def _add_category(self):
        """Kategorisiert Arzneimittel nach Wirkstoff/Bezeichnung."""

        def categorize(row):
            text = (
                str(row.get('Wirkstoffe', '')) + ' ' +
                str(row.get('Arzneimittlbezeichnung', ''))
            ).lower()

            for kw in ANTIBIOTIKA_KEYWORDS:
                if kw in text:
                    return 'Antibiotika'
            for kw in ATEMWEGE_KEYWORDS:
                if kw in text:
                    return 'Atemwege'
            for kw in FIEBER_SCHMERZ_KEYWORDS:
                if kw in text:
                    return 'Fieber_Schmerz'
            return 'Sonstiges'

        self.df_filtered['category'] = self.df_filtered.apply(categorize, axis=1)

    def _add_pediatric_flag(self):
        """Setzt is_pediatric Flag für Kinder-Arzneimittel."""

        def check_pediatric(row):
            text = (
                str(row.get('Darreichungsform', '')) + ' ' +
                str(row.get('Arzneimittlbezeichnung', ''))
            ).lower()
            return any(kw in text for kw in PEDIATRIC_KEYWORDS)

        self.df_filtered['is_pediatric'] = self.df_filtered.apply(check_pediatric, axis=1)

    def get_infection_signals(self) -> dict:
        """Aggregiert Infektionswellen-Signale aus den Engpassmeldungen.

        Returns:
            Dict mit Risikobewertung, fehlenden Medikamenten und Wellentyp.
        """
        if self.df_filtered is None or self.df_filtered.empty:
            return {
                'current_risk_score': 0,
                'total_relevant_shortages': 0,
                'high_demand_shortages': 0,
                'top_missing_drugs': [],
                'wave_type': 'None',
                'pediatric_alert': False,
                'pediatric_shortages': 0,
                'by_category': {},
                'upcoming_shortages': 0,
                'analysis_date': self._today.isoformat(),
            }

        df = self.df_filtered

        # Zählung nach Signal-Typ
        high_demand = df[df['signal_type'] == 'High_Infection_Signal']
        supply_shock = df[df['signal_type'] == 'Supply_Shock']

        # Nur infektionsrelevante Kategorien für Score
        infection_relevant = df[df['category'].isin(['Antibiotika', 'Atemwege', 'Fieber_Schmerz'])]
        infection_high_demand = high_demand[
            high_demand['category'].isin(['Antibiotika', 'Atemwege', 'Fieber_Schmerz'])
        ]

        # ── Risk Score Berechnung (0-100) ──
        # Basiert auf: Anzahl "Erhöhte Nachfrage" in infektionsrelevanten Kategorien
        # Gewichtung: Antibiotika 3x, Atemwege 2.5x, Fieber/Schmerz 2x
        weights = {'Antibiotika': 3.0, 'Atemwege': 2.5, 'Fieber_Schmerz': 2.0}
        weighted_score = 0
        for cat, weight in weights.items():
            cat_count = len(infection_high_demand[infection_high_demand['category'] == cat])
            # Dedupliziere nach Bearbeitungsnummer (gleiche Meldung, verschiedene PZNs)
            if 'Bearbeitungsnummer' in infection_high_demand.columns:
                cat_unique = infection_high_demand[
                    infection_high_demand['category'] == cat
                ]['Bearbeitungsnummer'].nunique()
            else:
                cat_unique = cat_count
            weighted_score += cat_unique * weight

        # Pädiatrie-Bonus: Kinder-Engpässe bei Infektionsmitteln sind besonders alarmierend
        pediatric_infection = infection_high_demand[infection_high_demand['is_pediatric']]
        if len(pediatric_infection) > 0:
            weighted_score *= 1.3

        # Normalisierung auf 0-100 (Schwelle: 20 gewichtete Punkte = 100)
        risk_score = min(100, int(weighted_score / 20 * 100))

        # ── Top fehlende Medikamente ──
        # Dedupliziere nach Arzneimittlbezeichnung, priorisiere "Erhöhte Nachfrage"
        top_drugs = (
            infection_relevant
            .sort_values('signal_type', ascending=True)  # High_Infection_Signal first
            .drop_duplicates(subset=['Arzneimittlbezeichnung'], keep='first')
            ['Arzneimittlbezeichnung']
            .head(10)
            .tolist()
        )

        # ── Wellentyp bestimmen ──
        cat_counts = infection_high_demand['category'].value_counts()
        if cat_counts.empty:
            wave_type = 'None'
        elif cat_counts.index[0] == 'Antibiotika':
            wave_type = 'Bacterial'
        elif cat_counts.index[0] == 'Atemwege':
            wave_type = 'Respiratory_Viral'
        elif cat_counts.index[0] == 'Fieber_Schmerz':
            wave_type = 'General_Infection'
        else:
            wave_type = 'Mixed'

        # Wenn mehrere Kategorien stark vertreten sind → Mixed
        if len(cat_counts) >= 2:
            top2 = cat_counts.head(2)
            if top2.iloc[1] >= top2.iloc[0] * 0.5:
                wave_type = 'Mixed'

        # ── Kategorien-Breakdown ──
        by_category = {}
        for cat in ['Antibiotika', 'Atemwege', 'Fieber_Schmerz', 'Sonstiges']:
            cat_df = df[df['category'] == cat]
            cat_hd = high_demand[high_demand['category'] == cat] if not high_demand.empty else pd.DataFrame()
            by_category[cat] = {
                'total': len(cat_df),
                'high_demand': len(cat_hd),
                'unique_drugs': cat_df['Arzneimittlbezeichnung'].nunique() if not cat_df.empty else 0,
                'pediatric': int(cat_df['is_pediatric'].sum()) if not cat_df.empty else 0,
            }

        # ── Upcoming shortages (starten in den nächsten 28 Tagen) ──
        today = pd.Timestamp(self._today)
        upcoming = df[df['Beginn'] > today]

        # ── Pädiatrie-Alarm ──
        pediatric_total = df[df['is_pediatric']]
        pediatric_alert = len(pediatric_infection) >= 2

        return {
            'current_risk_score': risk_score,
            'total_relevant_shortages': len(df),
            'high_demand_shortages': len(high_demand),
            'supply_shock_shortages': len(supply_shock),
            'top_missing_drugs': top_drugs,
            'wave_type': wave_type,
            'pediatric_alert': pediatric_alert,
            'pediatric_shortages': len(pediatric_total),
            'by_category': by_category,
            'upcoming_shortages': len(upcoming),
            'analysis_date': self._today.isoformat(),
        }

    def get_weekly_trend(self) -> list:
        """Aggregiert Engpässe nach Beginn-Woche für Trendanalyse.

        Returns:
            Liste von Dicts mit wöchentlicher Aggregation.
        """
        if self.df_filtered is None or self.df_filtered.empty:
            return []

        df = self.df_filtered.copy()
        df['week'] = df['Beginn'].dt.isocalendar().week.astype(int)
        df['year'] = df['Beginn'].dt.year

        weekly = (
            df.groupby(['year', 'week', 'category', 'signal_type'])
            .agg(
                count=('PZN', 'count'),
                unique_drugs=('Arzneimittlbezeichnung', 'nunique'),
            )
            .reset_index()
        )

        return weekly.to_dict(orient='records')

    def get_summary_text(self) -> str:
        """Generiert einen kurzen deutschsprachigen Zusammenfassungstext."""
        signals = self.get_infection_signals()

        if signals['current_risk_score'] == 0:
            return "Keine infektionsrelevanten Lieferengpässe durch erhöhte Nachfrage erkannt."

        parts = []
        parts.append(
            f"Infektionswellen-Risiko: {signals['current_risk_score']}/100 "
            f"({signals['wave_type']})"
        )
        parts.append(
            f"{signals['high_demand_shortages']} Engpässe durch erhöhte Nachfrage, "
            f"davon {signals['by_category'].get('Antibiotika', {}).get('high_demand', 0)} Antibiotika, "
            f"{signals['by_category'].get('Atemwege', {}).get('high_demand', 0)} Atemwege, "
            f"{signals['by_category'].get('Fieber_Schmerz', {}).get('high_demand', 0)} Fieber/Schmerz."
        )

        if signals['pediatric_alert']:
            parts.append(
                f"KINDER-ALARM: {signals['pediatric_shortages']} pädiatrische Engpässe — "
                "mögliche Schul-/Kita-Welle."
            )

        if signals['top_missing_drugs']:
            parts.append(f"Top fehlend: {', '.join(signals['top_missing_drugs'][:5])}")

        return ' | '.join(parts)
