import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';

import PilotPage from './PilotPage';
import { usePilotSurfaceData } from '../../features/media/usePilotSurfaceData';

jest.mock('../../features/media/usePilotSurfaceData');

const mockedUsePilotSurfaceData = usePilotSurfaceData as jest.MockedFunction<typeof usePilotSurfaceData>;

function buildPilotPayload({
  virus,
  horizonDays,
  topRegion,
  secondRegion,
  campaignState = 'go',
  allocationState = 'go',
  forecastState = 'go',
  evidenceState = 'go',
  businessValidated = true,
}: {
  virus: string;
  horizonDays: number;
  topRegion: string;
  secondRegion: string;
  campaignState?: 'go' | 'watch' | 'watch_only' | 'no_data' | 'no_model';
  allocationState?: 'go' | 'watch' | 'watch_only' | 'no_data' | 'no_model' | 'no_go';
  forecastState?: 'go' | 'watch' | 'no_data' | 'no_model';
  evidenceState?: 'go' | 'watch' | 'watch_only' | 'no_data';
  businessValidated?: boolean;
}) {
  const leadRegionCode = topRegion === 'Berlin' ? 'BE' : 'BY';
  const secondRegionCode = secondRegion === 'Sachsen' ? 'SN' : 'HB';
  const leadReason = `${topRegion} is the current lead region for ${virus}.`;

  const forecast = forecastState === 'no_model'
    ? {
        virus_typ: virus,
        status: 'no_model',
        generated_at: '2026-03-17T09:00:00Z',
        horizon_days: horizonDays,
        supported_horizon_days: [3, 5, 7],
        target_window_days: [horizonDays, horizonDays],
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
      }
    : forecastState === 'no_data'
      ? {
          virus_typ: virus,
          status: 'no_data',
          message: 'No data available for this pilot scope.',
          generated_at: '2026-03-17T09:00:00Z',
          horizon_days: horizonDays,
          supported_horizon_days: [3, 5, 7],
          target_window_days: [horizonDays, horizonDays],
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
        }
      : {
          virus_typ: virus,
          status: 'trained',
          generated_at: '2026-03-17T09:00:00Z',
          horizon_days: horizonDays,
          supported_horizon_days: [3, 5, 7],
          target_window_days: [horizonDays, horizonDays],
          quality_gate: { overall_passed: forecastState === 'go' },
          decision_summary: {
            watch_regions: 1,
            prepare_regions: 0,
            activate_regions: 1,
            avg_priority_score: 0.61,
            top_region: leadRegionCode,
            top_region_decision: 'Activate',
          },
          total_regions: 2,
          predictions: [
            {
              bundesland: leadRegionCode,
              bundesland_name: topRegion,
              virus_typ: virus,
              as_of_date: '2026-03-17',
              target_week_start: '2026-03-23',
              target_window_days: [horizonDays, horizonDays],
              horizon_days: horizonDays,
              event_probability_calibrated: 0.81,
              current_known_incidence: 77.1,
              change_pct: 18.4,
              trend: 'steigend',
              decision_label: 'Activate',
              priority_score: 0.88,
              decision_rank: 1,
              rank: 1,
              uncertainty_summary: 'Revision risk is still material.',
              reason_trace: {
                why: [leadReason],
                contributing_signals: [],
                uncertainty: ['Revision risk is still material.'],
                policy_overrides: [],
              },
              decision: {
                forecast_confidence: 0.78,
                explanation_summary: leadReason,
                uncertainty_summary: 'Revision risk is still material.',
              },
            },
            {
              bundesland: secondRegionCode,
              bundesland_name: secondRegion,
              virus_typ: virus,
              as_of_date: '2026-03-17',
              target_week_start: '2026-03-23',
              target_window_days: [horizonDays, horizonDays],
              horizon_days: horizonDays,
              event_probability_calibrated: 0.34,
              current_known_incidence: 52.4,
              change_pct: 3.8,
              trend: 'stabil',
              decision_label: 'Watch',
              priority_score: 0.29,
              decision_rank: 2,
              rank: 2,
              uncertainty_summary: 'Forecast confidence is only 0.41.',
              reason_trace: {
                why: [`${secondRegion} remains below the action threshold.`],
                contributing_signals: [],
                uncertainty: ['Forecast confidence is only 0.41.'],
                policy_overrides: [],
              },
              decision: {
                forecast_confidence: 0.41,
                explanation_summary: `${secondRegion} remains below the action threshold.`,
                uncertainty_summary: 'Forecast confidence is only 0.41.',
              },
            },
          ],
          top_5: [],
          top_decisions: [],
        };

  const allocation = allocationState === 'no_model'
    ? {
        virus_typ: virus,
        status: 'no_model',
        message: 'No allocation model for this pilot scope.',
        headline: 'No allocation model',
        summary: {
          activate_regions: 0,
          prepare_regions: 0,
          watch_regions: 0,
          total_budget_allocated: 0,
          budget_share_total: 0,
          weekly_budget: 120000,
          spend_enabled: false,
          spend_blockers: [],
        },
        horizon_days: horizonDays,
        generated_at: '2026-03-17T09:01:00Z',
        recommendations: [],
      }
    : allocationState === 'no_data'
      ? {
          virus_typ: virus,
          status: 'no_data',
          message: 'No allocation data available.',
          headline: 'No allocation data',
          summary: {
            activate_regions: 0,
            prepare_regions: 0,
            watch_regions: 0,
            total_budget_allocated: 0,
            budget_share_total: 0,
            weekly_budget: 120000,
            spend_enabled: false,
            spend_blockers: [],
          },
          horizon_days: horizonDays,
          generated_at: '2026-03-17T09:01:00Z',
          recommendations: [],
        }
      : {
          virus_typ: virus,
          status: 'ready',
          headline: `${virus}: ${topRegion} jetzt aktivieren`,
          horizon_days: horizonDays,
          generated_at: '2026-03-17T09:01:00Z',
          summary: {
            activate_regions: 1,
            prepare_regions: 0,
            watch_regions: 1,
            total_budget_allocated: 120000,
            budget_share_total: 1,
            weekly_budget: 120000,
            spend_enabled: allocationState === 'go',
            spend_blockers: allocationState === 'no_go' ? ['Budget release blocked'] : [],
          },
          recommendations: [
            {
              bundesland: leadRegionCode,
              bundesland_name: topRegion,
              priority_rank: 1,
              action: 'activate',
              intensity: 'high',
              recommended_activation_level: 'Activate',
              confidence: 0.79,
              suggested_budget_share: 0.46,
              suggested_budget_amount: 55200,
              channels: ['search', 'social'],
              products: ['GeloMyrtol forte'],
              spend_gate_status: allocationState === 'no_go' ? 'blocked' : 'released',
              budget_release_recommendation: allocationState === 'go' ? 'release' : 'hold',
              reason_trace: { why: [`Allocation favors ${topRegion}.`], uncertainty: ['Revision risk slightly reduces share.'], policy_overrides: [] },
            },
            {
              bundesland: secondRegionCode,
              bundesland_name: secondRegion,
              priority_rank: 2,
              action: 'watch',
              intensity: 'medium',
              recommended_activation_level: 'Watch',
              confidence: 0.42,
              suggested_budget_share: 0.08,
              suggested_budget_amount: 9600,
              channels: ['search'],
              products: ['GeloBronchial'],
              spend_gate_status: 'observe_only',
              budget_release_recommendation: 'hold',
              reason_trace: { why: [`${secondRegion} stays in watch mode.`], uncertainty: ['Confidence penalty lowers share.'], policy_overrides: [] },
            },
          ],
        };

  const campaignRecommendations = campaignState === 'no_model'
    ? {
        virus_typ: virus,
        status: 'no_model',
        message: 'No campaign recommendation model for this scope.',
        headline: 'No campaign recommendation model',
        summary: { total_recommendations: 0, ready_recommendations: 0, guarded_recommendations: 0, observe_only_recommendations: 0, top_region: null, top_product_cluster: null },
        generated_at: '2026-03-17T09:02:00Z',
        recommendations: [],
      }
    : campaignState === 'no_data'
      ? {
          virus_typ: virus,
          status: 'no_data',
          message: 'No campaign recommendations available.',
          headline: 'No campaign recommendations',
          summary: { total_recommendations: 0, ready_recommendations: 0, guarded_recommendations: 0, observe_only_recommendations: 0, top_region: null, top_product_cluster: null },
          generated_at: '2026-03-17T09:02:00Z',
          recommendations: [],
        }
      : {
          virus_typ: virus,
          status: 'ready',
          headline: `${virus}: ${topRegion} als Kampagnenfokus`,
          generated_at: '2026-03-17T09:02:00Z',
          summary: {
            total_recommendations: 2,
            ready_recommendations: campaignState === 'watch' || campaignState === 'watch_only' ? 0 : 2,
            guarded_recommendations: campaignState === 'watch' || campaignState === 'watch_only' ? 2 : 0,
            observe_only_recommendations: 0,
            top_region: topRegion,
            top_product_cluster: 'gelo_core_respiratory',
          },
          recommendations: [
            {
              region: leadRegionCode,
              region_name: topRegion,
              activation_level: campaignState === 'watch' || campaignState === 'watch_only' ? 'Watch' : 'Activate',
              priority_rank: 1,
              suggested_budget_share: 0.46,
              suggested_budget_amount: 55200,
              confidence: 0.79,
              evidence_class: 'truth_backed',
              recommended_product_cluster: {
                cluster_key: 'gelo_core_respiratory',
                label: 'Gelo Core Respiratory',
                fit_score: 0.92,
                products: ['GeloMyrtol forte'],
              },
              recommended_keyword_cluster: {
                cluster_key: 'respiratory_relief_search',
                label: 'Respiratory Relief Search',
                fit_score: 0.88,
                keywords: ['husten', 'bronchial', 'atemwege'],
              },
              recommendation_rationale: {
                why: [`${topRegion} carries the strongest early wave signal.`],
                product_fit: ['Product fit aligns with respiratory demand.'],
                keyword_fit: ['Keyword cluster is consistent with current signal.'],
                budget_notes: ['Budget share remains concentrated on the top region.'],
                evidence_notes: ['Outcome evidence is supportive.'],
                guardrails: campaignState === 'watch' || campaignState === 'watch_only' ? ['Spend remains in review mode.'] : ['No guardrail blockers.'],
              },
              channels: ['search', 'social'],
              products: ['GeloMyrtol forte'],
              keywords: ['husten', 'bronchial'],
              spend_guardrail_status: campaignState === 'watch' || campaignState === 'watch_only' ? 'observe_only' : 'ready',
            },
            {
              region: secondRegionCode,
              region_name: secondRegion,
              activation_level: 'Watch',
              priority_rank: 2,
              suggested_budget_share: 0.08,
              suggested_budget_amount: 9600,
              confidence: 0.42,
              evidence_class: 'epidemiological_only',
              recommended_product_cluster: {
                cluster_key: 'gelo_bronchial_support',
                label: 'Gelo Bronchial Support',
                fit_score: 0.66,
                products: ['GeloBronchial'],
              },
              recommended_keyword_cluster: {
                cluster_key: 'bronchial_recovery_search',
                label: 'Bronchial Recovery Search',
                fit_score: 0.63,
                keywords: ['bronchial', 'atemwege'],
              },
              recommendation_rationale: {
                why: [`${secondRegion} remains a watch-only region.`],
                product_fit: ['Product fit is supportive but not yet strong enough.'],
                keyword_fit: ['Keyword cluster remains secondary.'],
                budget_notes: ['Only minimal budget should be discussed.'],
                evidence_notes: ['Evidence remains observational.'],
                guardrails: ['Hold until the signal strengthens.'],
              },
              channels: ['search'],
              products: ['GeloBronchial'],
              keywords: ['bronchial'],
              spend_guardrail_status: 'observe_only',
            },
          ],
        };

  const evidence = evidenceState === 'no_data'
    ? null
    : {
        virus_typ: virus,
        target_source: 'RKI_ARE',
        generated_at: '2026-03-17T09:03:00Z',
        data_freshness: {
          wastewater: '2026-03-16T08:00:00Z',
          model_lineage: '2026-03-17T06:00:00Z',
        },
        truth_coverage: {
          coverage_weeks: 28,
          latest_week: '2026-03-10',
          regions_covered: 12,
          products_covered: 4,
          outcome_fields_present: ['sales', 'orders'],
          required_fields_present: ['Media Spend', 'Sales'],
          conversion_fields_present: ['Sales'],
          trust_readiness: 'im_aufbau',
          truth_freshness_state: 'fresh',
          source_labels: ['manual_csv'],
          last_imported_at: '2026-03-16T18:00:00Z',
          latest_batch_id: 'batch-1',
          latest_source_label: 'manual_csv',
        },
        business_validation: {
          brand: 'gelo',
          operator_context: { operator: 'PEIX', product_mode: 'media', truth_partner: 'GELO' },
          truth_readiness: 'im_aufbau',
          truth_ready: true,
          coverage_weeks: 28,
          regions_with_spend: 4,
          products_with_spend: 3,
          activation_cycles: 5,
          holdout_ready: true,
          holdout_groups: ['north', 'south'],
          holdout_labeled_rows: 124,
          channels_present: ['search', 'social'],
          lift_metrics_available: true,
          outcome_signal_score: 0.68,
          outcome_confidence_pct: 72,
          expected_units_lift_enabled: true,
          expected_revenue_lift_enabled: true,
          action_class: 'budget_activation',
          validation_status: businessValidated ? 'passed_holdout_validation' : 'pending_holdout_validation',
          decision_scope: businessValidated ? 'validated_budget_activation' : 'decision_support_only',
          validated_for_budget_activation: businessValidated,
          evidence_tier: businessValidated ? 'commercially_validated' : 'holdout_ready',
          message: businessValidated ? 'Commercial validation is ready.' : 'Commercial validation is still in review.',
          guidance: businessValidated ? 'Pilot can be discussed with budget activation language.' : 'Keep the scope in review mode.',
          validation_requirements: {
            min_coverage_weeks: 26,
            min_activation_cycles: 4,
            requires_explicit_holdout_design: true,
            requires_validated_lift_metrics: true,
          },
        },
        forecast_monitoring: {
          virus_typ: virus,
          target_source: 'RKI_ARE',
          monitoring_status: evidenceState === 'go' ? 'healthy' : 'warning',
          forecast_readiness: evidenceState === 'go' ? 'GO' : 'WATCH',
          drift_status: 'ok',
          freshness_status: 'fresh',
          issue_date: '2026-03-17',
          model_version: 'pilot-model-v1',
          event_forecast: {
            event_probability: 0.81,
            confidence: 0.78,
            calibration_passed: true,
          },
          latest_accuracy: {
            computed_at: '2026-03-17T08:00:00Z',
            samples: 84,
            mape: 0.12,
            rmse: 0.38,
            correlation: 0.72,
            drift_detected: false,
            freshness_status: 'fresh',
          },
          latest_backtest: {
            run_id: 'backtest-1',
            created_at: '2026-03-16T08:00:00Z',
            target_source: 'RKI_ARE',
            freshness_status: 'fresh',
            quality_gate: { overall_passed: evidenceState === 'go' },
            interval_coverage: { coverage_80_pct: 91.2 },
            event_calibration: { brier_score: 0.026, ece: 0.023 },
            timing_metrics: { median_lead_days: 4.1 },
            lead_lag: { effective_lead_days: 4.2 },
            improvement_vs_baselines: { mae_vs_persistence_pct: -8.3, mae_vs_seasonal_pct: -6.1 },
          },
          alerts: evidenceState === 'go' ? [] : ['Forecast readiness remains in watch mode.'],
        },
        model_lineage: {
          virus_typ: virus,
          model_family: 'regional_stack',
          base_estimators: ['hw', 'ridge', 'prophet'],
          meta_learner: 'xgboost',
          model_version: 'pilot-model-v1',
          trained_at: '2026-03-17T06:00:00Z',
          feature_set_version: 'rsv_ranking_v1',
          feature_names: ['momentum', 'agreement', 'trend'],
          drift_state: 'ok',
          coverage_limits: [],
          latest_accuracy: {
            computed_at: '2026-03-17T08:00:00Z',
            samples: 84,
            mape: 0.12,
            rmse: 0.38,
            correlation: 0.72,
          },
          latest_forecast_created_at: '2026-03-17T09:00:00Z',
        },
        known_limits: ['No causal uplift model is used in this view.'],
        proxy_validation: null,
        truth_validation: null,
        truth_validation_legacy: null,
        recent_runs: [
          { mode: 'forecast', status: evidenceState === 'go' ? 'GO' : 'WATCH' },
          { mode: 'allocation', status: allocationState === 'go' ? 'GO' : allocationState === 'no_go' ? 'NO_GO' : 'WATCH' },
        ],
      };

  const pilotReporting = campaignState === 'no_data' || forecastState === 'no_data'
    ? {
        brand: 'gelo',
        generated_at: '2026-03-17T09:04:00Z',
        reporting_window: {
          start: '2026-01-01',
          end: '2026-03-17',
          lookback_weeks: 26,
          include_draft: false,
        },
        summary: {
          total_recommendations: 0,
          activated_recommendations: 0,
          region_scopes: 0,
          regions_covered: 0,
          products_covered: 0,
          comparisons_with_evidence: 0,
          supportive_comparisons: 0,
        },
        pilot_kpi_summary: {
          hit_rate: { value: null, assessed: 0, supportive: 0 },
          early_warning_lead_time_days: { average: null, median: null, assessed: 0 },
          share_of_correct_regional_prioritizations: { value: null, assessed_high_priority: 0, supportive_or_directional: 0 },
          agreement_with_outcome_signals: { value: null, assessed: 0, agreeing_scopes: 0 },
        },
        recommendation_history: [],
        activation_history: [],
        region_evidence_view: [],
        before_after_comparison: [],
        methodology: { version: 'pilot_reporting_v1' },
      }
    : {
        brand: 'gelo',
        generated_at: '2026-03-17T09:04:00Z',
        reporting_window: {
          start: '2026-01-01',
          end: '2026-03-17',
          lookback_weeks: 26,
          include_draft: false,
        },
        summary: {
          total_recommendations: 2,
          activated_recommendations: campaignState === 'go' ? 1 : 0,
          region_scopes: 2,
          regions_covered: 2,
          products_covered: 2,
          comparisons_with_evidence: 2,
          supportive_comparisons: 1,
        },
        pilot_kpi_summary: {
          hit_rate: { value: campaignState === 'go' ? 0.6 : 0.35, assessed: 2, supportive: campaignState === 'go' ? 1 : 0 },
          early_warning_lead_time_days: { average: 4.2, median: 4.2, assessed: 2 },
          share_of_correct_regional_prioritizations: { value: campaignState === 'go' ? 0.5 : 0.25, assessed_high_priority: 2, supportive_or_directional: campaignState === 'go' ? 1 : 0, priority_threshold: 0.55 },
          agreement_with_outcome_signals: { value: campaignState === 'go' ? 0.67 : 0.33, assessed: 2, agreeing_scopes: campaignState === 'go' ? 1 : 0 },
        },
        recommendation_history: [
          {
            opportunity_id: 'opp-1',
            created_at: '2026-03-08T09:00:00Z',
            updated_at: '2026-03-09T09:00:00Z',
            current_status: campaignState === 'go' ? 'APPROVED' : 'READY',
            brand: 'gelo',
            product: 'GeloMyrtol forte',
            region_codes: [leadRegionCode],
            region_names: [topRegion],
            priority_score: 0.84,
            signal_score: 0.82,
            signal_confidence_pct: 78,
            event_probability_pct: 81,
            activation_window: { start: '2026-03-10', end: '2026-03-17' },
            lead_time_days: 4,
            playbook_key: 'respiratory_core',
            playbook_title: 'Respiratory Core',
            trigger_event: 'wave',
            recommendation_summary: `Lead recommendation for ${topRegion}.`,
            mapping_status: 'mapped',
            guardrail_notes: ['No blocker.'],
            status_history: [],
          },
        ],
        activation_history: campaignState === 'go' ? [
          {
            opportunity_id: 'opp-1',
            current_status: 'APPROVED',
            approved_at: '2026-03-09T10:00:00Z',
            activated_at: '2026-03-10T09:00:00Z',
            activation_window: { start: '2026-03-10', end: '2026-03-17' },
            lead_time_days: 4,
            product: 'GeloMyrtol forte',
            region_codes: [leadRegionCode],
            region_names: [topRegion],
            weekly_budget_eur: 120000,
            total_flight_budget_eur: 840000,
            primary_kpi: 'sales',
            campaign_name: 'Pilot wave activation',
          },
        ] : [],
        region_evidence_view: [
          {
            region_code: leadRegionCode,
            region_name: topRegion,
            recommendations: 5,
            activations: campaignState === 'go' ? 2 : 0,
            avg_priority_score: 0.81,
            avg_lead_time_days: 4.2,
            avg_after_delta_pct: 12.4,
            hit_rate: campaignState === 'go' ? 0.75 : 0.2,
            agreement_with_outcome_signals: campaignState === 'go' ? 0.8 : 0.25,
            dominant_evidence_status: campaignState === 'go' ? 'supportive' : 'observational',
            top_products: ['GeloMyrtol forte'],
            evidence_status_counts: { supportive: campaignState === 'go' ? 3 : 1 },
          },
          {
            region_code: secondRegionCode,
            region_name: secondRegion,
            recommendations: 2,
            activations: 0,
            avg_priority_score: 0.44,
            avg_lead_time_days: 2.8,
            avg_after_delta_pct: 3.2,
            hit_rate: 0.2,
            agreement_with_outcome_signals: 0.2,
            dominant_evidence_status: 'observational',
            top_products: ['GeloBronchial'],
            evidence_status_counts: { observational: 2 },
          },
        ],
        before_after_comparison: [
          {
            comparison_id: 'cmp-1',
            region_code: leadRegionCode,
            region_name: topRegion,
            product: 'GeloMyrtol forte',
            primary_metric: 'sales',
            delta_pct: campaignState === 'go' ? 12.4 : -1.2,
            outcome_support_status: campaignState === 'go' ? 'supportive' : 'not_supportive',
          },
          {
            comparison_id: 'cmp-2',
            region_code: secondRegionCode,
            region_name: secondRegion,
            product: 'GeloBronchial',
            primary_metric: 'orders',
            delta_pct: 3.2,
            outcome_support_status: 'mixed',
          },
        ],
        methodology: {
          version: 'pilot_reporting_v1',
          recommendation_history_source: 'MarketingOpportunity + AuditLog',
          outcome_source_preference: 'OutcomeObservation',
          before_after_definition: 'Matched pre-window vs active/after window using the configured activation range.',
          strict_hit_definition: 'A hit requires a positive primary KPI delta and at least moderate signal/outcome agreement.',
        },
      };

  return {
    forecast,
    allocation,
    campaignRecommendations,
    evidence,
    pilotReporting,
    loading: false,
  };
}

describe('PilotPage', () => {
  beforeEach(() => {
    mockedUsePilotSurfaceData.mockReset();
  });

  it('renders the customer-facing summary, recommendations, and evidence sections', () => {
    mockedUsePilotSurfaceData.mockImplementation(() => buildPilotPayload({
      virus: 'RSV A',
      horizonDays: 7,
      topRegion: 'Berlin',
      secondRegion: 'Sachsen',
    }) as any);

    render(<PilotPage />);

    expect(screen.getByRole('heading', { name: 'What should we do now?' })).toBeInTheDocument();
    expect(screen.getByText('Operational Recommendations')).toBeInTheDocument();
    expect(screen.getByText('Pilot Evidence / Readiness')).toBeInTheDocument();
    expect(screen.getByText('Lead Region')).toBeInTheDocument();
    expect(screen.getByText('Berlin', { selector: '.campaign-confidence-chip' })).toBeInTheDocument();
    expect(screen.getByText(/Hit rate/i)).toBeInTheDocument();
  });

  it('updates virus, horizon, scope, and stage filters without changing the data contract', () => {
    mockedUsePilotSurfaceData.mockImplementation(({ virus, horizonDays }) => {
      if (virus === 'Influenza A' && horizonDays === 5) {
        return buildPilotPayload({
          virus,
          horizonDays,
          topRegion: 'Bayern',
          secondRegion: 'Bremen',
        }) as any;
      }
      return buildPilotPayload({
        virus,
        horizonDays,
        topRegion: 'Berlin',
        secondRegion: 'Sachsen',
      }) as any;
    });

    render(<PilotPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Forecast' }));
    const operationalSection = screen.getByText('Operational Recommendations').closest('section');
    expect(operationalSection).not.toBeNull();
    expect(within(operationalSection as HTMLElement).getByText('Berlin')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Watch' }));
    expect(within(operationalSection as HTMLElement).getByText('Sachsen')).toBeInTheDocument();
    expect(within(operationalSection as HTMLElement).queryByText('Berlin')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Activate' }));
    fireEvent.click(screen.getByRole('button', { name: 'Influenza A' }));
    fireEvent.click(screen.getByRole('button', { name: '5 Tage' }));
    expect(within(operationalSection as HTMLElement).getByText('Bayern')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Evidence' }));
    expect(screen.getByText('Focus lens: Evidence')).toBeInTheDocument();
    expect(screen.getByText('Top Evidenz-Treiber')).toBeInTheDocument();
  });

  it('shows a no_model empty state when no model is available', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildPilotPayload({
      virus: 'RSV A',
      horizonDays: 7,
      topRegion: 'Berlin',
      secondRegion: 'Sachsen',
      forecastState: 'no_model',
      allocationState: 'no_model',
      campaignState: 'no_model',
    }) as any);

    render(<PilotPage />);

    expect(screen.getByText('Für diesen Scope liegt noch kein belastbares Modell vor.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Forecast ansehen' })).toBeInTheDocument();
  });

  it('shows a no_data empty state when the data layer is empty', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildPilotPayload({
      virus: 'RSV A',
      horizonDays: 7,
      topRegion: 'Berlin',
      secondRegion: 'Sachsen',
      forecastState: 'no_data',
      allocationState: 'no_data',
      campaignState: 'no_data',
      evidenceState: 'no_data',
    }) as any);

    render(<PilotPage />);

    expect(screen.getByText('Das Modell ist da, aber die Datenlage reicht noch nicht aus.')).toBeInTheDocument();
    const banner = screen.getByText('Das Modell ist da, aber die Datenlage reicht noch nicht aus.').closest('section');
    expect(banner).not.toBeNull();
    expect(within(banner as HTMLElement).getByText('NO DATA')).toBeInTheDocument();
  });

  it('shows a watch_only empty state when the scope should remain observational', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildPilotPayload({
      virus: 'RSV A',
      horizonDays: 7,
      topRegion: 'Berlin',
      secondRegion: 'Sachsen',
      campaignState: 'watch_only',
      allocationState: 'watch_only',
      forecastState: 'watch',
      evidenceState: 'watch_only',
      businessValidated: false,
    }) as any);

    render(<PilotPage />);

    expect(screen.getByText('Die Lage ist interessant, aber noch beobachtungsnah.')).toBeInTheDocument();
    const banner = screen.getByText('Die Lage ist interessant, aber noch beobachtungsnah.').closest('section');
    expect(banner).not.toBeNull();
    expect(within(banner as HTMLElement).getByText('WATCH')).toBeInTheDocument();
  });

  it('shows a no_go empty state when spend remains blocked', () => {
    mockedUsePilotSurfaceData.mockReturnValue(buildPilotPayload({
      virus: 'RSV A',
      horizonDays: 7,
      topRegion: 'Berlin',
      secondRegion: 'Sachsen',
      allocationState: 'no_go',
      campaignState: 'watch_only',
      forecastState: 'watch',
      evidenceState: 'watch_only',
      businessValidated: false,
    }) as any);

    render(<PilotPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Allocation' }));

    expect(screen.getByText('Der Scope bleibt bewusst gesperrt.')).toBeInTheDocument();
    const banner = screen.getByText('Der Scope bleibt bewusst gesperrt.').closest('section');
    expect(banner).not.toBeNull();
    expect(within(banner as HTMLElement).getByText('NO GO')).toBeInTheDocument();
  });
});
