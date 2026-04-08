import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

import { useVirusRadarHeroForecast } from './useVirusRadarHeroForecast';
import { mediaApi } from './api';

jest.mock('./api', () => ({
  mediaApi: {
    getDecision: jest.fn(),
    getBacktestRun: jest.fn(),
  },
}));

function buildBacktest(valueToday: number, valueFuture: number) {
  return {
    planning_curve: {
      curve: [
        { date: '2026-04-01', planning_qty: valueToday * 0.8 },
        { date: '2026-04-08', planning_qty: valueToday },
        { date: '2026-04-15', planning_qty: valueFuture },
      ],
    },
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
    mockedMediaApi.getDecision.mockImplementation(async (virus: string) => ({
      wave_run_id: `${virus}-run`,
    } as any));
    mockedMediaApi.getBacktestRun.mockImplementation(async (runId: string) => {
      if (runId.startsWith('RSV A')) return buildBacktest(100, 145) as any;
      if (runId.startsWith('SARS-CoV-2')) return buildBacktest(100, 121) as any;
      if (runId.startsWith('Influenza A')) return buildBacktest(100, 108) as any;
      return buildBacktest(100, 94) as any;
    });

    render(<Harness />);

    expect(screen.getByTestId('hero-loading')).toHaveTextContent('loading');

    await waitFor(() => expect(screen.getByTestId('hero-loading')).toHaveTextContent('ready'));

    expect(mockedMediaApi.getDecision).toHaveBeenCalledTimes(4);
    expect(mockedMediaApi.getBacktestRun).toHaveBeenCalledTimes(4);
    expect(screen.getByTestId('hero-top-virus')).toHaveTextContent('RSV A');
    expect(screen.getByTestId('hero-headline')).toHaveTextContent('RSV A');
  });
});
