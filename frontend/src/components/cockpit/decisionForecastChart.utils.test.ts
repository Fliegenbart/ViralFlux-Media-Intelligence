import { buildDecisionForecastChartModel } from './decisionForecastChart.utils';

describe('buildDecisionForecastChartModel', () => {
  it('keeps historical points and builds a daily 7-day forecast bridge to the target date', () => {
    const model = buildDecisionForecastChartModel({
      horizonDays: 7,
      prediction: {
        bundesland: 'SN',
        bundesland_name: 'Sachsen',
        virus_typ: 'Influenza A',
        as_of_date: '2026-03-12',
        target_date: '2026-03-19',
        target_week_start: '2026-03-16',
        target_window_days: [7],
        horizon_days: 7,
        event_probability: 0.81,
        expected_target_incidence: 100,
        current_known_incidence: 86,
        prediction_interval: {
          lower: 95,
          upper: 108,
        },
        change_pct: 16.3,
        trend: 'up',
        last_data_date: '2026-03-12',
      },
      backtest: {
        bundesland: 'SN',
        bundesland_name: 'Sachsen',
        timeline: [
          {
            bundesland: 'SN',
            bundesland_name: 'Sachsen',
            as_of_date: '2026-03-10',
            target_date: '2026-03-17',
            horizon_days: 7,
            current_known_incidence: 80,
            expected_target_incidence: 90,
          },
          {
            bundesland: 'SN',
            bundesland_name: 'Sachsen',
            as_of_date: '2026-03-11',
            target_date: '2026-03-18',
            horizon_days: 7,
            current_known_incidence: 83,
            expected_target_incidence: 93,
          },
          {
            bundesland: 'SN',
            bundesland_name: 'Sachsen',
            as_of_date: '2026-03-12',
            target_date: '2026-03-19',
            horizon_days: 7,
            current_known_incidence: 86,
            expected_target_incidence: 96,
          },
        ],
      },
    });

    expect(model.rows.map((row) => row.date)).toEqual([
      '2026-03-10',
      '2026-03-11',
      '2026-03-12',
      '2026-03-13',
      '2026-03-14',
      '2026-03-15',
      '2026-03-16',
      '2026-03-17',
      '2026-03-18',
      '2026-03-19',
    ]);
    expect(model.rows.find((row) => row.date === '2026-03-10')?.actual).toBe(80);
    expect(model.rows.find((row) => row.date === '2026-03-12')).toMatchObject({
      actual: 86,
      forecast: 86,
      bandLower: 86,
      bandUpper: 86,
      inForecastZone: true,
    });
    expect(model.rows.find((row) => row.date === '2026-03-19')).toMatchObject({
      forecast: 100,
      bandLower: 95,
      bandUpper: 108,
      inForecastZone: true,
    });
    expect(model.rows.filter((row) => row.inForecastZone)).toHaveLength(8);
    expect(model.currentDate).toBe('2026-03-12');
    expect(model.targetDate).toBe('2026-03-19');
    expect(model.hasHistory).toBe(true);
    expect(model.hasForecast).toBe(true);
  });

  it('returns an honest empty model when there is no usable prediction and no history', () => {
    const model = buildDecisionForecastChartModel({
      horizonDays: 7,
      prediction: null,
      backtest: null,
    });

    expect(model.rows).toEqual([]);
    expect(model.hasHistory).toBe(false);
    expect(model.hasForecast).toBe(false);
    expect(model.currentDate).toBeNull();
    expect(model.targetDate).toBeNull();
  });
});
