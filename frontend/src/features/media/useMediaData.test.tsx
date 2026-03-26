import '@testing-library/jest-dom';
import React, { act } from 'react';
import { render, screen, waitFor } from '@testing-library/react';

import { useNowPageData } from './useMediaData';
import { mediaApi } from './api';

jest.mock('./api', () => ({
  mediaApi: {
    getDecision: jest.fn(),
    getEvidence: jest.fn(),
    getBacktestRun: jest.fn(),
    getRegionalBacktest: jest.fn(),
    getRegionalForecast: jest.fn(),
    getRegionalAllocation: jest.fn(),
    getRegionalCampaignRecommendations: jest.fn(),
    getWaveRadar: jest.fn(),
  },
}));

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
};

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function Harness() {
  const { loading, view } = useNowPageData('Influenza A', 'gelo', 7, 120000, 0);

  return (
    <div>
      <div data-testid="loading-state">{loading ? 'loading' : 'ready'}</div>
      <div data-testid="has-data">{view.hasData ? 'yes' : 'no'}</div>
      <div data-testid="summary">{view.summary}</div>
    </div>
  );
}

describe('useNowPageData', () => {
  const mockedMediaApi = mediaApi as jest.Mocked<typeof mediaApi>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('loads core data first and background regional data afterwards', async () => {
    const callOrder: string[] = [];
    const decisionDeferred = createDeferred<any>();
    const evidenceDeferred = createDeferred<any>();
    const backtestDeferred = createDeferred<any>();
    const forecastDeferred = createDeferred<any>();
    const allocationDeferred = createDeferred<any>();
    const recommendationDeferred = createDeferred<any>();
    const regionalBacktestDeferred = createDeferred<any>();
    const waveRadarDeferred = createDeferred<any>();

    mockedMediaApi.getDecision.mockImplementation(() => {
      callOrder.push('decision');
      return decisionDeferred.promise;
    });
    mockedMediaApi.getEvidence.mockImplementation(() => {
      callOrder.push('evidence');
      return evidenceDeferred.promise;
    });
    mockedMediaApi.getBacktestRun.mockImplementation(() => {
      callOrder.push('backtest');
      return backtestDeferred.promise;
    });
    mockedMediaApi.getRegionalForecast.mockImplementation(() => {
      callOrder.push('forecast');
      return forecastDeferred.promise;
    });
    mockedMediaApi.getRegionalBacktest.mockImplementation(() => {
      callOrder.push('regionalBacktest');
      return regionalBacktestDeferred.promise;
    });
    mockedMediaApi.getRegionalAllocation.mockImplementation(() => {
      callOrder.push('allocation');
      return allocationDeferred.promise;
    });
    mockedMediaApi.getRegionalCampaignRecommendations.mockImplementation(() => {
      callOrder.push('recommendation');
      return recommendationDeferred.promise;
    });
    mockedMediaApi.getWaveRadar.mockImplementation(() => {
      callOrder.push('waveRadar');
      return waveRadarDeferred.promise;
    });

    render(<Harness />);

    expect(callOrder).toEqual(['decision', 'evidence']);
    expect(screen.getByTestId('loading-state')).toHaveTextContent('loading');
    expect(screen.getByTestId('has-data')).toHaveTextContent('no');

    await act(async () => {
      decisionDeferred.resolve({
        generated_at: '2026-03-21T09:00:00Z',
        weekly_decision: {
          decision_state: 'WATCH',
          action_stage: 'prepare',
          recommended_action: 'Berlin priorisieren.',
          why_now: ['Berlin bleibt im Blick.'],
          risk_flags: [],
          top_regions: [{ code: 'BE', name: 'Berlin', signal_score: 63.4, trend: 'rising' }],
        },
        top_recommendations: [],
        wave_run_id: 'wave-1',
      });
      await Promise.resolve();
    });

    expect(callOrder).toEqual(['decision', 'evidence']);

    await act(async () => {
      evidenceDeferred.resolve({
        generated_at: '2026-03-21T09:00:00Z',
        source_status: {
          live_count: 1,
          total: 1,
          items: [],
        },
        forecast_monitoring: {
          monitoring_status: 'watch',
          freshness_status: 'fresh',
        },
      });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByTestId('loading-state')).toHaveTextContent('ready');
    });
    expect(screen.getByTestId('has-data')).toHaveTextContent('yes');
    expect(callOrder).toEqual(['decision', 'evidence', 'backtest']);

    await act(async () => {
      backtestDeferred.resolve({
        run_id: 'wave-1',
        chart_data: [],
      });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(callOrder).toEqual(['decision', 'evidence', 'backtest', 'forecast', 'allocation', 'recommendation', 'waveRadar']);
    });

    await act(async () => {
      forecastDeferred.resolve({
        generated_at: '2026-03-21T09:00:00Z',
        predictions: [],
      });
      await Promise.resolve();
      allocationDeferred.resolve({
        generated_at: '2026-03-21T09:00:00Z',
        recommendations: [],
      });
      await Promise.resolve();
      recommendationDeferred.resolve({
        generated_at: '2026-03-21T09:00:00Z',
        recommendations: [],
      });
      waveRadarDeferred.resolve({
        generated_at: '2026-03-21T09:00:00Z',
        waves: [],
      });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(mockedMediaApi.getRegionalCampaignRecommendations).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(callOrder).toEqual(['decision', 'evidence', 'backtest', 'forecast', 'allocation', 'recommendation', 'waveRadar', 'regionalBacktest']);
    });

    await act(async () => {
      regionalBacktestDeferred.resolve({
        bundesland: 'BE',
        bundesland_name: 'Berlin',
        timeline: [],
      });
      await Promise.resolve();
    });
  });
});
