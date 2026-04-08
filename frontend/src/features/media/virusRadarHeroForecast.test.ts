import { LatestForecastResponse } from '../../types/media';
import {
  VIRUS_RADAR_HERO_VIRUSES,
  buildVirusRadarHeroForecastData,
} from './virusRadarHeroForecast';

function buildForecast(values: Array<{ date: string; value: number }>, virus: string): LatestForecastResponse {
  return {
    virus_typ: virus,
    forecast: values.map((entry) => ({
      date: entry.date,
      predicted_value: entry.value,
    })),
  };
}

describe('buildVirusRadarHeroForecastData', () => {
  it('normalizes all virus forecasts to a shared today=100 scale and ranks the strongest 7-day outlook first', () => {
    const result = buildVirusRadarHeroForecastData(
      {
        'Influenza A': buildForecast([
          { date: '2026-04-08', value: 100 },
          { date: '2026-04-09', value: 102 },
          { date: '2026-04-15', value: 108 },
        ], 'Influenza A'),
        'Influenza B': buildForecast([
          { date: '2026-04-08', value: 100 },
          { date: '2026-04-09', value: 98 },
          { date: '2026-04-15', value: 94 },
        ], 'Influenza B'),
        'SARS-CoV-2': buildForecast([
          { date: '2026-04-08', value: 100 },
          { date: '2026-04-10', value: 110 },
          { date: '2026-04-15', value: 121 },
        ], 'SARS-CoV-2'),
        'RSV A': buildForecast([
          { date: '2026-04-08', value: 100 },
          { date: '2026-04-12', value: 126 },
          { date: '2026-04-15', value: 145 },
        ], 'RSV A'),
      },
      '2026-04-08',
    );

    expect(result.availableViruses).toEqual(VIRUS_RADAR_HERO_VIRUSES);
    expect(result.chartData).toHaveLength(5);
    expect(result.chartData[0].date).toBe('2026-04-08');
    expect(result.chartData[0].series['Influenza A']).toBe(100);
    expect(result.chartData[0].series['Influenza B']).toBe(100);
    expect(result.chartData[0].series['SARS-CoV-2']).toBe(100);
    expect(result.chartData[0].series['RSV A']).toBe(100);
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
