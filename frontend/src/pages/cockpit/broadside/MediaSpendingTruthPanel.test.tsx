import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import MediaSpendingTruthPanel from './MediaSpendingTruthPanel';
import type { MediaSpendingTruthPayload } from '../types';

const basePayload: MediaSpendingTruthPayload = {
  schema_version: 'media_spending_truth_v1',
  decision_date: '2026-04-29',
  valid_until: '2026-05-06',
  global_status: 'blocked',
  budget_permission: 'blocked',
  forecast_evidence: 'blocked',
  data_quality: 'poor',
  regions: [
    {
      region_code: 'NW',
      region_name: 'Nordrhein-Westfalen',
      media_spending_truth: 'blocked',
      recommended_action: 'none',
      recommended_delta_pct: 0,
      max_delta_pct: 0,
      confidence: 0.42,
      budget_opportunity_score: 0.62,
      reason_codes: ['stale_data'],
      limiting_factors: ['artifact_quality_gate_not_passed'],
      manual_approval_required: false,
    },
  ],
  limitations: ['not_for_automatic_budget_execution'],
};

describe('MediaSpendingTruthPanel', () => {
  it('renders blocked state clearly', () => {
    render(<MediaSpendingTruthPanel truth={basePayload} />);

    expect(screen.getByTestId('media-spending-truth-panel')).toHaveClass('media-truth-blocked');
    expect(screen.getAllByText('Blockiert').length).toBeGreaterThan(0);
    expect(screen.getByText('Keine Budgetfreigabe')).toBeInTheDocument();
    expect(screen.getByText('Nordrhein-Westfalen')).toBeInTheDocument();
    expect(screen.getByText('Daten zu alt')).toBeInTheDocument();
  });

  it('renders planner-assist suggestions with manual approval', () => {
    render(
      <MediaSpendingTruthPanel
        truth={{
          ...basePayload,
          global_status: 'planner_assist',
          budget_permission: 'manual_approval_required',
          forecast_evidence: 'limited',
          data_quality: 'good',
          regions: [
            {
              ...basePayload.regions[0],
              media_spending_truth: 'preposition_approved',
              recommended_action: 'small_increase',
              recommended_delta_pct: 5,
              max_delta_pct: 5,
              confidence: 0.71,
              reason_codes: ['high_import_pressure', 'manual_approval_required'],
              manual_approval_required: true,
            },
          ],
        }}
      />,
    );

    expect(screen.getByText('Manuelle Prüfung')).toBeInTheDocument();
    expect(screen.getByText('Manuelle Freigabe nötig')).toBeInTheDocument();
    expect(screen.getByText('+5%')).toBeInTheDocument();
    expect(screen.getByText(/Früh positionieren/)).toBeInTheDocument();
  });

  it('renders spendable regional actions', () => {
    render(
      <MediaSpendingTruthPanel
        truth={{
          ...basePayload,
          global_status: 'spendable',
          budget_permission: 'approved_with_cap',
          forecast_evidence: 'validated',
          data_quality: 'good',
          regions: [
            {
              ...basePayload.regions[0],
              media_spending_truth: 'increase_approved',
              recommended_action: 'increase',
              recommended_delta_pct: 12,
              max_delta_pct: 15,
              confidence: 0.78,
              reason_codes: ['high_surge_probability'],
              manual_approval_required: false,
            },
          ],
        }}
      />,
    );

    expect(screen.getAllByText('Freigegeben mit Cap').length).toBeGreaterThan(0);
    expect(screen.getByText('Erhöhen freigegeben')).toBeInTheDocument();
    expect(screen.getByText('+12%')).toBeInTheDocument();
    expect(screen.getByText('hohe 7-Tage-Wachstumswahrscheinlichkeit')).toBeInTheDocument();
  });
});
