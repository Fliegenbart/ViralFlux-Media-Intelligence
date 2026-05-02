import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';

import { useTriLayerSnapshot } from './useTriLayerSnapshot';

function mockJsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  } as Response;
}

const payload = {
  module: 'tri_layer_evidence_fusion',
  version: 'tlef_bicg_v0',
  mode: 'research',
  as_of: '2026-05-02T08:00:00Z',
  virus_typ: 'Influenza A',
  horizon_days: 7,
  brand: 'gelo',
  summary: {
    early_warning_score: null,
    commercial_relevance_score: null,
    budget_permission_state: 'blocked',
    budget_can_change: false,
    reason: 'Research-only diagnostic snapshot.',
  },
  regions: [],
  source_status: {
    wastewater: { status: 'not_connected', coverage: null, freshness_days: null },
    clinical: { status: 'not_connected', coverage: null, freshness_days: null },
    sales: { status: 'not_connected', coverage: null, freshness_days: null },
  },
  model_notes: ['Research-only. Does not change media budget.', 'Sales layer is not connected.'],
};

function Harness() {
  const { snapshot, loading, error } = useTriLayerSnapshot({
    virusTyp: 'Influenza A',
    horizonDays: 7,
    brand: 'gelo',
    client: 'GELO',
    mode: 'research',
  });

  return (
    <div>
      <div data-testid="loading">{loading ? 'loading' : 'ready'}</div>
      <div data-testid="module">{snapshot?.module ?? '-'}</div>
      <div data-testid="sales">{snapshot?.source_status.sales.status ?? '-'}</div>
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

describe('useTriLayerSnapshot', () => {
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

  it('fetches the protected tri-layer endpoint with cookie credentials', async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse(payload));

    renderHarness();

    await waitFor(() => expect(screen.getByTestId('module')).toHaveTextContent('tri_layer_evidence_fusion'));
    expect(screen.getByTestId('sales')).toHaveTextContent('not_connected');

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(
      '/api/v1/media/cockpit/tri-layer/snapshot?virus_typ=Influenza+A&horizon_days=7&brand=gelo&client=GELO&mode=research',
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
});
