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
    region_rollup: [],
    top_opportunities: [],
  };
}

describe('buildVirusRadarHeroForecastData', () => {
  it('builds a shared 7-day comparison from the portfolio rollup and ranks the strongest outlook first', () => {
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
    expect(result.chartData).toHaveLength(8);
    expect(result.chartData[0].date).toBe('2026-04-08');
    expect(result.chartData[0].series['Influenza A']).toBe(100);
    expect(result.chartData[0].series['Influenza B']).toBe(100);
    expect(result.chartData[0].series['SARS-CoV-2']).toBe(100);
    expect(result.chartData[0].series['RSV A']).toBe(100);
    expect(result.chartData[7].date).toBe('2026-04-15');
    expect(result.chartData[7].series['RSV A']).toBe(145);
    expect(result.summaries.map((item) => item.virus)).toEqual([
      'RSV A',
      'SARS-CoV-2',
      'Influenza A',
      'Influenza B',
    ]);
    expect(result.summaries[0].deltaPct).toBeCloseTo(45);
    expect(result.summaries[3].direction).toBe('fallend');
    expect(result.headlineSecondary).toContain('RSV A');
  });
});
