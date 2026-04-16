import '@testing-library/jest-dom';
import React, { act } from 'react';
import { render, screen, waitFor } from '@testing-library/react';

jest.mock('../../components/cockpit/cockpitUtils', () => ({
  businessValidationLabel: (value: unknown) => String(value || 'Im Aufbau'),
  evidenceTierLabel: (value: unknown) => String(value || 'Prüfen'),
  formatDateTime: (value: unknown) => String(value || '-'),
  formatCurrency: (value: unknown) => `${Number(value || 0).toFixed(0)} EUR`,
  formatPercent: (value: unknown, digits = 0) => `${Number(value || 0).toFixed(digits)}%`,
  truthFreshnessLabel: (value: unknown) => String(value || 'Beobachten'),
  truthLayerLabel: (value: { trust_readiness?: string } | null | undefined) => (
    value?.trust_readiness === 'im_aufbau' ? 'Im Aufbau' : String(value?.trust_readiness || 'Belastbar')
  ),
  workflowLabel: (value: unknown) => String(value || 'Prüfen'),
}));

import {
  buildNowPageViewModel,
  buildWorkspaceStatus,
  useNowPageData,
  useRegionsPageData,
  useTimegraphPageData,
} from './useMediaData';
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
    getRegions: jest.fn(),
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

function PreferredFocusHarness() {
  const { loading } = useNowPageData('Influenza A', 'gelo', 7, 120000, 0, undefined, 'BY');

  return <div data-testid="preferred-focus-loading">{loading ? 'loading' : 'ready'}</div>;
}

function TimegraphHarness() {
  const {
    loading,
    backtestLoading,
    selectedRegion,
    setSelectedRegion,
    regionOptions,
    selectedPrediction,
    regionalBacktest,
  } = useTimegraphPageData('Influenza A', 'gelo', 0);

  return (
    <div>
      <div data-testid="timegraph-loading">{loading ? 'loading' : 'ready'}</div>
      <div data-testid="timegraph-backtest-loading">{backtestLoading ? 'loading' : 'ready'}</div>
      <div data-testid="timegraph-region">{selectedRegion || '-'}</div>
      <div data-testid="timegraph-region-options">{regionOptions.map((item) => item.code).join(',') || '-'}</div>
      <div data-testid="timegraph-prediction">{selectedPrediction?.bundesland_name || '-'}</div>
      <div data-testid="timegraph-backtest">{regionalBacktest?.bundesland_name || '-'}</div>
      <button type="button" onClick={() => setSelectedRegion('BY')}>Region BY</button>
    </div>
  );
}

function RegionsHarness({ dataVersion }: { dataVersion: number }) {
  const { regionsLoading, regionsView } = useRegionsPageData('Influenza A', 'gelo', dataVersion);

  return (
    <div>
      <div data-testid="regions-loading">{regionsLoading ? 'loading' : 'ready'}</div>
      <div data-testid="regions-top">{regionsView?.map.top_regions[0]?.code || '-'}</div>
    </div>
  );
}

function buildDecision(overrides: Record<string, unknown> = {}) {
  const topRegions = (overrides.top_regions as Array<Record<string, unknown>> | undefined) || [
    { code: 'BE', name: 'Berlin', signal_score: 72.4, trend: 'rising' },
    { code: 'BY', name: 'Bayern', signal_score: 58.1, trend: 'rising' },
    { code: 'SN', name: 'Sachsen', signal_score: 46.2, trend: 'flat' },
  ];

  return {
    generated_at: '2026-03-21T09:00:00Z',
    weekly_decision: {
      decision_state: 'GO',
      action_stage: 'activate',
      recommended_action: 'Berlin priorisieren.',
      why_now: ['Berlin zeigt die stärkste Dynamik.'],
      risk_flags: [],
      top_regions: topRegions,
      forecast_state: 'ok',
      ...((overrides.weekly_decision as Record<string, unknown> | undefined) || {}),
    },
    top_recommendations: overrides.top_recommendations ?? [
      {
        id: 'rec-1',
        recommended_product: 'GeloMyrtol forte',
        region_codes: ['BE'],
        region_codes_display: ['BE'],
        decision_brief: {
          recommendation: { primary_region: 'Berlin' },
          summary_sentence: 'Berlin priorisieren.',
        },
      },
    ],
    business_validation: overrides.business_validation ?? {
      coverage_weeks: 26,
    },
    wave_run_id: 'wave-1',
  } as any;
}

function buildEvidence(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: '2026-03-21T09:00:00Z',
    source_status: overrides.source_status ?? {
      live_count: 2,
      total: 2,
      items: [{ status_color: 'green' }, { status_color: 'green' }],
    },
    forecast_monitoring: overrides.forecast_monitoring ?? {
      forecast_readiness: 'ready',
      monitoring_status: 'ok',
      freshness_status: 'fresh',
      alerts: [],
    },
    business_validation: overrides.business_validation ?? {
      coverage_weeks: 26,
    },
    truth_coverage: overrides.truth_coverage ?? {
      coverage_weeks: 30,
      trust_readiness: 'im_aufbau',
    },
  } as any;
}

function buildForecast(predictions?: Array<Record<string, unknown>>) {
  return {
    generated_at: '2026-03-21T09:00:00Z',
    predictions: predictions ?? [
      {
        bundesland: 'BE',
        bundesland_name: 'Berlin',
        event_probability: 0.81,
        decision_label: 'Prepare',
        decision_rank: 1,
        expected_target_incidence: 160,
        current_known_incidence: 110,
        reason_trace: { why: ['Berlin vorne'] },
      },
      {
        bundesland: 'BY',
        bundesland_name: 'Bayern',
        event_probability: 0.56,
        decision_label: 'Prepare',
        decision_rank: 2,
        expected_target_incidence: 130,
        current_known_incidence: 101,
        reason_trace: { why: ['Bayern folgt'] },
      },
      {
        bundesland: 'SN',
        bundesland_name: 'Sachsen',
        event_probability: 0.43,
        decision_label: 'Watch',
        decision_rank: 3,
        expected_target_incidence: 115,
        current_known_incidence: 99,
        reason_trace: { why: ['Sachsen beobachten'] },
      },
      {
        bundesland: 'NW',
        bundesland_name: 'Nordrhein-Westfalen',
        event_probability: 0.31,
        decision_label: 'Watch',
        decision_rank: 4,
        expected_target_incidence: 108,
        current_known_incidence: 97,
        reason_trace: { why: ['Nur Reserve'] },
      },
    ],
  } as any;
}

function buildRegions(topRegionCode: string, topRegionName: string) {
  return {
    virus_typ: 'Influenza A',
    target_source: 'regional',
    generated_at: '2026-03-21T09:00:00Z',
    map: {
      has_data: true,
      date: '2026-03-21',
      max_viruslast: 100,
      regions: {
        [topRegionCode]: {
          name: topRegionName,
          avg_viruslast: 82,
          intensity: 0.82,
          trend: 'steigend',
          change_pct: 18,
          n_standorte: 2,
          signal_score: 0.82,
          priority_rank: 1,
        },
      },
      top_regions: [
        {
          code: topRegionCode,
          name: topRegionName,
          trend: 'steigend',
          signal_score: 0.82,
          priority_rank: 1,
        },
      ],
      activation_suggestions: [],
    },
    top_regions: [
      {
        code: topRegionCode,
        name: topRegionName,
        trend: 'steigend',
        signal_score: 0.82,
      },
    ],
  } as any;
}

function buildBriefingView(input: {
  decision?: any;
  evidence?: any;
  forecast?: any;
}) {
  const decision = input.decision ?? buildDecision();
  const evidence = input.evidence ?? buildEvidence();
  const forecast = input.forecast ?? buildForecast();
  const workspaceStatus = buildWorkspaceStatus(decision, evidence);

  return buildNowPageViewModel(
    decision,
    evidence,
    forecast,
    null,
    null,
    workspaceStatus,
    120000,
    7,
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

  it('uses the preferred focus region for the hero backtest when Virus-Radar provides one', async () => {
    mockedMediaApi.getDecision.mockResolvedValue(buildDecision() as any);
    mockedMediaApi.getEvidence.mockResolvedValue(buildEvidence() as any);
    mockedMediaApi.getBacktestRun.mockResolvedValue({ run_id: 'wave-1' } as any);
    mockedMediaApi.getRegionalForecast.mockResolvedValue(buildForecast() as any);
    mockedMediaApi.getRegionalAllocation.mockResolvedValue({ generated_at: '2026-03-21T09:00:00Z', recommendations: [] } as any);
    mockedMediaApi.getRegionalCampaignRecommendations.mockResolvedValue({ generated_at: '2026-03-21T09:00:00Z', recommendations: [] } as any);
    mockedMediaApi.getWaveRadar.mockResolvedValue({ generated_at: '2026-03-21T09:00:00Z', waves: [] } as any);
    mockedMediaApi.getRegionalBacktest.mockResolvedValue({
      bundesland: 'BY',
      bundesland_name: 'Bayern',
      timeline: [],
    } as any);

    render(<PreferredFocusHarness />);

    await waitFor(() => expect(screen.getByTestId('preferred-focus-loading')).toHaveTextContent('ready'));

    expect(mockedMediaApi.getRegionalBacktest).toHaveBeenCalledWith('Influenza A', 'BY', 7);
  });

  it('uses the bundesland with the strongest absolute forecast growth for the hero backtest', async () => {
    mockedMediaApi.getDecision.mockResolvedValue(buildDecision() as any);
    mockedMediaApi.getEvidence.mockResolvedValue(buildEvidence() as any);
    mockedMediaApi.getBacktestRun.mockResolvedValue({ run_id: 'wave-1' } as any);
    mockedMediaApi.getRegionalForecast.mockResolvedValue(buildForecast([
      {
        bundesland: 'BE',
        bundesland_name: 'Berlin',
        decision_rank: 1,
        event_probability: 0.81,
        expected_target_incidence: 170,
        current_known_incidence: 150,
      },
      {
        bundesland: 'BY',
        bundesland_name: 'Bayern',
        decision_rank: 2,
        event_probability: 0.56,
        expected_target_incidence: 160,
        current_known_incidence: 90,
      },
    ]) as any);
    mockedMediaApi.getRegionalAllocation.mockResolvedValue({ generated_at: '2026-03-21T09:00:00Z', recommendations: [] } as any);
    mockedMediaApi.getRegionalCampaignRecommendations.mockResolvedValue({ generated_at: '2026-03-21T09:00:00Z', recommendations: [] } as any);
    mockedMediaApi.getWaveRadar.mockResolvedValue({ generated_at: '2026-03-21T09:00:00Z', waves: [] } as any);
    mockedMediaApi.getRegionalBacktest.mockResolvedValue({
      bundesland: 'BY',
      bundesland_name: 'Bayern',
      timeline: [],
    } as any);

    render(<Harness />);

    await waitFor(() => expect(screen.getByTestId('loading-state')).toHaveTextContent('ready'));

    expect(mockedMediaApi.getRegionalBacktest).toHaveBeenCalledWith('Influenza A', 'BY', 7);
  });
});

describe('useTimegraphPageData', () => {
  const mockedMediaApi = mediaApi as jest.Mocked<typeof mediaApi>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('defaults to the highest-ranked forecast region and reloads the graph when the region changes', async () => {
    mockedMediaApi.getRegionalForecast.mockResolvedValue(buildForecast([
      {
        bundesland: 'BE',
        bundesland_name: 'Berlin',
        decision_rank: 1,
        expected_target_incidence: 160,
        current_known_incidence: 110,
      },
      {
        bundesland: 'BY',
        bundesland_name: 'Bayern',
        decision_rank: 2,
        expected_target_incidence: 140,
        current_known_incidence: 101,
      },
    ]) as any);
    mockedMediaApi.getRegionalBacktest.mockImplementation(async (_virus, regionCode) => ({
      bundesland: regionCode,
      bundesland_name: regionCode === 'BY' ? 'Bayern' : 'Berlin',
      timeline: [],
    }) as any);

    render(<TimegraphHarness />);

    await waitFor(() => expect(screen.getByTestId('timegraph-loading')).toHaveTextContent('ready'));
    await waitFor(() => expect(screen.getByTestId('timegraph-backtest')).toHaveTextContent('Berlin'));

    expect(mockedMediaApi.getRegionalForecast).toHaveBeenCalledWith('Influenza A', 7, 'gelo');
    expect(mockedMediaApi.getRegionalBacktest).toHaveBeenCalledWith('Influenza A', 'BE', 7);
    expect(screen.getByTestId('timegraph-region')).toHaveTextContent('BE');
    expect(screen.getByTestId('timegraph-region-options')).toHaveTextContent('BE,BY');
    expect(screen.getByTestId('timegraph-prediction')).toHaveTextContent('Berlin');

    act(() => {
      screen.getByRole('button', { name: 'Region BY' }).click();
    });

    await waitFor(() => expect(screen.getByTestId('timegraph-region')).toHaveTextContent('BY'));
    await waitFor(() => expect(screen.getByTestId('timegraph-backtest')).toHaveTextContent('Bayern'));
    expect(mockedMediaApi.getRegionalBacktest).toHaveBeenLastCalledWith('Influenza A', 'BY', 7);
  });

  it('stays calm when no forecast regions are available', async () => {
    mockedMediaApi.getRegionalForecast.mockResolvedValue(buildForecast([]) as any);

    render(<TimegraphHarness />);

    await waitFor(() => expect(screen.getByTestId('timegraph-loading')).toHaveTextContent('ready'));

    expect(screen.getByTestId('timegraph-region')).toHaveTextContent('-');
    expect(screen.getByTestId('timegraph-region-options')).toHaveTextContent('-');
    expect(screen.getByTestId('timegraph-prediction')).toHaveTextContent('-');
    expect(screen.getByTestId('timegraph-backtest')).toHaveTextContent('-');
    expect(mockedMediaApi.getRegionalBacktest).not.toHaveBeenCalled();
  });
});

describe('useRegionsPageData', () => {
  const mockedMediaApi = mediaApi as jest.Mocked<typeof mediaApi>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('keeps the newer region result when an older request resolves later', async () => {
    const firstRegions = createDeferred<any>();
    const secondRegions = createDeferred<any>();
    const firstEvidence = createDeferred<any>();
    const secondEvidence = createDeferred<any>();

    mockedMediaApi.getRegions
      .mockImplementationOnce(() => firstRegions.promise)
      .mockImplementationOnce(() => secondRegions.promise);
    mockedMediaApi.getEvidence
      .mockImplementationOnce(() => firstEvidence.promise)
      .mockImplementationOnce(() => secondEvidence.promise);

    const { rerender } = render(<RegionsHarness dataVersion={0} />);

    expect(screen.getByTestId('regions-loading')).toHaveTextContent('loading');

    await act(async () => {
      rerender(<RegionsHarness dataVersion={1} />);
      await Promise.resolve();
    });

    await act(async () => {
      secondRegions.resolve(buildRegions('BY', 'Bayern'));
      secondEvidence.resolve(buildEvidence());
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByTestId('regions-loading')).toHaveTextContent('ready');
    });
    expect(screen.getByTestId('regions-top')).toHaveTextContent('BY');

    await act(async () => {
      firstRegions.resolve(buildRegions('BE', 'Berlin'));
      firstEvidence.resolve(buildEvidence());
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByTestId('regions-top')).toHaveTextContent('BY');
    });
  });
});

describe('buildNowPageViewModel', () => {
  it('limits secondary moves to two alternatives', () => {
    const view = buildBriefingView({});

    expect(view.secondaryMoves).toHaveLength(2);
    expect(view.secondaryMoves.map((item) => item.name)).toEqual(['Bayern', 'Sachsen']);
  });

  it('focuses the virus radar on the bundesland with the strongest absolute forecast growth', () => {
    const view = buildBriefingView({
      decision: buildDecision({
        top_recommendations: [
          {
            id: 'rec-1',
            recommended_product: 'GeloMyrtol forte',
            region_codes: ['BE'],
            region_codes_display: ['BE'],
            decision_brief: {
              recommendation: { primary_region: 'Berlin' },
              summary_sentence: 'Berlin priorisieren.',
            },
          },
          {
            id: 'rec-2',
            recommended_product: 'GeloMyrtol forte',
            region_codes: ['BY'],
            region_codes_display: ['BY'],
            decision_brief: {
              recommendation: { primary_region: 'Bayern' },
              summary_sentence: 'Bayern priorisieren.',
            },
          },
        ],
      }),
      forecast: buildForecast([
        {
          bundesland: 'BE',
          bundesland_name: 'Berlin',
          event_probability: 0.81,
          decision_label: 'Prepare',
          decision_rank: 1,
          expected_target_incidence: 170,
          current_known_incidence: 150,
          reason_trace: { why: ['Berlin vorne im alten Ranking'] },
        },
        {
          bundesland: 'BY',
          bundesland_name: 'Bayern',
          event_probability: 0.72,
          decision_label: 'Prepare',
          decision_rank: 2,
          expected_target_incidence: 160,
          current_known_incidence: 90,
          reason_trace: { why: ['Bayern wächst absolut am stärksten'] },
        },
      ]),
    });

    expect(view.focusRegion?.code).toBe('BY');
    expect(view.focusRegion?.name).toBe('Bayern');
    expect(view.heroRecommendation?.region).toBe('Bayern');
    expect(view.primaryRecommendationId).toBe('rec-2');
  });

  it.each([
    [
      'strong',
      buildDecision({
        business_validation: {
          validated_for_budget_activation: true,
        },
      }),
      buildEvidence({
        business_validation: {
          validated_for_budget_activation: true,
        },
      }),
      buildForecast(),
      'Bereit für Review',
    ],
    [
      'guarded',
      buildDecision(),
      buildEvidence(),
      buildForecast(),
      'Mit Vorsicht prüfen',
    ],
    [
      'weak',
      buildDecision({
        top_regions: [],
        top_recommendations: [],
        weekly_decision: {
          recommended_action: '',
          why_now: [],
          top_regions: [],
        },
      }),
      buildEvidence({
        source_status: null,
        forecast_monitoring: {
          monitoring_status: 'watch',
          freshness_status: 'stale',
          alerts: [],
        },
        business_validation: null,
        truth_coverage: null,
      }),
      { generated_at: '2026-03-21T09:00:00Z', predictions: [] } as any,
      'Noch keine belastbare Empfehlung',
    ],
    [
      'blocked',
      buildDecision({
        weekly_decision: {
          risk_flags: ['Die Revision der Quelldaten bleibt sichtbar.'],
        },
      }),
      buildEvidence(),
      buildForecast(),
      'Vor Review blockiert',
    ],
  ])('derives the %s briefing state from existing signals', (_label, decision, evidence, forecast, expectedStateLabel) => {
    const view = buildBriefingView({ decision, evidence, forecast });

    expect(view.heroRecommendation?.stateLabel).toBe(expectedStateLabel);
    expect(view.heroRecommendation?.state).toBe(_label);
  });

  it('creates an honest weak empty state when no reliable weekly recommendation exists', () => {
    const view = buildBriefingView({
      decision: buildDecision({
        top_regions: [],
        top_recommendations: [],
        weekly_decision: {
          recommended_action: '',
          why_now: [],
          top_regions: [],
        },
      }),
      evidence: buildEvidence({
        source_status: null,
        forecast_monitoring: {
          monitoring_status: 'watch',
          freshness_status: 'stale',
          alerts: [],
        },
      }),
      forecast: { generated_at: '2026-03-21T09:00:00Z', predictions: [] } as any,
    });

    expect(view.emptyState?.title).toBe('Noch keine belastbare Wochenempfehlung.');
    expect(view.primaryActionLabel).toBe('Top-Empfehlung prüfen');
  });
});
