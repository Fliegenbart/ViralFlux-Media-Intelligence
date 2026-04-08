import { BacktestResponse } from '../../types/media';
import {
  VIRUS_RADAR_HERO_VIRUSES,
  buildVirusRadarHeroForecastData,
} from './virusRadarHeroForecast';

function buildPlanningCurve(values: Array<{ date: string; value: number }>): BacktestResponse {
  return {
    planning_curve: {
      lead_days: 7,
      correlation: 0.72,
      curve: values.map((entry) => ({
        date: entry.date,
        target_date: entry.date,
        planning_qty: entry.value,
      })),
    },
  };
}

describe('buildVirusRadarHeroForecastData', () => {
  it('normalizes all virus curves to a shared today=100 scale and ranks the strongest 7-day outlook first', () => {
    const result = buildVirusRadarHeroForecastData(
      {
        'Influenza A': buildPlanningCurve([
          { date: '2026-04-01', value: 80 },
          { date: '2026-04-08', value: 100 },
          { date: '2026-04-15', value: 108 },
        ]),
        'Influenza B': buildPlanningCurve([
          { date: '2026-04-01', value: 92 },
          { date: '2026-04-08', value: 100 },
          { date: '2026-04-15', value: 94 },
        ]),
        'SARS-CoV-2': buildPlanningCurve([
          { date: '2026-04-01', value: 70 },
          { date: '2026-04-08', value: 100 },
          { date: '2026-04-15', value: 121 },
        ]),
        'RSV A': buildPlanningCurve([
          { date: '2026-04-01', value: 64 },
          { date: '2026-04-08', value: 100 },
          { date: '2026-04-15', value: 145 },
        ]),
      },
      '2026-04-08',
    );

    expect(result.availableViruses).toEqual(VIRUS_RADAR_HERO_VIRUSES);
    expect(result.chartData).toHaveLength(3);
    expect(result.chartData[1].date).toBe('2026-04-08');
    expect(result.chartData[1].series['Influenza A']).toBe(100);
    expect(result.chartData[1].series['Influenza B']).toBe(100);
    expect(result.chartData[1].series['SARS-CoV-2']).toBe(100);
    expect(result.chartData[1].series['RSV A']).toBe(100);
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
