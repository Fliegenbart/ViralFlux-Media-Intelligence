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
  actualSeries: Record<string, number | null>;
  forecastSeries: Record<string, number | null>;
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

type RealSeriesPoint = {
  date: string;
  actualValue?: number | null;
  forecastValue?: number | null;
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

function normalizeSeriesValue(value: number, baseline: number): number {
  return Number(((value / baseline) * 100).toFixed(2));
}

function buildChartFromHeroTimeseries(
  portfolio: RegionalPortfolioResponse,
): {
  chartData: VirusRadarHeroChartRow[];
  summaries: VirusRadarHeroSummary[];
  availableViruses: string[];
} | null {
  const heroSeries = portfolio.hero_timeseries || [];
  if (!heroSeries.length) return null;

  const actualMapByVirus = new Map<string, Map<string, number>>();
  const forecastMapByVirus = new Map<string, Map<string, number>>();
  const summaries: VirusRadarHeroSummary[] = [];
  const allDates = new Set<string>();

  heroSeries.forEach((series) => {
    const virus = series.virus_typ;
    if (!VIRUS_RADAR_HERO_VIRUSES.includes(virus as VirusRadarHeroVirus)) return;

    const normalizedPoints: RealSeriesPoint[] = (series.points || [])
      .filter((point) => point?.date)
      .map((point) => ({
        date: point.date,
        actualValue: Number.isFinite(point.actual_value) ? Number(point.actual_value) : null,
        forecastValue: Number.isFinite(point.forecast_value) ? Number(point.forecast_value) : null,
      }))
      .sort((left, right) => left.date.localeCompare(right.date));

    const actualPoints = normalizedPoints.filter((point) => Number.isFinite(point.actualValue));
    if (!actualPoints.length) return;

    const latestActual = actualPoints[actualPoints.length - 1];
    const baseline = Number(latestActual.actualValue);
    if (!Number.isFinite(baseline) || baseline <= 0) return;

    const actualSeries = new Map<string, number>();
    actualPoints.forEach((point) => {
      actualSeries.set(point.date, normalizeSeriesValue(Number(point.actualValue), baseline));
      allDates.add(point.date);
    });
    actualMapByVirus.set(virus, actualSeries);

    const forecastPoint = normalizedPoints.find((point) => Number.isFinite(point.forecastValue));
    if (forecastPoint && Number.isFinite(forecastPoint.forecastValue)) {
      const forecastSeries = new Map<string, number>();
      forecastSeries.set(latestActual.date, 100);
      forecastSeries.set(
        forecastPoint.date,
        normalizeSeriesValue(Number(forecastPoint.forecastValue), baseline),
      );
      allDates.add(forecastPoint.date);
      forecastMapByVirus.set(virus, forecastSeries);

      const forecastValue = Number(forecastPoint.forecastValue);
      const deltaPct = Number((((forecastValue - baseline) / baseline) * 100).toFixed(1));
      summaries.push({
        virus,
        currentIndex: 100,
        projectedIndex: normalizeSeriesValue(forecastValue, baseline),
        deltaPct,
        direction: normalizeDirection(deltaPct),
      });
      return;
    }

    summaries.push({
      virus,
      currentIndex: 100,
      projectedIndex: 100,
      deltaPct: 0,
      direction: 'stabil',
    });
  });

  const orderedDates = Array.from(allDates).sort((left, right) => left.localeCompare(right));
  if (!orderedDates.length || !summaries.length) return null;

  const chartData: VirusRadarHeroChartRow[] = orderedDates.map((date) => ({
    date,
    dateLabel: formatDayMonth(date),
    actualSeries: Object.fromEntries(
      VIRUS_RADAR_HERO_VIRUSES.map((virus) => [virus, actualMapByVirus.get(virus)?.get(date) ?? null]),
    ),
    forecastSeries: Object.fromEntries(
      VIRUS_RADAR_HERO_VIRUSES.map((virus) => [virus, forecastMapByVirus.get(virus)?.get(date) ?? null]),
    ),
  }));

  summaries.sort((left, right) => right.deltaPct - left.deltaPct);

  return {
    chartData,
    summaries,
    availableViruses: VIRUS_RADAR_HERO_VIRUSES.filter((virus) => actualMapByVirus.has(virus)),
  };
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
  const realTimeseriesResult = portfolio ? buildChartFromHeroTimeseries(portfolio) : null;
  if (realTimeseriesResult) {
    return {
      availableViruses: realTimeseriesResult.availableViruses,
      chartData: realTimeseriesResult.chartData,
      summaries: realTimeseriesResult.summaries,
      headlinePrimary: 'Die letzten Wochen und die nächsten 7 Tage.',
      headlineSecondary: buildHeadlineSecondary(realTimeseriesResult.summaries),
      summary: buildSummary(realTimeseriesResult.summaries),
    };
  }

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
    const actualSeries = Object.fromEntries(
      VIRUS_RADAR_HERO_VIRUSES.map((virus) => [
        virus,
        date === today ? 100 : null,
      ]),
    );
    const forecastSeries = Object.fromEntries(
      VIRUS_RADAR_HERO_VIRUSES.map((virus) => {
        const point = seriesByVirus.get(virus)?.find((entry) => entry.date === date);
        return [virus, point?.value ?? null];
      }),
    );

    return {
      date,
      dateLabel: formatDayMonth(date),
      actualSeries,
      forecastSeries,
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
