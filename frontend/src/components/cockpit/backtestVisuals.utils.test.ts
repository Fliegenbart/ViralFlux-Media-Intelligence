import {
  buildFocusRegionChartRows,
  buildUncertaintyText,
  buildWaveSpreadRows,
} from './backtestVisuals.utils';

jest.mock('./cockpitUtils', () => ({
  formatDateShort: (value?: string | null) => {
    if (!value) return '-';
    const iso = String(value).slice(0, 10);
    const [year, month, day] = iso.split('-');
    return `${day}.${month}.${year}`;
  },
  formatPercent: (value: number) => `${Math.round(value)}%`,
}));

describe('backtestVisuals.utils', () => {
  it('merges backtest history and forecast points into one ordered focus-region chart series', () => {
    const rows = buildFocusRegionChartRows(
      {
        as_of_date: '2026-03-17',
        last_data_date: '2026-03-17',
        target_date: '2026-03-24',
        current_known_incidence: 95,
        expected_target_incidence: 140,
        prediction_interval: {
          lower: 120,
          upper: 165,
        },
      } as any,
      {
        timeline: [
          {
            as_of_date: '2026-03-03',
            target_date: '2026-03-10',
            current_known_incidence: 70,
            expected_target_incidence: 84,
          },
          {
            as_of_date: '2026-03-10',
            target_date: '2026-03-17',
            current_known_incidence: 82,
            expected_target_incidence: 95,
          },
        ],
      } as any,
    );

    expect(rows).toEqual([
      expect.objectContaining({
        date: '2026-03-02',
        actual: 70,
      }),
      expect.objectContaining({
        date: '2026-03-09',
        actual: 82,
        validated: 84,
      }),
      expect.objectContaining({
        date: '2026-03-16',
        actual: 95,
        validated: 95,
        forecast: 95,
      }),
      expect.objectContaining({
        date: '2026-03-23',
        forecast: 140,
        bandBase: 120,
        bandRange: 45,
      }),
    ]);
  });

  it('describes uncertainty differently for narrow and wide forecast bands', () => {
    expect(buildUncertaintyText({
      expected_target_incidence: 120,
      prediction_interval: {
        lower: 110,
        upper: 130,
      },
      quality_gate: {
        overall_passed: true,
      },
    } as any)).toBe('Die Richtung ist belastbar, die genaue Höhe bleibt ein Forecast.');

    expect(buildUncertaintyText({
      expected_target_incidence: 120,
      prediction_interval: {
        lower: 60,
        upper: 190,
      },
      quality_gate: {
        overall_passed: false,
      },
    } as any)).toBe('Die Richtung ist sichtbar, die genaue Höhe bleibt noch unsicher.');
  });

  it('turns historical spread ordering into compact rows with day offsets', () => {
    const rows = buildWaveSpreadRows({
      summary: {
        first_onset: {
          date: '2025-11-10',
        },
      },
      regions: [
        {
          bundesland: 'Berlin',
          wave_start: '2025-11-10',
          wave_rank: 1,
        },
        {
          bundesland: 'Brandenburg',
          wave_start: '2025-11-17',
          wave_rank: 2,
        },
      ],
    } as any);

    expect(rows).toEqual([
      expect.objectContaining({
        rank: 1,
        bundesland: 'Berlin',
        offsetDays: 0,
      }),
      expect.objectContaining({
        rank: 2,
        bundesland: 'Brandenburg',
        offsetDays: 7,
      }),
    ]);
  });
});
