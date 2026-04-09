import { RegionalPortfolioResponse } from '../../types/media';
import {
  VIRUS_RADAR_HERO_VIRUSES,
  buildVirusRadarHeroForecastData,
} from './virusRadarHeroForecast';

function buildPortfolioRollup(
  values: Array<{ virus_typ: string; top_change_pct: number; top_region_name?: string }>,
): RegionalPortfolioResponse {
  return {
    generated_at: '2026-04-08T08:00:00Z',
    reference_virus: 'Influenza A',
    summary: {
      trained_viruses: values.length,
      go_viruses: 1,
      total_opportunities: values.length,
      watchlist_opportunities: values.length,
      priority_opportunities: 0,
      validated_opportunities: 0,
    },
    benchmark: [],
    virus_rollup: values.map((entry, index) => ({
      virus_typ: entry.virus_typ,
      rank: index + 1,
      top_region_name: entry.top_region_name || entry.virus_typ,
      top_change_pct: entry.top_change_pct,
    })),
    hero_timeseries: values.map((entry, index) => ({
      virus_typ: entry.virus_typ,
      run_id: `run-${index + 1}`,
      points: [
        { date: '2026-03-18', actual_value: 82 + (index * 4) },
        { date: '2026-03-25', actual_value: 100 },
        { date: '2026-04-01', forecast_value: 100 * (1 + entry.top_change_pct / 100) },
      ],
    })),
    region_rollup: [],
    top_opportunities: [],
  };
}

describe('buildVirusRadarHeroForecastData', () => {
  it('builds a shared history-plus-forecast comparison from hero timeseries and ranks the strongest outlook first', () => {
    const result = buildVirusRadarHeroForecastData(
      buildPortfolioRollup([
        { virus_typ: 'Influenza A', top_change_pct: 8, top_region_name: 'Berlin' },
        { virus_typ: 'Influenza B', top_change_pct: -6, top_region_name: 'Hamburg' },
        { virus_typ: 'SARS-CoV-2', top_change_pct: 21, top_region_name: 'Saarland' },
        { virus_typ: 'RSV A', top_change_pct: 45, top_region_name: 'Mecklenburg-Vorpommern' },
      ]),
      '2026-04-08',
    );

    expect(result.availableViruses).toEqual(VIRUS_RADAR_HERO_VIRUSES);
    expect(result.chartData).toHaveLength(3);
    expect(result.chartData[0].date).toBe('2026-03-18');
    expect(result.chartData[1].actualSeries['Influenza A']).toBe(100);
    expect(result.chartData[1].forecastSeries['Influenza A']).toBe(100);
    expect(result.chartData[2].date).toBe('2026-04-01');
    expect(result.chartData[2].forecastSeries['RSV A']).toBeCloseTo(145, 0);
    expect(result.summaries.map((item) => item.virus)).toEqual([
      'RSV A',
      'SARS-CoV-2',
      'Influenza A',
      'Influenza B',
    ]);
    expect(result.summaries[0].deltaPct).toBeCloseTo(45);
    expect(result.summaries[3].direction).toBe('fallend');
    expect(result.headlineSecondary).toContain('RSV A');
    expect(result.headlinePrimary).toContain('letzten Wochen');
  });
});
