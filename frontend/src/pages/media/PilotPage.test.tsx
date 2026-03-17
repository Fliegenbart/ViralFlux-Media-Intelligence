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
  scopeReadiness = 'WATCH',
  budgetReleaseStatus = 'WATCH',
}: {
  virus: string;
  horizonDays: number;
  leadRegion: string;
  emptyState?: 'ready' | 'no_model' | 'no_data' | 'watch_only' | 'no_go';
  scopeReadiness?: 'GO' | 'WATCH' | 'NO_GO';
  budgetReleaseStatus?: 'GO' | 'WATCH' | 'NO_GO';
}) {
  const allocationScopeStatus: 'GO' | 'WATCH' = budgetReleaseStatus === 'GO' ? 'GO' : 'WATCH';
  const epidemiologyStatus: 'GO' | 'NO_GO' = scopeReadiness === 'NO_GO' ? 'NO_GO' : 'GO';
  const commercialStatus: 'GO' | 'WATCH' | 'NO_GO' = budgetReleaseStatus;
  const holdoutStatus: 'GO' | 'WATCH' = budgetReleaseStatus === 'GO' ? 'GO' : 'WATCH';
  return {
    pilotReadout: {
      brand: 'gelo',
      virus_typ: virus,
      horizon_days: horizonDays,
      run_context: {
        scope_readiness: scopeReadiness,
        scope_readiness_by_section: {
          forecast: scopeReadiness,
          allocation: allocationScopeStatus,
          recommendation: scopeReadiness,
          evidence: allocationScopeStatus,
        },
        gate_snapshot: {
          scope_readiness: scopeReadiness,
          epidemiology_status: epidemiologyStatus,
          commercial_data_status: commercialStatus,
          holdout_status: holdoutStatus,
          budget_release_status: budgetReleaseStatus,
          missing_requirements: budgetReleaseStatus === 'GO'
            ? []
            : ['Validated incremental lift metrics are still missing.'],
          coverage_weeks: 18,
          validation_status: budgetReleaseStatus === 'GO'
            ? 'passed_holdout_validation'
            : 'pending_holdout_validation',
          latest_evaluation: {
            available: true,
            run_id: 'run-123',
            gate_outcome: scopeReadiness,
            retained: scopeReadiness === 'GO',
          },
        },
      },
      executive_summary: {
        what_should_we_do_now: `Prioritize ${leadRegion} for ${virus}.`,
        decision_stage: leadRegion === 'Berlin' ? 'Activate' : 'Watch',
        scope_readiness: scopeReadiness,
        headline: `${virus} pilot summary`,
        top_regions: [
          {
            region_code: leadRegion === 'Berlin' ? 'BE' : 'BY',
            region_name: leadRegion,
            decision_stage: leadRegion === 'Berlin' ? 'Activate' : 'Watch',
            priority_score: 0.88,
            event_probability: 0.81,
            budget_amount_eur: 64000,
            confidence: 0.72,
            reason_trace: [`${leadRegion} is the current lead region.`],
          },
        ],
        budget_recommendation: {
          weekly_budget_eur: 120000,
          recommended_active_budget_eur: budgetReleaseStatus === 'GO' ? 120000 : 0,
          spend_enabled: budgetReleaseStatus === 'GO',
          blocked_reasons: budgetReleaseStatus === 'GO'
            ? []
            : ['Budget release is still blocked.'],
        },
        confidence_summary: {
          lead_region_confidence: 0.72,
          lead_region_event_probability: 0.81,
          evaluation_retained: scopeReadiness === 'GO',
          evaluation_gate_outcome: scopeReadiness,
        },
        uncertainty_summary: 'Revision risk remains visible.',
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
          scope_readiness: scopeReadiness,
          epidemiology_status: epidemiologyStatus,
          commercial_data_status: commercialStatus,
          holdout_status: holdoutStatus,
          budget_release_status: budgetReleaseStatus,
          missing_requirements: budgetReleaseStatus === 'GO'
            ? []
            : ['Validated incremental lift metrics are still missing.'],
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
          ? 'No customer-ready model is available for this scope.'
          : emptyState === 'no_data'
            ? 'The model path exists, but there is not enough live data for a pilot decision right now.'
            : emptyState === 'watch_only'
              ? 'The pilot can prioritize regions, but budget release stays on watch.'
              : emptyState === 'no_go'
                ? 'The scope remains intentionally blocked.'
                : 'The scope is customer-ready.',
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

    expect(screen.getByText('PEIX / GELO Pilot Surface')).toBeInTheDocument();
    expect(screen.getByText('What should we do now?')).toBeInTheDocument();
    expect(screen.getByText('Operational Recommendations')).toBeInTheDocument();
    expect(screen.getByText('Pilot Evidence / Readiness')).toBeInTheDocument();
    expect(screen.getByText('Prioritize Berlin for RSV A.')).toBeInTheDocument();
    expect(screen.getAllByText('Berlin is the current lead region.')).toHaveLength(2);
  });

  it('supports virus, horizon, scope, and stage filters without inventing new client logic', () => {
    mockedUsePilotSurfaceData.mockImplementation(({ virus, horizonDays }) => buildReadout({
      virus,
      horizonDays,
      leadRegion: virus === 'Influenza B' ? 'Bayern' : 'Berlin',
    }));

    render(<PilotPage />);

    fireEvent.change(screen.getByLabelText('Virus'), { target: { value: 'Influenza B' } });
    expect(screen.getByText('Prioritize Bayern for Influenza B.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Horizon'), { target: { value: '5' } });
    expect(mockedUsePilotSurfaceData).toHaveBeenLastCalledWith(expect.objectContaining({
      virus: 'Influenza B',
      horizonDays: 5,
    }), expect.any(Function));

    fireEvent.click(screen.getByRole('button', { name: 'Evidence' }));
    expect(screen.getAllByText('Pilot-Evidenz, Gates und Readiness').length).toBeGreaterThan(0);

    const operationalSection = screen.getByText('Operational Recommendations').closest('section');
    expect(operationalSection).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Watch' }));
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

    expect(screen.getByText('No customer-ready model is available for this scope.')).toBeInTheDocument();
  });

  it('renders the no_data empty state', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildReadout({
      virus: 'RSV A',
      horizonDays: 7,
      leadRegion: 'Berlin',
      emptyState: 'no_data',
    }));

    render(<PilotPage />);

    expect(screen.getByText('The model path exists, but there is not enough live data for a pilot decision right now.')).toBeInTheDocument();
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

    expect(screen.getByText('The pilot can prioritize regions, but budget release stays on watch.')).toBeInTheDocument();
    expect(screen.getByText('Validated incremental lift metrics are still missing.')).toBeInTheDocument();
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

    expect(screen.getByText('The scope remains intentionally blocked.')).toBeInTheDocument();
  });
});
