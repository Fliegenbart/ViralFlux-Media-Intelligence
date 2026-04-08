import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import { ForecastChartTooltip } from './ForecastChartTooltip';

describe('ForecastChartTooltip', () => {
  it('renders a high-contrast tooltip with clear label-value rows', () => {
    render(
      <ForecastChartTooltip
        active
        label="Schleswig-Holstein · 23.02"
        payload={[
          {
            name: 'historicalLine',
            value: 30.4,
          },
          {
            name: 'forecastLine',
            value: 42.1,
          },
        ]}
      />,
    );

    expect(screen.getByText('Schleswig-Holstein · 23.02')).toBeInTheDocument();
    expect(screen.getByText('Ist-Inzidenz')).toBeInTheDocument();
    expect(screen.getByText('30.4')).toBeInTheDocument();
    expect(screen.getByText('Prognose')).toBeInTheDocument();
    expect(screen.getByText('42.1')).toBeInTheDocument();
  });
});
