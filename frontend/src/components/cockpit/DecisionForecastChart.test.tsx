import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import { DecisionForecastChart } from './DecisionForecastChart';

jest.mock('recharts', () => {
  const ReactLib = require('react');

  const passthrough = ({ children }: { children?: React.ReactNode }) => ReactLib.createElement(ReactLib.Fragment, null, children);
  const svgPassthrough = ({ children }: { children?: React.ReactNode }) => ReactLib.createElement('svg', null, children);
  const empty = () => null;

  return {
    ResponsiveContainer: passthrough,
    ComposedChart: svgPassthrough,
    CartesianGrid: empty,
    ReferenceArea: empty,
    ReferenceLine: empty,
    Tooltip: empty,
    XAxis: empty,
    YAxis: empty,
    Area: empty,
    Line: empty,
  };
});

describe('DecisionForecastChart', () => {
  it('renders a calm chart shell with legend and date anchors', () => {
    render(
      <DecisionForecastChart
        horizonDays={7}
        prediction={{
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
        }}
        backtest={{
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
        }}
      />,
    );

    expect(screen.getByLabelText('Entscheidungsgraph')).toBeInTheDocument();
    expect(screen.getByText('Historisch')).toBeInTheDocument();
    expect(screen.getByText('Modellierte 7-Tage-Fortfuehrung')).toBeInTheDocument();
    expect(screen.getByText('Bandbreite')).toBeInTheDocument();
    expect(screen.getByText('Stand 12.03.2026')).toBeInTheDocument();
    expect(screen.getByText('Ziel 19.03.2026')).toBeInTheDocument();
    expect(screen.getByText('Vergangenheit')).toBeInTheDocument();
    expect(screen.getByText('Naechste 7 Tage')).toBeInTheDocument();
  });

  it('shows a restrained empty state when there is no usable chart data', () => {
    render(
      <DecisionForecastChart
        horizonDays={7}
        prediction={null}
        backtest={null}
      />,
    );

    expect(screen.getByText('Noch kein belastbarer Verlauf fuer diese Entscheidung verfuegbar.')).toBeInTheDocument();
  });
});
