import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import OperationalDashboard from './OperationalDashboard';
import {
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastResponse,
} from '../../types/media';

function buildForecast(): RegionalForecastResponse {
  return {
    virus_typ: 'Influenza A',
    as_of_date: '2026-03-17',
    horizon_days: 7,
    supported_horizon_days: [3, 5, 7],
    target_window_days: [7, 7],
    decision_summary: {
      watch_regions: 1,
      prepare_regions: 0,
      activate_regions: 1,
      avg_priority_score: 0.61,
      top_region: 'BE',
      top_region_decision: 'Activate',
    },
    total_regions: 2,
    generated_at: '2026-03-17T09:00:00Z',
    top_5: [],
    top_decisions: [],
    predictions: [
      {
        bundesland: 'BE',
        bundesland_name: 'Berlin',
        virus_typ: 'Influenza A',
        as_of_date: '2026-03-17',
        target_date: '2026-03-24',
        target_week_start: '2026-03-23',
        target_window_days: [7, 7],
        horizon_days: 7,
        event_probability_calibrated: 0.81,
        expected_target_incidence: 114.4,
        current_known_incidence: 77.1,
        change_pct: 18.4,
        trend: 'steigend',
        decision_label: 'Activate',
        priority_score: 0.88,
        decision_rank: 1,
        rank: 1,
        uncertainty_summary: 'Revision risk is still material at 0.33.',
        reason_trace: {
          why: [
            'Event probability 0.81 clears the Activate threshold 0.70.',
            'Forecast confidence is strong at 0.78.',
          ],
          why_details: [
            {
              code: 'event_probability_activate_threshold',
              message: 'raw',
              params: { event_probability: 0.81, threshold: 0.7 },
            },
            {
              code: 'forecast_confidence_strong',
              message: 'raw',
              params: { forecast_confidence: 0.78 },
            },
          ],
          contributing_signals: [],
          uncertainty: ['Revision risk is still material at 0.33.'],
          uncertainty_details: [
            {
              code: 'revision_risk_material',
              message: 'raw',
              params: { revision_risk: 0.33 },
            },
          ],
          policy_overrides: [],
        },
        decision: {
          bundesland: 'BE',
          bundesland_name: 'Berlin',
          virus_typ: 'Influenza A',
          horizon_days: 7,
          signal_stage: 'activate',
          stage: 'activate',
          decision_score: 0.88,
          event_probability: 0.81,
          forecast_confidence: 0.78,
          source_freshness_score: 0.82,
          source_freshness_days: 1.9,
          source_revision_risk: 0.33,
          trend_acceleration_score: 0.76,
          cross_source_agreement_score: 0.71,
          cross_source_agreement_direction: 'up',
          usable_source_share: 0.92,
          source_coverage_score: 0.86,
          explanation_summary: 'Berlin: Activate because event probability is 0.81 and source alignment stays supportive.',
          explanation_summary_detail: {
            code: 'decision_summary',
            message: 'raw',
            params: {
              bundesland_name: 'Berlin',
              stage: 'activate',
              event_probability: 0.81,
              forecast_confidence: 0.78,
              agreement_direction: 'up',
            },
          },
          uncertainty_summary: 'Revision risk is still material at 0.33.',
          uncertainty_summary_detail: {
            code: 'uncertainty_summary',
            message: 'raw',
            params: {
              parts: ['revision_risk'],
              revision_risk: 0.33,
            },
          },
          reason_trace: {
            why: [
              'Event probability 0.81 clears the Activate threshold 0.70.',
            ],
            why_details: [
              {
                code: 'event_probability_activate_threshold',
                message: 'raw',
                params: { event_probability: 0.81, threshold: 0.7 },
              },
            ],
            contributing_signals: [],
            uncertainty: ['Revision risk is still material at 0.33.'],
            uncertainty_details: [
              {
                code: 'revision_risk_material',
                message: 'raw',
                params: { revision_risk: 0.33 },
              },
            ],
            policy_overrides: [],
          },
        },
      },
      {
        bundesland: 'SN',
        bundesland_name: 'Sachsen',
        virus_typ: 'Influenza A',
        as_of_date: '2026-03-17',
        target_date: '2026-03-24',
        target_week_start: '2026-03-23',
        target_window_days: [7, 7],
        horizon_days: 7,
        event_probability_calibrated: 0.34,
        expected_target_incidence: 56.2,
        current_known_incidence: 52.4,
        change_pct: 3.8,
        trend: 'stabil',
        decision_label: 'Watch',
        priority_score: 0.29,
        decision_rank: 2,
        rank: 2,
        uncertainty_summary: 'Forecast confidence is only 0.41.',
        reason_trace: {
          why: [
            'Event probability 0.34 stays below the rule set needed for Prepare/Activate.',
          ],
          contributing_signals: [],
          uncertainty: ['Forecast confidence is only 0.41.'],
          policy_overrides: [],
        },
        decision: {
          bundesland: 'SN',
          bundesland_name: 'Sachsen',
          virus_typ: 'Influenza A',
          horizon_days: 7,
          signal_stage: 'watch',
          stage: 'watch',
          decision_score: 0.29,
          event_probability: 0.34,
          forecast_confidence: 0.41,
          source_freshness_score: 0.7,
          source_freshness_days: 2.6,
          source_revision_risk: 0.21,
          trend_acceleration_score: 0.39,
          cross_source_agreement_score: 0.45,
          cross_source_agreement_direction: 'flat',
          usable_source_share: 0.84,
          source_coverage_score: 0.74,
          explanation_summary: 'Sachsen: Watch because probability and trend stay below the current action thresholds.',
          uncertainty_summary: 'Forecast confidence is only 0.41.',
          reason_trace: {
            why: [
              'Event probability 0.34 stays below the rule set needed for Prepare/Activate.',
            ],
            contributing_signals: [],
            uncertainty: ['Forecast confidence is only 0.41.'],
            policy_overrides: [],
          },
        },
      },
    ],
  };
}

function buildAllocation(): RegionalAllocationResponse {
  return {
    virus_typ: 'Influenza A',
    headline: 'Influenza A: Berlin jetzt aktivieren',
    horizon_days: 7,
    target_window_days: [7, 7],
    generated_at: '2026-03-17T09:01:00Z',
    summary: {
      activate_regions: 1,
      prepare_regions: 0,
      watch_regions: 1,
      total_budget_allocated: 120000,
      budget_share_total: 1,
      weekly_budget: 120000,
      spend_enabled: true,
      spend_blockers: [],
    },
    truth_layer: {
      enabled: true,
      scopes_evaluated: 2,
    },
    recommendations: [
      {
        bundesland: 'BE',
        bundesland_name: 'Berlin',
        priority_rank: 1,
        action: 'activate',
        intensity: 'high',
        recommended_activation_level: 'Activate',
        confidence: 0.79,
        suggested_budget_share: 0.46,
        suggested_budget_amount: 55200,
        suggested_budget_eur: 55200,
        channels: ['search', 'social'],
        products: ['GeloMyrtol forte'],
        spend_gate_status: 'released',
        budget_release_recommendation: 'release',
        evidence_status: 'truth_backed',
        uncertainty_summary: 'Revision risk is still material at 0.33.',
        decision_label: 'Activate',
        reason_trace: {
          why: ['Activate regions receive the highest base label weight.'],
          budget_driver_details: [
            {
              code: 'budget_driver_activate_multiplier',
              message: 'raw',
            },
          ],
          contributing_signals: [],
          uncertainty: ['Revision risk slightly reduces share.'],
          uncertainty_details: [
            {
              code: 'uncertainty_revision_risk_material',
              message: 'raw',
              params: { revision_risk: 0.33 },
            },
          ],
          policy_overrides: [],
        },
      },
      {
        bundesland: 'SN',
        bundesland_name: 'Sachsen',
        priority_rank: 2,
        action: 'watch',
        intensity: 'medium',
        recommended_activation_level: 'Watch',
        confidence: 0.42,
        suggested_budget_share: 0.08,
        suggested_budget_amount: 9600,
        suggested_budget_eur: 9600,
        channels: ['search'],
        products: ['GeloBronchial'],
        spend_gate_status: 'observe_only',
        budget_release_recommendation: 'hold',
        evidence_status: 'epidemiological_only',
        uncertainty_summary: 'Forecast confidence is only 0.41.',
        reason_trace: {
          why: ['Watch regions stay discussion-first and receive only minimal budget.'],
          contributing_signals: [],
          uncertainty: ['Confidence penalty lowers allocation.'],
          policy_overrides: [],
        },
      },
    ],
  };
}

function buildRecommendations(): RegionalCampaignRecommendationsResponse {
  return {
    virus_typ: 'Influenza A',
    headline: 'Influenza A: Berlin jetzt mit Respiratory Core Demand diskutieren',
    generated_at: '2026-03-17T09:02:00Z',
    horizon_days: 7,
    target_window_days: [7, 7],
    summary: {
      total_recommendations: 2,
      ready_recommendations: 1,
      guarded_recommendations: 0,
      observe_only_recommendations: 1,
      top_region: 'BE',
      top_product_cluster: 'Respiratory Core Demand',
    },
    recommendations: [
      {
        region: 'BE',
        region_name: 'Berlin',
        activation_level: 'Activate',
        priority_rank: 1,
        suggested_budget_share: 0.46,
        suggested_budget_amount: 55200,
        confidence: 0.79,
        evidence_class: 'truth_backed',
        recommended_product_cluster: {
          cluster_key: 'gelo_core_respiratory',
          label: 'Respiratory Core Demand',
          fit_score: 0.94,
          products: ['GeloMyrtol forte'],
        },
        recommended_keyword_cluster: {
          cluster_key: 'respiratory_relief_search',
          label: 'Respiratory Relief Search',
          fit_score: 0.91,
          keywords: ['husten schleim loesen', 'bronchitis schleim'],
        },
        recommendation_rationale: {
          why: ['Berlin stays on activate with budget share 46.00%.'],
          why_details: [
            {
              code: 'campaign_stage_budget_share',
              message: 'raw',
              params: { region_name: 'Berlin', stage: 'activate', budget_share: 0.46 },
            },
          ],
          product_fit: ['Respiratory Core Demand scores 0.94 for the available product set.'],
          product_fit_details: [
            {
              code: 'campaign_product_cluster_fit',
              message: 'raw',
              params: {
                cluster_label: 'Respiratory Core Demand',
                fit_score: 0.94,
                products: ['GeloMyrtol forte'],
              },
            },
          ],
          keyword_fit: ['Respiratory Relief Search translates the product cluster into concrete search intent.'],
          budget_notes: ['Suggested campaign budget is 55200.00 EUR.'],
          evidence_notes: ['Evidence class is truth_backed.'],
          evidence_note_details: [
            {
              code: 'campaign_evidence_class',
              message: 'raw',
              params: { evidence_class: 'truth_backed' },
            },
          ],
          guardrails: ['Spend guardrails are currently satisfied.'],
          guardrail_details: [
            {
              code: 'campaign_guardrail_ready',
              message: 'raw',
            },
          ],
        },
        channels: ['search', 'social'],
        timeline: 'sofort',
        products: ['GeloMyrtol forte'],
        keywords: ['husten schleim loesen', 'bronchitis schleim'],
        spend_guardrail_status: 'ready',
      },
      {
        region: 'SN',
        region_name: 'Sachsen',
        activation_level: 'Watch',
        priority_rank: 2,
        suggested_budget_share: 0.08,
        suggested_budget_amount: 9600,
        confidence: 0.42,
        evidence_class: 'epidemiological_only',
        recommended_product_cluster: {
          cluster_key: 'gelo_bronchial_support',
          label: 'Bronchial Recovery Support',
          fit_score: 0.71,
          products: ['GeloBronchial'],
        },
        recommended_keyword_cluster: {
          cluster_key: 'bronchial_recovery_search',
          label: 'Bronchial Recovery Search',
          fit_score: 0.69,
          keywords: ['bronchien verschleimt'],
        },
        recommendation_rationale: {
          why: ['Sachsen stays on watch with budget share 8.00%.'],
          product_fit: ['Bronchial Recovery Support scores 0.71 for the available product set.'],
          keyword_fit: ['Bronchial Recovery Search keeps the keyword logic discussion-ready.'],
          budget_notes: ['Suggested campaign budget is 9600.00 EUR.'],
          evidence_notes: ['Evidence class is epidemiological_only.'],
          guardrails: ['Recommendation stays discussion-only for now.'],
        },
        channels: ['search'],
        timeline: 'beobachten',
        products: ['GeloBronchial'],
        keywords: ['bronchien verschleimt'],
        spend_guardrail_status: 'observe_only',
      },
    ],
  };
}

const noop = () => {};

describe('OperationalDashboard', () => {
  it('renders the executive summary and connected recommendation layers', () => {
    render(
      <OperationalDashboard
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        onHorizonChange={noop}
        weeklyBudget={120000}
        forecast={buildForecast()}
        allocation={buildAllocation()}
        campaignRecommendations={buildRecommendations()}
        loading={false}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    expect(screen.getByText('Was solltest du jetzt tun?')).toBeInTheDocument();
    expect(screen.getByText('Activate Berlin für Respiratory Core Demand.')).toBeInTheDocument();
    expect(screen.getAllByText('Berlin bleibt aktuell auf Aktivieren mit 46 % Budgetanteil.').length).toBeGreaterThan(0);
    expect(screen.getByText('Stufen nach Entscheidung')).toBeInTheDocument();
    expect(screen.getByText('Empfehlungsansicht')).toBeInTheDocument();
    expect(screen.getByText(/Event-Wahrscheinlichkeit ist die Forecast-Chance/i)).toBeInTheDocument();
    expect(screen.getAllByText('Die Vorhersage liegt mit 81 % über der Schwelle für eine Aktivierung.').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Die Budget- und Freigabegrenzen sind aktuell erfüllt.').length).toBeGreaterThan(0);
  });

  it('updates the executive focus when the decision-stage filter changes', () => {
    render(
      <OperationalDashboard
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        onHorizonChange={noop}
        weeklyBudget={120000}
        forecast={buildForecast()}
        allocation={buildAllocation()}
        campaignRecommendations={buildRecommendations()}
        loading={false}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    fireEvent.change(screen.getByRole('combobox', { name: 'Entscheidungsstufe' }), {
      target: { value: 'watch' },
    });

    expect(screen.getByText('Watch Sachsen für Bronchial Recovery Support.')).toBeInTheDocument();
    expect(screen.getByText('Empfehlungsansicht')).toBeInTheDocument();
  });

  it('shows a stable empty state for no-model responses', () => {
    render(
      <OperationalDashboard
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={5}
        onHorizonChange={noop}
        weeklyBudget={120000}
        forecast={{
          virus_typ: 'Influenza A',
          status: 'no_model',
          message: 'Kein regionales Panel-Modell für Horizon 5 verfügbar.',
          horizon_days: 5,
          supported_horizon_days: [3, 5, 7],
          target_window_days: [5, 5],
          decision_summary: {
            watch_regions: 0,
            prepare_regions: 0,
            activate_regions: 0,
            avg_priority_score: 0,
            top_region: null,
            top_region_decision: null,
          },
          total_regions: 0,
          predictions: [],
          top_5: [],
          top_decisions: [],
          generated_at: '2026-03-17T09:00:00Z',
        }}
        allocation={{
          virus_typ: 'Influenza A',
          status: 'no_model',
          message: 'Keine regionalen Allocation-Empfehlungen verfügbar.',
          headline: 'Influenza A: keine regionalen Allocation-Empfehlungen verfügbar',
          summary: {
            activate_regions: 0,
            prepare_regions: 0,
            watch_regions: 0,
            total_budget_allocated: 0,
            budget_share_total: 0,
            weekly_budget: 120000,
          },
          horizon_days: 5,
          recommendations: [],
          generated_at: '2026-03-17T09:01:00Z',
        }}
        campaignRecommendations={{
          virus_typ: 'Influenza A',
          status: 'no_model',
          message: 'Keine Campaign Recommendations verfügbar.',
          headline: 'Influenza A: keine Campaign Recommendations verfügbar',
          summary: {
            total_recommendations: 0,
            ready_recommendations: 0,
            guarded_recommendations: 0,
            observe_only_recommendations: 0,
            top_region: null,
            top_product_cluster: null,
          },
          recommendations: [],
          generated_at: '2026-03-17T09:02:00Z',
        }}
        loading={false}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    expect(screen.getByText('Für diesen Scope ist noch kein regionales Modell verfügbar.')).toBeInTheDocument();
    expect(screen.getByText('Kein regionales Panel-Modell für Horizon 5 verfügbar.')).toBeInTheDocument();
    expect(screen.getByText('Unterstützte Horizonte 3 / 5 / 7')).toBeInTheDocument();
  });
});
