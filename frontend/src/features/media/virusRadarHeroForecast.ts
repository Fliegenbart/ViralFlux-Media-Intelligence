import { RegionalPortfolioResponse } from '../../types/media';

export const VIRUS_RADAR_HERO_VIRUSES = [
  'Influenza A',
  'Influenza B',
  'SARS-CoV-2',
  'RSV A',
] as const;

export const VIRUS_RADAR_HERO_COLORS: Record<string, string> = {
  'Influenza A': '#e8523a',
  'Influenza B': '#1f7a66',
  'SARS-CoV-2': '#1457d2',
  'RSV A': '#7a3ff2',
};

export type VirusRadarHeroVirus = (typeof VIRUS_RADAR_HERO_VIRUSES)[number];

export interface VirusRadarHeroChartRow {
  date: string;
  dateLabel: string;
  isForecast: boolean;
  series: Record<string, number | null>;
}

export interface VirusRadarHeroSummary {
  virus: string;
  currentIndex: number;
  projectedIndex: number;
  deltaPct: number;
  direction: 'steigend' | 'fallend' | 'stabil';
}

export interface VirusRadarHeroForecastData {
  availableViruses: string[];
  chartData: VirusRadarHeroChartRow[];
  summaries: VirusRadarHeroSummary[];
  headlinePrimary: string;
  headlineSecondary: string;
  summary: string;
}

type ForecastPoint = {
  date: string;
  value: number;
};

function formatDayMonth(dateStr: string): string {
  const date = new Date(dateStr);
  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  return `${day}.${month}`;
}

function addDays(dateStr: string, days: number): string {
  const date = new Date(`${dateStr}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function normalizeDirection(deltaPct: number): 'steigend' | 'fallend' | 'stabil' {
  if (deltaPct >= 3) return 'steigend';
  if (deltaPct <= -3) return 'fallend';
  return 'stabil';
}

function buildProjectionSeries(today: string, deltaPct: number): ForecastPoint[] {
  return Array.from({ length: 8 }, (_, dayOffset) => {
    const progress = dayOffset / 7;
    return {
      date: addDays(today, dayOffset),
      value: Number((100 + (deltaPct * progress)).toFixed(2)),
    };
  });
}

function buildHeadlineSecondary(summaries: VirusRadarHeroSummary[]): string {
  if (!summaries.length) return 'Noch keine belastbare 7-Tage-Prognose.';

  const rising = summaries.filter((item) => item.direction === 'steigend');
  if (rising.length >= 2) return `${rising[0].virus} und ${rising[1].virus} ziehen aktuell am stärksten an.`;
  if (rising.length === 1) return `${rising[0].virus} zieht aktuell am stärksten an.`;
  if (summaries[0].direction === 'fallend') return `${summaries[0].virus} flacht aktuell eher ab.`;
  return `${summaries[0].virus} bleibt aktuell am stabilsten.`;
}

function buildSummary(summaries: VirusRadarHeroSummary[]): string {
  if (!summaries.length) {
    return 'Sobald frische Prognosekurven vorliegen, wird hier das gemeinsame Lagebild der nächsten sieben Tage sichtbar.';
  }

  const top = summaries[0];
  const second = summaries[1];
  const topPrefix = `${top.virus} liegt in der 7-Tage-Richtung bei ${top.deltaPct >= 0 ? '+' : ''}${top.deltaPct.toFixed(0)} %.`;
  if (!second) {
    return `${topPrefix} Alle Linien sind auf Heute = 100 normiert und zeigen die erwartete 7-Tage-Richtung je Virus.`;
  }
  return `${topPrefix} Dahinter folgt ${second.virus} mit ${second.deltaPct >= 0 ? '+' : ''}${second.deltaPct.toFixed(0)} %. Alle Linien sind auf Heute = 100 normiert und zeigen die erwartete 7-Tage-Richtung je Virus.`;
}

export function buildVirusRadarHeroForecastData(
  portfolio: RegionalPortfolioResponse | null | undefined,
  today = new Date().toISOString().slice(0, 10),
): VirusRadarHeroForecastData {
  const seriesByVirus = new Map<string, ForecastPoint[]>();
  const summaries: VirusRadarHeroSummary[] = [];
  const rollups = portfolio?.virus_rollup || [];

  VIRUS_RADAR_HERO_VIRUSES.forEach((virus) => {
    const rollup = rollups.find((item) => item.virus_typ === virus);
    const deltaPct = Number(rollup?.top_change_pct ?? Number.NaN);
    if (!Number.isFinite(deltaPct)) return;

    const normalizedPoints = buildProjectionSeries(today, deltaPct);
    seriesByVirus.set(virus, normalizedPoints);
    const projectedIndex = Number((100 + deltaPct).toFixed(1));

    summaries.push({
      virus,
      currentIndex: 100,
      projectedIndex,
      deltaPct,
      direction: normalizeDirection(deltaPct),
    });
  });

  const allDates = Array.from(
    new Set(
      Array.from(seriesByVirus.values()).flatMap((points) => points.map((point) => point.date)),
    ),
  ).sort((left, right) => left.localeCompare(right));

  const chartData: VirusRadarHeroChartRow[] = allDates.map((date) => {
    const series = Object.fromEntries(
      VIRUS_RADAR_HERO_VIRUSES.map((virus) => {
        const point = seriesByVirus.get(virus)?.find((entry) => entry.date === date);
        return [virus, point?.value ?? null];
      }),
    );

    return {
      date,
      dateLabel: formatDayMonth(date),
      isForecast: date > today,
      series,
    };
  });

  summaries.sort((left, right) => right.deltaPct - left.deltaPct);

  return {
    availableViruses: VIRUS_RADAR_HERO_VIRUSES.filter((virus) => seriesByVirus.has(virus)),
    chartData,
    summaries,
    headlinePrimary: 'Das Lagebild der nächsten 7 Tage.',
    headlineSecondary: buildHeadlineSecondary(summaries),
    summary: buildSummary(summaries),
  };
}
