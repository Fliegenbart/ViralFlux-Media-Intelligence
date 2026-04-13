import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

import { useVirusRadarHeroForecast } from './useVirusRadarHeroForecast';
import { mediaApi } from './api';

jest.mock('./api', () => ({
  mediaApi: {
    getRegionalHeroOverview: jest.fn(),
  },
}));

function buildPortfolio() {
  return {
    generated_at: '2026-04-08T08:00:00Z',
    reference_virus: 'Influenza A',
    summary: {
      trained_viruses: 4,
      go_viruses: 1,
      total_opportunities: 4,
      watchlist_opportunities: 4,
      priority_opportunities: 0,
      validated_opportunities: 0,
    },
    benchmark: [],
    virus_rollup: [
      { virus_typ: 'Influenza A', top_change_pct: 8, top_region_name: 'Berlin' },
      { virus_typ: 'Influenza B', top_change_pct: -6, top_region_name: 'Hamburg' },
      { virus_typ: 'SARS-CoV-2', top_change_pct: 21, top_region_name: 'Saarland' },
      { virus_typ: 'RSV A', top_change_pct: 45, top_region_name: 'Mecklenburg-Vorpommern' },
    ],
    hero_timeseries: [
      {
        virus_typ: 'Influenza A',
        points: [
          { date: '2026-03-18', actual_value: 88 },
          { date: '2026-03-25', actual_value: 100 },
          { date: '2026-04-01', forecast_value: 108 },
        ],
      },
      {
        virus_typ: 'Influenza B',
        points: [
          { date: '2026-03-18', actual_value: 104 },
          { date: '2026-03-25', actual_value: 100 },
          { date: '2026-04-01', forecast_value: 94 },
        ],
      },
      {
        virus_typ: 'SARS-CoV-2',
        points: [
          { date: '2026-03-18', actual_value: 90 },
          { date: '2026-03-25', actual_value: 100 },
          { date: '2026-04-01', forecast_value: 121 },
        ],
      },
      {
        virus_typ: 'RSV A',
        points: [
          { date: '2026-03-18', actual_value: 70 },
          { date: '2026-03-25', actual_value: 100 },
          { date: '2026-04-01', forecast_value: 145 },
        ],
      },
    ],
    region_rollup: [],
    top_opportunities: [],
  };
}

function Harness() {
  const { heroForecast, loading } = useVirusRadarHeroForecast('gelo', 0);

  return (
    <div>
      <div data-testid="hero-loading">{loading ? 'loading' : 'ready'}</div>
      <div data-testid="hero-headline">{heroForecast.headlineSecondary}</div>
      <div data-testid="hero-top-virus">{heroForecast.summaries[0]?.virus || '-'}</div>
    </div>
  );
}

describe('useVirusRadarHeroForecast', () => {
  const mockedMediaApi = mediaApi as jest.Mocked<typeof mediaApi>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('loads one shared 7-day portfolio and builds a four-virus hero outlook from it', async () => {
    mockedMediaApi.getRegionalHeroOverview.mockResolvedValue(buildPortfolio() as any);

    render(<Harness />);

    expect(screen.getByTestId('hero-loading')).toHaveTextContent('loading');

    await waitFor(() => expect(screen.getByTestId('hero-loading')).toHaveTextContent('ready'));

    expect(mockedMediaApi.getRegionalHeroOverview).toHaveBeenCalledTimes(1);
    expect(mockedMediaApi.getRegionalHeroOverview).toHaveBeenCalledWith('Influenza A', 7, 'gelo');
    expect(screen.getByTestId('hero-top-virus')).toHaveTextContent('RSV A');
    expect(screen.getByTestId('hero-headline')).toHaveTextContent('RSV A');
  });
});
