import '@testing-library/jest-dom';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import TriLayerPage from './TriLayerPage';
import { useTriLayerSnapshot } from './useTriLayerSnapshot';
import type { TriLayerSnapshot } from './types';

jest.mock('./useTriLayerSnapshot', () => ({
  useTriLayerSnapshot: jest.fn(),
}));

const mockedUseTriLayerSnapshot = useTriLayerSnapshot as jest.MockedFunction<typeof useTriLayerSnapshot>;

const baseSnapshot: TriLayerSnapshot = {
  module: 'tri_layer_evidence_fusion',
  version: 'tlef_bicg_v0',
  mode: 'research',
  as_of: '2026-05-02T08:00:00Z',
  virus_typ: 'Influenza A',
  horizon_days: 7,
  brand: 'gelo',
  summary: {
    early_warning_score: 68.4,
    commercial_relevance_score: null,
    budget_permission_state: 'shadow_only',
    budget_can_change: false,
    reason: 'Sales calibration layer is not connected.',
  },
  source_status: {
    wastewater: { status: 'partial', coverage: 0.5, freshness_days: 2 },
    clinical: { status: 'connected', coverage: 0.75, freshness_days: 1 },
    sales: { status: 'not_connected', coverage: null, freshness_days: null },
  },
  regions: [
    {
      region: 'Rheinland-Pfalz',
      region_code: 'RP',
      early_warning_score: 61.2,
      phase_lead_rank: 1,
      phase_lead_score: 61.2,
      phase_lead_p_up_h7: 0.62,
      phase_lead_p_surge_h7: 0.54,
      phase_lead_growth: 0.432,
      phase_lead_drivers: ['SARS-CoV-2', 'Influenza B'],
      commercial_relevance_score: null,
      budget_permission_state: 'shadow_only',
      wave_phase: 'early_growth',
      posterior: {
        intensity_mean: 0.82,
        intensity_p10: 55,
        intensity_p90: 93,
        growth_mean: 0.24,
        uncertainty: 0.22,
      },
      evidence_weights: {
        wastewater: null,
        clinical: 1,
        sales: null,
      },
      lead_lag: {
        wastewater_to_clinical_days_mean: null,
        clinical_to_sales_days_mean: null,
        lag_uncertainty: null,
      },
      gates: {
        epidemiological_signal: 'pass',
        clinical_confirmation: 'pass',
        sales_calibration: 'not_available',
        coverage: 'pass',
        drift: 'pass',
        budget_isolation: 'pass',
      },
      explanation: 'Research-only regional diagnostic built from existing FluxEngine regional forecast outputs.',
    },
  ],
  model_notes: [
    'Research-only. Does not change media budget.',
    'Sales layer is not connected.',
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <TriLayerPage />
    </MemoryRouter>,
  );
}

describe('TriLayerPage', () => {
  const originalFetch = global.fetch;
  const fetchMock = jest.fn<Promise<Response>, [RequestInfo | URL, RequestInit?]>();

  function mockJson(body: unknown, status = 200): Response {
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    } as Response;
  }

  beforeAll(() => {
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  beforeEach(() => {
    mockedUseTriLayerSnapshot.mockReset();
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(mockJson({ report: null }));
  });

  it('renders the research-only warning and budget safety state', () => {
    mockedUseTriLayerSnapshot.mockReturnValue({
      snapshot: baseSnapshot,
      loading: false,
      error: null,
      reload: jest.fn(),
    });

    renderPage();

    expect(screen.getByRole('heading', { name: /Tri-Layer Evidence Fusion — Research Layer/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Research-only\. This page does not activate or change media budget\./).length).toBeGreaterThan(0);
    expect(screen.getByText('Phase-Lead Frühwarn-Score')).toBeInTheDocument();
    expect(screen.getByText(/Regionaler Atemwegsdruck aus Phase-Lead/i)).toBeInTheDocument();
    expect(screen.getByText('Budget can change: false')).toBeInTheDocument();
  });

  it('explains why cockpit signal and tri-layer score can differ', () => {
    mockedUseTriLayerSnapshot.mockReturnValue({
      snapshot: {
        ...baseSnapshot,
        summary: {
          ...baseSnapshot.summary,
          early_warning_score: 27.3,
        },
      },
      loading: false,
      error: null,
      reload: jest.fn(),
    });

    renderPage();

    expect(screen.getByRole('heading', { name: /Phase-Lead-Priorität ≠ Budget-Freigabe/i })).toBeInTheDocument();
    expect(screen.getByText(/Phase-Lead liefert die regionale Atemwegs-Priorität/i)).toBeInTheDocument();
    expect(screen.getByText(/Rheinland-Pfalz ist die aktuelle Phase-Lead-Top-Region/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Horizon 7 days/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Budget bleibt blockiert/i).length).toBeGreaterThan(0);
  });

  it('shows missing Sales honestly and renders region rows', () => {
    mockedUseTriLayerSnapshot.mockReturnValue({
      snapshot: baseSnapshot,
      loading: false,
      error: null,
      reload: jest.fn(),
    });

    renderPage();

    expect(screen.getAllByText('Sales layer not connected').length).toBeGreaterThan(0);
    expect(screen.getByRole('cell', { name: /Rheinland-Pfalz/i })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'RP' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: /SARS-CoV-2 \+ Influenza B/i })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: /shadow only/i })).toBeInTheDocument();
  });

  it('does not crash on unsupported or missing regional data', () => {
    mockedUseTriLayerSnapshot.mockReturnValue({
      snapshot: {
        ...baseSnapshot,
        summary: {
          ...baseSnapshot.summary,
          early_warning_score: null,
          budget_permission_state: 'blocked',
        },
        regions: [],
        model_notes: ['Regional forecast artifact diagnostic: Bitte horizon-spezifisches Training starten.'],
      },
      loading: false,
      error: null,
      reload: jest.fn(),
    });

    renderPage();

    expect(screen.getByText('No regional rows available for this research snapshot.')).toBeInTheDocument();
    expect(screen.getByText(/Bitte horizon-spezifisches Training starten/i)).toBeInTheDocument();
  });

  it('uses the cockpit gate for 401 errors', () => {
    const error = new Error('HTTP 401 — Tri-Layer-Snapshot nicht verfügbar') as Error & { status?: number };
    error.status = 401;
    mockedUseTriLayerSnapshot.mockReturnValue({
      snapshot: null,
      loading: false,
      error,
      reload: jest.fn(),
    });

    renderPage();

    expect(screen.getByLabelText(/Passwort/i)).toBeInTheDocument();
  });

  it('renders the backtest no-report state and safety warning', async () => {
    mockedUseTriLayerSnapshot.mockReturnValue({
      snapshot: baseSnapshot,
      loading: false,
      error: null,
      reload: jest.fn(),
    });
    fetchMock.mockResolvedValueOnce(mockJson({ report: null }));

    renderPage();

    expect(await screen.findByText('No completed Tri-Layer backtest report yet.')).toBeInTheDocument();
    expect(screen.getByText('Research backtest only. Does not affect live cockpit decisions.')).toBeInTheDocument();
    expect(screen.getByText('include_sales=false means Budget Permission cannot exceed shadow_only.')).toBeInTheDocument();
  });

  it('starts a backtest and polls running status until success', async () => {
    mockedUseTriLayerSnapshot.mockReturnValue({
      snapshot: baseSnapshot,
      loading: false,
      error: null,
      reload: jest.fn(),
    });
    fetchMock
      .mockResolvedValueOnce(mockJson({ report: null }))
      .mockResolvedValueOnce(mockJson({
        status: 'started',
        run_id: 'tlef-run',
        status_url: '/api/v1/media/cockpit/tri-layer/backtest/tlef-run',
      }, 202))
      .mockResolvedValueOnce(mockJson({
        run_id: 'tlef-run',
        status: 'STARTED',
      }))
      .mockResolvedValueOnce(mockJson({
        run_id: 'tlef-run',
        status: 'SUCCESS',
        report: {
          status: 'complete',
          run_id: 'tlef-run',
          virus_typ: 'Influenza A',
          horizon_days: 7,
          date_range: { start_date: '2024-10-01', end_date: '2024-10-10' },
          cutoffs: 4,
          regions: 2,
          source_availability: {
            wastewater: { status: 'connected', rows: 4 },
            survstat: { status: 'connected', rows: 4 },
            notaufnahme: { status: 'not_connected', rows: 0 },
            sales: { status: 'not_connected' },
          },
          metrics: {
            number_of_cutoffs: 4,
            onset_detection_gain: 0.25,
            peak_lead_time: 5,
            false_early_warning_rate: 0.1,
            phase_accuracy: 0.5,
            sales_lift_predictiveness: null,
            budget_regret_reduction: null,
            calibration_error: 0.2,
            pr_auc: null,
            gate_transition_counts: {
              sales_calibration: { pass: 0, watch: 0, fail: 0, not_available: 4 },
            },
          },
          models: {
            persistence: { brier_score: 0.4, onset_detection_gain: 0 },
            clinical_only: { brier_score: 0.3, onset_detection_gain: 0.1 },
            wastewater_only: { brier_score: null, onset_detection_gain: null },
            wastewater_plus_clinical: { brier_score: 0.2, onset_detection_gain: 0.25 },
            forecast_proxy_only: { brier_score: null, onset_detection_gain: null },
            tri_layer_epi_no_sales: { brier_score: 0.2, onset_detection_gain: 0.25 },
          },
          incremental_value: {
            wastewater_vs_clinical_only: { onset_detection_gain_delta: 0.15 },
            tri_layer_vs_persistence: { brier_score_delta: -0.2 },
            forecast_proxy_vs_raw_tri_layer: { status: 'not_evaluated' },
          },
          claim_readiness: {
            earlier_than_clinical: 'pass',
            better_than_persistence: 'watch',
            commercially_validated: 'fail',
            budget_ready: 'fail',
          },
          allowed_claims: ['Earlier epidemiological warning in this backtest window.'],
          forbidden_claims: ['Commercial lift validated.', 'Budget optimization validated.', 'ROI improvement proven.'],
          baselines: {
            persistence: { description: 'Persistence' },
            clinical_only: { description: 'Clinical' },
            wastewater_plus_clinical: { description: 'Epi' },
            tri_layer_without_budget_isolation: { false_budget_triggers: 2 },
            tri_layer_with_budget_isolation: { false_budget_triggers: 1 },
          },
        },
      }));

    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /Start backtest/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/media/cockpit/tri-layer/backtest',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    ));
    await waitFor(() => expect(screen.getByText('Status: STARTED')).toBeInTheDocument());
    expect(await screen.findByText('number_of_cutoffs')).toBeInTheDocument();
    expect(screen.getByText('0.250')).toBeInTheDocument();
    expect(screen.getAllByText('not evaluated').length).toBeGreaterThan(0);
    expect(screen.getByText('tri_layer_with_budget_isolation')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Scientific Validation/i })).toBeInTheDocument();
    expect(screen.getAllByText('wastewater_plus_clinical').length).toBeGreaterThan(0);
    expect(screen.getByText('Earlier epidemiological warning in this backtest window.')).toBeInTheDocument();
    expect(screen.getByText('Commercial lift validated.')).toBeInTheDocument();
  });

  it('renders polling failure without implying production impact', async () => {
    mockedUseTriLayerSnapshot.mockReturnValue({
      snapshot: baseSnapshot,
      loading: false,
      error: null,
      reload: jest.fn(),
    });
    fetchMock
      .mockResolvedValueOnce(mockJson({ report: null }))
      .mockResolvedValueOnce(mockJson({
        status: 'started',
        run_id: 'tlef-fail',
        status_url: '/api/v1/media/cockpit/tri-layer/backtest/tlef-fail',
      }, 202))
      .mockResolvedValueOnce(mockJson({
        run_id: 'tlef-fail',
        status: 'FAILURE',
        error: 'sales source unavailable',
      }));

    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /Start backtest/i }));

    expect(await screen.findByText(/sales source unavailable/i)).toBeInTheDocument();
    expect(screen.getByText('Research backtest only. Does not affect live cockpit decisions.')).toBeInTheDocument();
  });
});
