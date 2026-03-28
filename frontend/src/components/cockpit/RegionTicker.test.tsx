import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import RegionTicker, { RegionTickerRegion } from './RegionTicker';

const regions: RegionTickerRegion[] = [
  {
    region_id: 'DE-NW',
    bundesland: 'NW',
    bundesland_name: 'Nordrhein-Westfalen',
    virus_typ: 'Influenza A',
    as_of_date: '2026-03-28',
    target_week_start: '2026-03-31',
    target_window_days: [3, 7],
    horizon_days: 5,
    event_probability_calibrated: 0.72,
    current_known_incidence: 10,
    change_pct: 12,
    trend: 'steigend',
    decision_rank: 1,
    decision_stage: 'activate',
    budget_amount: 42000,
  },
  {
    region_id: 'DE-BY',
    bundesland: 'BY',
    bundesland_name: 'Bayern',
    virus_typ: 'Influenza A',
    as_of_date: '2026-03-28',
    target_week_start: '2026-03-31',
    target_window_days: [3, 7],
    horizon_days: 5,
    event_probability_calibrated: 0.54,
    current_known_incidence: 9,
    change_pct: 4,
    trend: 'steigend',
    decision_rank: 2,
    decision_stage: 'prepare',
    budget_amount: 28000,
  },
  {
    region_id: 'DE-BE',
    bundesland: 'BE',
    bundesland_name: 'Berlin',
    virus_typ: 'Influenza A',
    as_of_date: '2026-03-28',
    target_week_start: '2026-03-31',
    target_window_days: [3, 7],
    horizon_days: 5,
    event_probability_calibrated: 0.31,
    current_known_incidence: 8,
    change_pct: -3,
    trend: 'fallend',
    decision_rank: 3,
    decision_stage: 'watch',
    budget_amount: null,
  },
];

describe('RegionTicker', () => {
  it('renders all passed regions', () => {
    render(
      <RegionTicker
        regions={regions}
        selectedRegion={null}
        onRegionSelect={jest.fn()}
      />,
    );

    expect(screen.getByText('Nordrhein-Westfalen')).toBeInTheDocument();
    expect(screen.getByText('Bayern')).toBeInTheDocument();
    expect(screen.getByText('Berlin')).toBeInTheDocument();
  });

  it('fires onRegionSelect with the correct id on row click', () => {
    const onRegionSelect = jest.fn();

    render(
      <RegionTicker
        regions={regions}
        selectedRegion={null}
        onRegionSelect={onRegionSelect}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Bayern Prepare/i }));

    expect(onRegionSelect).toHaveBeenCalledWith('DE-BY');
  });

  it('assigns the correct stage dot classes', () => {
    const { container } = render(
      <RegionTicker
        regions={regions}
        selectedRegion={null}
        onRegionSelect={jest.fn()}
      />,
    );

    expect(container.querySelector('.region-ticker__stage-dot--activate')).toBeTruthy();
    expect(container.querySelector('.region-ticker__stage-dot--prepare')).toBeTruthy();
    expect(container.querySelector('.region-ticker__stage-dot--watch')).toBeTruthy();
  });

  it('shows the correct trend arrows', () => {
    render(
      <RegionTicker
        regions={regions}
        selectedRegion={null}
        onRegionSelect={jest.fn()}
      />,
    );

    expect(screen.getByText('↑')).toBeInTheDocument();
    expect(screen.getByText('↗')).toBeInTheDocument();
    expect(screen.getByText('↘')).toBeInTheDocument();
  });
});
