import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

import { useVirusRadarHeroForecast } from './useVirusRadarHeroForecast';
import { mediaApi } from './api';

jest.mock('./api', () => ({
  mediaApi: {
    getLatestForecast: jest.fn(),
  },
}));

function buildForecast(virusTyp: string, valueToday: number, valueFuture: number) {
  return {
    virus_typ: virusTyp,
    forecast: [
      { date: '2026-04-08T00:00:00', predicted_value: valueToday },
      { date: '2026-04-15T00:00:00', predicted_value: valueFuture },
    ],
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

  it('loads all four virus backtests and builds a shared hero outlook', async () => {
    mockedMediaApi.getLatestForecast.mockImplementation(async (virus: string) => {
      if (virus === 'RSV A') return buildForecast(virus, 100, 145) as any;
      if (virus === 'SARS-CoV-2') return buildForecast(virus, 100, 121) as any;
      if (virus === 'Influenza A') return buildForecast(virus, 100, 108) as any;
      return buildForecast(virus, 100, 94) as any;
    });

    render(<Harness />);

    expect(screen.getByTestId('hero-loading')).toHaveTextContent('loading');

    await waitFor(() => expect(screen.getByTestId('hero-loading')).toHaveTextContent('ready'));

    expect(mockedMediaApi.getLatestForecast).toHaveBeenCalledTimes(4);
    expect(screen.getByTestId('hero-top-virus')).toHaveTextContent('RSV A');
    expect(screen.getByTestId('hero-headline')).toHaveTextContent('RSV A');
  });
});
