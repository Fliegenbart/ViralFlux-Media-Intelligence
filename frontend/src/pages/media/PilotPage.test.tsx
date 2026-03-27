import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';

import PilotPage from './PilotPage';
import { usePilotSurfaceData } from '../../features/media/usePilotSurfaceData';

jest.mock('../../features/media/usePilotSurfaceData');

const mockedUsePilotSurfaceData = usePilotSurfaceData as jest.MockedFunction<typeof usePilotSurfaceData>;

function buildReadout({
  virus,
  horizonDays,
  leadRegion,
  emptyState = 'ready',
  scopeReadiness = 'GO',
  budgetReleaseStatus = 'WATCH',
  liveCoverageReadiness = 'GO',
  liveFreshnessReadiness = 'GO',
}: {
  virus: string;
  horizonDays: number;
  leadRegion: string;
  emptyState?: 'ready' | 'no_model' | 'no_data' | 'watch_only' | 'no_go';
  scopeReadiness?: 'GO' | 'WATCH' | 'NO_GO';
  budgetReleaseStatus?: 'GO' | 'WATCH' | 'NO_GO';
  liveCoverageReadiness?: 'GO' | 'WATCH' | 'NO_GO';
  liveFreshnessReadiness?: 'GO' | 'WATCH' | 'NO_GO';
}) {
  const allocationScopeStatus: 'GO' | 'WATCH' = scopeReadiness === 'NO_GO' ? 'WATCH' : 'GO';
  const epidemiologyStatus: 'GO' | 'NO_GO' = scopeReadiness === 'NO_GO' ? 'NO_GO' : 'GO';
  const commercialStatus: 'GO' | 'WATCH' | 'NO_GO' = budgetReleaseStatus;
  const holdoutStatus: 'GO' | 'WATCH' = budgetReleaseStatus === 'GO' ? 'GO' : 'WATCH';
  const budgetMode = budgetReleaseStatus === 'GO' ? 'validated_allocation' : 'scenario_split';
  const operationalScopeStatus: 'GO' | 'WATCH' | 'NO_GO' = (
    liveCoverageReadiness === 'NO_GO' || liveFreshnessReadiness === 'NO_GO'
      ? 'NO_GO'
      : liveCoverageReadiness === 'WATCH' || liveFreshnessReadiness === 'WATCH'
        ? 'WATCH'
        : 'GO'
  );
  const liveCoverageStatus: 'ok' | 'warning' | 'critical' = liveCoverageReadiness === 'GO'
    ? 'ok'
    : liveCoverageReadiness === 'WATCH'
      ? 'warning'
      : 'critical';
  const liveFreshnessStatus: 'ok' | 'warning' | 'critical' = liveFreshnessReadiness === 'GO'
    ? 'ok'
    : liveFreshnessReadiness === 'WATCH'
      ? 'warning'
      : 'critical';
  const forecastRecencyStatus: 'ok' = 'ok';
  const forecastRecencyReadiness: 'GO' = 'GO';
  const validationDisclaimer = budgetReleaseStatus === 'GO'
    ? 'Forecast und kommerzielle Validierung greifen für diesen Scope bereits sauber zusammen.'
    : 'Diese Budgetsicht ist ein forecast-basierter Szenario-Split. Die kommerzielle Validierung für die Budgetfreigabe von GELO steht noch aus.';
  return {
    pilotReadout: {
      brand: 'gelo',
      virus_typ: virus,
      horizon_days: horizonDays,
      run_context: {
        forecast_readiness: scopeReadiness,
        commercial_validation_status: commercialStatus,
        pilot_mode: 'forecast_first',
        budget_mode: budgetMode,
        validation_disclaimer: validationDisclaimer,
        scope_readiness: scopeReadiness,
        scope_readiness_by_section: {
          forecast: epidemiologyStatus,
          allocation: allocationScopeStatus,
          recommendation: allocationScopeStatus,
          evidence: allocationScopeStatus,
        },
        gate_snapshot: {
          forecast_readiness: scopeReadiness,
          scope_readiness: scopeReadiness,
          epidemiology_status: epidemiologyStatus,
          commercial_data_status: commercialStatus,
          commercial_validation_status: commercialStatus,
          holdout_status: holdoutStatus,
          budget_release_status: budgetReleaseStatus,
          pilot_mode: 'forecast_first',
          budget_mode: budgetMode,
          validation_disclaimer: validationDisclaimer,
          missing_requirements: budgetReleaseStatus === 'GO'
            ? []
            : ['Validierte inkrementelle Lift-Metriken fehlen noch.'],
          coverage_weeks: 18,
          validation_status: budgetReleaseStatus === 'GO'
            ? 'passed_holdout_validation'
            : 'pending_holdout_validation',
          operational_readiness: {
            available: true,
            scope_status: operationalScopeStatus,
            live_source_coverage_status: liveCoverageStatus,
            live_source_freshness_status: liveFreshnessStatus,
            forecast_recency_status: forecastRecencyStatus,
            live_source_coverage_readiness: liveCoverageReadiness,
            live_source_freshness_readiness: liveFreshnessReadiness,
            forecast_recency_readiness: forecastRecencyReadiness,
            source_coverage_scope: 'artifact',
          },
          latest_evaluation: {
            available: true,
            run_id: 'run-123',
            gate_outcome: scopeReadiness,
            retained: scopeReadiness === 'GO',
          },
        },
      },
      executive_summary: {
        what_should_we_do_now: budgetReleaseStatus === 'GO'
          ? `Fokussiere ${leadRegion} jetzt für ${virus}.`
          : `Fokussiere ${leadRegion} jetzt für ${virus} und nutze die Verteilung unten als forecast-basierten Szenario-Split, solange die kommerzielle Validierung noch aussteht.`,
        decision_stage: leadRegion === 'Berlin' ? 'Activate' : 'Watch',
        forecast_readiness: scopeReadiness,
        commercial_validation_status: commercialStatus,
        pilot_mode: 'forecast_first',
        budget_mode: budgetMode,
        validation_disclaimer: validationDisclaimer,
        scope_readiness: scopeReadiness,
        headline: `${virus} Pilotübersicht`,
        top_regions: [
          {
            region_code: leadRegion === 'Berlin' ? 'BE' : 'BY',
            region_name: leadRegion,
            decision_stage: leadRegion === 'Berlin' ? 'Activate' : 'Watch',
            priority_score: 0.88,
            event_probability: 0.81,
            budget_amount_eur: 64000,
            confidence: 0.72,
            reason_trace_details: [
              {
                code: 'event_probability_activate_threshold',
                message: 'raw',
                params: { event_probability: 0.81, threshold: 0.7 },
              },
            ],
            reason_trace: [`${leadRegion} is the current lead region.`],
          },
        ],
        budget_recommendation: {
          weekly_budget_eur: 120000,
          recommended_active_budget_eur: 120000,
          scenario_budget_eur: 120000,
          spend_enabled: budgetReleaseStatus === 'GO',
          budget_mode: budgetMode,
          blocked_reasons: budgetReleaseStatus === 'GO'
            ? []
            : ['Die Budgetfreigabe ist aktuell noch blockiert.'],
        },
        confidence_summary: {
          lead_region_confidence: 0.72,
          lead_region_event_probability: 0.81,
          evaluation_retained: scopeReadiness === 'GO',
          evaluation_gate_outcome: scopeReadiness,
        },
        uncertainty_summary_detail: {
          code: 'uncertainty_summary',
          message: 'raw',
          params: { parts: ['revision_risk'], revision_risk: 0.33 },
        },
        uncertainty_summary: 'Revision risk remains visible.',
        reason_trace_details: [
          {
            code: 'event_probability_activate_threshold',
            message: 'raw',
            params: { event_probability: 0.81, threshold: 0.7 },
          },
        ],
        reason_trace: [`${leadRegion} is the current lead region.`],
      },
      operational_recommendations: {
        scope_readiness: scopeReadiness,
        summary: {
          headline: 'Operational plan',
          total_regions: 2,
          activate_regions: 1,
          prepare_regions: 0,
          watch_regions: 1,
          ready_recommendations: budgetReleaseStatus === 'GO' ? 1 : 0,
          guarded_recommendations: budgetReleaseStatus === 'GO' ? 0 : 1,
          observe_only_recommendations: 1,
        },
        regions: [
          {
            region_code: 'BE',
            region_name: 'Berlin',
            decision_stage: 'Activate',
            priority_rank: 1,
            priority_score: 0.88,
            event_probability: 0.81,
            budget_amount_eur: 64000,
            confidence: 0.72,
            recommended_product: 'Bronchial Recovery Support',
            recommended_keywords: 'Respiratory Relief Search',
            campaign_recommendation: 'Berlin recommendation',
            reason_trace_details: [
              {
                code: 'campaign_stage_budget_share',
                message: 'raw',
                params: { region_name: 'Berlin', stage: 'activate', budget_share: 0.58 },
              },
            ],
            uncertainty_summary_detail: {
              code: 'uncertainty_summary',
              message: 'raw',
              params: { parts: ['revision_risk'], revision_risk: 0.33 },
            },
            reason_trace: ['Berlin is the current lead region.'],
            uncertainty_summary: 'Revision risk remains visible.',
            budget_release_recommendation: 'Hold spend until lift metrics are validated.',
          },
          {
            region_code: 'BY',
            region_name: 'Bayern',
            decision_stage: 'Watch',
            priority_rank: 2,
            priority_score: 0.41,
            event_probability: 0.36,
            budget_amount_eur: 12000,
            confidence: 0.43,
            recommended_product: 'Respiratory Core Demand',
            recommended_keywords: 'Voice Recovery Search',
            campaign_recommendation: 'Bayern recommendation',
            reason_trace: ['Bayern stays below the action threshold.'],
            uncertainty_summary: 'Demand remains soft.',
            budget_release_recommendation: 'Keep on observe-only.',
          },
        ],
      },
      pilot_evidence: {
        scope_readiness: scopeReadiness,
        evaluation: {
          selected_experiment_name: scopeReadiness === 'GO' ? 'rsv_signal_core' : 'rsv_ranking',
          gate_outcome: scopeReadiness,
          retained: scopeReadiness === 'GO',
          calibration_mode: 'raw_passthrough',
          generated_at: '2026-03-17T10:00:00Z',
          comparison_table: [
            {
              role: 'baseline',
              name: 'baseline',
              precision_at_top3: 0.577778,
              activation_false_positive_rate: 0.005006,
              ece: 0.025965,
              brier: 0.028113,
              gate_outcome: 'WATCH',
              retained: true,
            },
            {
              role: 'experiment',
              name: 'rsv_signal_core',
              precision_at_top3: 0.6,
              activation_false_positive_rate: 0.003755,
              ece: 0.023418,
              brier: 0.026452,
              gate_outcome: scopeReadiness,
              retained: scopeReadiness === 'GO',
            },
          ],
        },
        readiness: {
          forecast_readiness: scopeReadiness,
          scope_readiness: scopeReadiness,
          epidemiology_status: epidemiologyStatus,
          commercial_data_status: commercialStatus,
          commercial_validation_status: commercialStatus,
          holdout_status: holdoutStatus,
          budget_release_status: budgetReleaseStatus,
          pilot_mode: 'forecast_first',
          budget_mode: budgetMode,
          validation_disclaimer: validationDisclaimer,
          missing_requirements: budgetReleaseStatus === 'GO'
            ? []
            : ['Validierte inkrementelle Lift-Metriken fehlen noch.'],
          coverage_weeks: 18,
          validation_status: budgetReleaseStatus === 'GO'
            ? 'passed_holdout_validation'
            : 'pending_holdout_validation',
        },
        legacy_context: {
          status: 'frozen',
          sunset_date: '2026-04-30',
          customer_surface_exposed: false,
        },
      },
      empty_state: {
        code: emptyState,
        title: emptyState === 'no_model'
          ? 'Für diesen Scope ist aktuell kein kundenfähiges Modell verfügbar.'
          : emptyState === 'no_data'
            ? 'Der Modellpfad existiert, aber aktuell reichen die Live-Daten noch nicht für eine Pilotentscheidung.'
            : emptyState === 'watch_only'
              ? 'Der Forecast ist nutzbar, die kommerzielle Validierung steht aber noch aus.'
              : emptyState === 'no_go'
                ? 'Dieser Scope bleibt bewusst gesperrt.'
                : 'Dieser Scope ist für den Forecast-First-Pilot bereit.',
        body: 'Surface body',
      },
    },
    loading: false,
    loadSurface: jest.fn(),
  };
}

describe('PilotPage', () => {
  beforeEach(() => {
    mockedUsePilotSurfaceData.mockReset();
  });

  it('renders the customer-facing summary, operational section, and evidence section', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildReadout({
      virus: 'RSV A',
      horizonDays: 7,
      leadRegion: 'Berlin',
    }));

    render(<PilotPage />);

    expect(screen.getByText('PEIX / GELO Pilotansicht')).toBeInTheDocument();
    expect(screen.getByText('Was sollten wir jetzt tun?')).toBeInTheDocument();
    expect(screen.getByText('Fokusbereich')).toBeInTheDocument();
    expect(screen.getByText('Forecast bereit')).toBeInTheDocument();
    expect(screen.getAllByText('Kommerzielle Validierung').length).toBeGreaterThan(0);
    expect(screen.getByText('Live-Quellabdeckung')).toBeInTheDocument();
    expect(screen.getByText('Live-Quellfrische')).toBeInTheDocument();
    expect(screen.getAllByText('Szenario-Split').length).toBeGreaterThan(0);
    expect(screen.getByText(/Event-Wahrscheinlichkeit ist die Forecast-Chance/i)).toBeInTheDocument();
    expect(screen.getByText('Die regionale virale Dynamik ist belastbar genug, um sie extern zu zeigen, zu priorisieren und zu besprechen.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Was PEIX GELO heute schon zeigen kann' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Operative Empfehlungen' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Pilot-Evidenz und Freigabestatus' })).toBeInTheDocument();
    expect(screen.getByText('Aktueller Freigabestatus')).toBeInTheDocument();
    expect(screen.getByText(/Fokussiere Berlin jetzt für RSV A und nutze die Verteilung unten als forecast-basierten Szenario-Split/i)).toBeInTheDocument();
  });

  it('renders GO readiness directly from backend data without client-side reinterpretation', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildReadout({
      virus: 'RSV A',
      horizonDays: 7,
      leadRegion: 'Berlin',
      scopeReadiness: 'GO',
      budgetReleaseStatus: 'GO',
    }));

    render(<PilotPage />);

    expect(screen.getAllByText('GO').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Validierte Allokation').length).toBeGreaterThan(0);
    expect(screen.getAllByText('rsv_signal_core').length).toBeGreaterThan(0);
  });

  it('shows live source readiness separately from artifact coverage on the pilot surface', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildReadout({
      virus: 'RSV A',
      horizonDays: 7,
      leadRegion: 'Berlin',
      scopeReadiness: 'WATCH',
      liveCoverageReadiness: 'GO',
      liveFreshnessReadiness: 'WATCH',
    }));

    render(<PilotPage />);

    expect(screen.getByText('Live-Quellabdeckung')).toBeInTheDocument();
    expect(screen.getByText('Live-Quellfrische')).toBeInTheDocument();
    expect(screen.getByText(/Artefakt-Coverage bleibt getrennt/i)).toBeInTheDocument();
    const evidenceSection = screen.getByText('Aktueller Freigabestatus').closest('.pilot-evidence-card') as HTMLElement | null;
    expect(evidenceSection).not.toBeNull();
    if (evidenceSection) {
      expect(within(evidenceSection).getByText('Live-Quellabdeckung')).toBeInTheDocument();
      expect(within(evidenceSection).getByText('Live-Quellfrische')).toBeInTheDocument();
      expect(within(evidenceSection).getAllByText('WATCH').length).toBeGreaterThan(0);
    }
  });

  it('supports virus, horizon, scope, and stage filters without inventing new client logic', () => {
    mockedUsePilotSurfaceData.mockImplementation(({ virus, horizonDays }) => buildReadout({
      virus,
      horizonDays,
      leadRegion: virus === 'Influenza B' ? 'Bayern' : 'Berlin',
    }));

    render(<PilotPage />);

    fireEvent.change(screen.getByLabelText('Virus'), { target: { value: 'Influenza B' } });
    expect(screen.getByText(/Fokussiere Bayern jetzt für Influenza B und nutze die Verteilung unten als forecast-basierten Szenario-Split/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Zeitraum'), { target: { value: '5' } });
    expect(mockedUsePilotSurfaceData).toHaveBeenLastCalledWith(expect.objectContaining({
      virus: 'Influenza B',
      horizonDays: 5,
    }), expect.any(Function));

    fireEvent.click(screen.getByRole('button', { name: 'Evidenz' }));
    expect(screen.getAllByText('Pilot-Evidenz und Freigabestatus').length).toBeGreaterThan(0);

    const operationalSection = screen.getByRole('heading', { name: 'Operative Empfehlungen' }).closest('section');
    expect(operationalSection).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Beobachten' }));
    expect(within(operationalSection as HTMLElement).queryByText('Berlin')).not.toBeInTheDocument();
    expect(within(operationalSection as HTMLElement).getByText('Bayern')).toBeInTheDocument();
  });

  it('renders the no_model empty state', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildReadout({
      virus: 'RSV A',
      horizonDays: 7,
      leadRegion: 'Berlin',
      emptyState: 'no_model',
      scopeReadiness: 'NO_GO',
      budgetReleaseStatus: 'NO_GO',
    }));

    render(<PilotPage />);

    expect(screen.getByText('Für diesen Scope ist aktuell kein kundenfähiges Modell verfügbar.')).toBeInTheDocument();
  });

  it('renders the no_data empty state', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildReadout({
      virus: 'RSV A',
      horizonDays: 7,
      leadRegion: 'Berlin',
      emptyState: 'no_data',
    }));

    render(<PilotPage />);

    expect(screen.getByText('Der Modellpfad existiert, aber aktuell reichen die Live-Daten noch nicht für eine Pilotentscheidung.')).toBeInTheDocument();
  });

  it('renders the watch_only empty state', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildReadout({
      virus: 'RSV A',
      horizonDays: 7,
      leadRegion: 'Berlin',
      emptyState: 'watch_only',
      scopeReadiness: 'WATCH',
      budgetReleaseStatus: 'WATCH',
    }));

    render(<PilotPage />);

    expect(screen.getByText('Der Forecast ist nutzbar, die kommerzielle Validierung steht aber noch aus.')).toBeInTheDocument();
    expect(screen.getAllByText('Validierte inkrementelle Lift-Metriken fehlen noch.').length).toBeGreaterThan(0);
  });

  it('renders the no_go empty state', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildReadout({
      virus: 'RSV A',
      horizonDays: 7,
      leadRegion: 'Berlin',
      emptyState: 'no_go',
      scopeReadiness: 'NO_GO',
      budgetReleaseStatus: 'NO_GO',
    }));

    render(<PilotPage />);

    expect(screen.getByText('Dieser Scope bleibt bewusst gesperrt.')).toBeInTheDocument();
  });
});
