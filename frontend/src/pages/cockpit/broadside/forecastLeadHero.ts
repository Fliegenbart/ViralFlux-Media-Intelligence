interface ForecastLeadHeroInput {
  backtestLead: number | null;
  bestLag: number | null;
  hasShift: boolean;
}

interface ForecastLeadHero {
  leadDays: number | null;
  leadLabel: string | null;
  leadNote: string;
}

export function deriveForecastLeadHero({
  backtestLead,
  bestLag,
  hasShift,
}: ForecastLeadHeroInput): ForecastLeadHero {
  const leadDays =
    backtestLead !== null
      ? backtestLead
      : bestLag !== null && bestLag > 0
        ? bestLag
        : null;

  const leadLabel =
    backtestLead !== null
      ? '5–10'
      : leadDays !== null
        ? `${leadDays > 0 ? '+' : ''}${leadDays}`
        : null;

  const leadNote =
    backtestLead !== null
      ? `Peak-Wochen sind der relevante Pilotfall: dort zeigte der Backtest 5–10 Tage Vorlauf. Der Median über alle Wochen bleibt ${leadDays ?? '—'} Tage.${!hasShift ? ' Diese Woche gibt das Ranking trotzdem kein klares Shift-Signal — die Top-BL-Liste liegt eng beieinander.' : ''}`
      : leadDays !== null && leadDays > 0
        ? `Das Lead-Signal basiert auf der Notaufnahme-Spur (${leadDays} Tage vor der Meldewesen-Referenz).`
        : leadDays !== null && leadDays === 0
          ? 'Modell und Meldewesen laufen synchron — kein Vorlauf messbar.'
          : 'Lead-Time nicht berechenbar — Backtest-Pairs unvollständig oder Modell synchron zum Meldewesen.';

  return { leadDays, leadLabel, leadNote };
}
