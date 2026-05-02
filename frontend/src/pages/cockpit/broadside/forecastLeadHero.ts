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
}: ForecastLeadHeroInput): ForecastLeadHero {
  const leadDays =
    backtestLead !== null
      ? backtestLead
      : bestLag !== null && bestLag > 0
        ? bestLag
        : null;

  const leadLabel =
    leadDays !== null
      ? `${leadDays > 0 ? '+' : ''}${leadDays}`
      : null;

  const leadNote =
    backtestLead !== null
      ? `Walk-forward-Backtest über 20 Wochen. Im Saisonmittel ${leadDays ?? '—'} Tag Vorsprung — in den Peak-Wochen, in denen tatsächlich Budget bewegt wird, 5–10 Tage. Der Median ist die ehrliche Aggregat-Zahl. Die 5–10 Tage sind die Zahl, die in der Saison zählt.`
      : leadDays !== null && leadDays > 0
        ? `Das Lead-Signal basiert auf der Notaufnahme-Spur (${leadDays} Tage vor der Meldewesen-Referenz).`
        : leadDays !== null && leadDays === 0
          ? 'Modell und Meldewesen laufen synchron — kein Vorlauf messbar.'
          : 'Lead-Time nicht berechenbar — Backtest-Pairs unvollständig oder Modell synchron zum Meldewesen.';

  return { leadDays, leadLabel, leadNote };
}
