import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';

import { usePhaseLeadSnapshot } from './usePhaseLeadSnapshot';

function mockJsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const payload = {
  module: 'phase_lead_graph_renewal_filter',
  version: 'plgrf_live_v0',
  mode: 'research',
  as_of: '2026-05-04',
  virus_typ: 'Influenza A',
  horizons: [3, 5, 7],
  summary: {
    data_source: 'live_database',
    fit_mode: 'fast_initialization',
    observation_count: 120,
    window_start: '2026-02-17',
    window_end: '2026-04-27',
    converged: true,
    objective_value: 123.4,
    data_vintage_hash: 'abc',
    config_hash: 'def',
    top_region: 'HH',
    warning_count: 0,
  },
  sources: {
    wastewater: { rows: 70, latest_event_date: '2026-04-22', units: ['HH'] },
  },
  regions: [
    {
      region_code: 'HH',
      region: 'Hamburg',
      current_level: 10,
      current_growth: 0.1,
      p_up_h7: 0.75,
      p_surge_h7: 0.5,
      p_front: 0.4,
      eeb: 2,
      gegb: 3,
      source_rows: 70,
    },
  ],
  rankings: { 'Influenza A': [{ region_id: 'HH', gegb: 3 }] },
  warnings: [],
};

function Harness() {
  const { snapshot, error } = usePhaseLeadSnapshot({
    virusTyp: 'Influenza A',
    windowDays: 42,
    nSamples: 12,
    maxIter: 7,
  });

  return (
    <div>
      <div data-testid="module">{snapshot?.module ?? '-'}</div>
      <div data-testid="region">{snapshot?.regions[0]?.region_code ?? '-'}</div>
      <div data-testid="error">{error?.message ?? '-'}</div>
    </div>
  );
}

function AggregateHarness() {
  const { snapshot, error } = usePhaseLeadSnapshot({
    virusTyp: 'Gesamt',
    windowDays: 70,
    nSamples: 80,
  });

  return (
    <div>
      <div data-testid="module">{snapshot?.module ?? '-'}</div>
      <div data-testid="error">{error?.message ?? '-'}</div>
    </div>
  );
}

function renderHarness() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <Harness />
    </SWRConfig>,
  );
}

function renderAggregateHarness() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <AggregateHarness />
    </SWRConfig>,
  );
}

describe('usePhaseLeadSnapshot', () => {
  const originalFetch = global.fetch;
  const fetchMock = jest.fn<Promise<Response>, [RequestInfo | URL, RequestInit?]>();

  beforeAll(() => {
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  beforeEach(() => {
    fetchMock.mockReset();
  });

  it('fetches the protected phase-lead endpoint with cookie credentials', async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse(payload));

    renderHarness();

    await waitFor(() => expect(screen.getByTestId('module')).toHaveTextContent('phase_lead_graph_renewal_filter'));
    expect(screen.getByTestId('region')).toHaveTextContent('HH');

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(
      '/api/v1/media/cockpit/phase-lead/snapshot?virus_typ=Influenza+A&window_days=42&n_samples=12&max_iter=7',
    );
    expect(init?.credentials).toBe('include');
    expect(new Headers(init?.headers).get('Accept')).toBe('application/json');
  });

  it('surfaces fetch errors without a fixture fallback', async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ detail: 'Unauthorized' }, 401));

    renderHarness();

    await waitFor(() => expect(screen.getByTestId('error')).toHaveTextContent('HTTP 401'));
    expect(screen.getByTestId('module')).toHaveTextContent('-');
  });

  it('fetches the aggregate endpoint for the Gesamt tab', async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ ...payload, virus_typ: 'Gesamt' }));

    renderAggregateHarness();

    await waitFor(() => expect(screen.getByTestId('module')).toHaveTextContent('phase_lead_graph_renewal_filter'));

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(
      '/api/v1/media/cockpit/phase-lead/aggregate?window_days=70&n_samples=80',
    );
    expect(init?.credentials).toBe('include');
  });
});
