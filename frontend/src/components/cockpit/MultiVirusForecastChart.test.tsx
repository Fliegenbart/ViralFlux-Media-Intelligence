import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import { MultiVirusForecastChart } from './MultiVirusForecastChart';

jest.mock('recharts', () => {
  const ReactLib = require('react');

  const passthrough = ({ children }: { children?: React.ReactNode }) => ReactLib.createElement(ReactLib.Fragment, null, children);
  const empty = () => null;

  return {
    ResponsiveContainer: passthrough,
    LineChart: passthrough,
    CartesianGrid: empty,
    Tooltip: empty,
    XAxis: empty,
    YAxis: empty,
    ReferenceArea: empty,
    ReferenceLine: ({ label }: { label?: { value?: string } | string }) => (
      <div>{typeof label === 'string' ? label : label?.value}</div>
    ),
    Line: empty,
  };
});

describe('MultiVirusForecastChart', () => {
  it('labels the normalization baseline as the last observed point instead of today', () => {
    render(
      <MultiVirusForecastChart
        selectedVirus="Influenza A"
        data={[
          {
            date: '2026-03-18',
            dateLabel: '18.03',
            actualSeries: { 'Influenza A': 84 },
            forecastSeries: { 'Influenza A': null },
          },
          {
            date: '2026-03-30',
            dateLabel: '30.03',
            actualSeries: { 'Influenza A': 100 },
            forecastSeries: { 'Influenza A': 100 },
          },
          {
            date: '2026-04-01',
            dateLabel: '01.04',
            actualSeries: { 'Influenza A': null },
            forecastSeries: { 'Influenza A': 108 },
          },
        ]}
      />,
    );

    expect(screen.getByText('Letzter Stand')).toBeInTheDocument();
    expect(screen.queryByText('Heute')).not.toBeInTheDocument();
  });
});
