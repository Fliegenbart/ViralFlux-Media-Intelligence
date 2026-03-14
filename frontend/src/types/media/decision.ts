import { BacktestResponse } from './backtest';
import { BusinessValidationSummary, OutcomeLearningSummary, TruthCoverage } from './evidence';
import { RecommendationCard } from './recommendations';
import { MetricContract } from './shared';

export interface WeeklyDecisionRegion {
  code?: string;
  name?: string;
  signal_score?: number;
  trend?: string;
}

export interface WeeklyDecision {
  decision_state: 'GO' | 'WATCH' | string;
  action_stage?: 'activate' | 'prepare' | string;
  decision_mode?: 'epidemic_wave' | 'mixed' | 'supply_window' | string;
  decision_mode_label?: string;
  decision_mode_reason?: string;
  decision_window?: {
    start?: string | null;
    horizon_days?: number | null;
  };
  recommended_action?: string | null;
  top_regions: WeeklyDecisionRegion[];
  top_products?: string[];
  budget_shift?: number | null;
  why_now: string[];
  risk_flags: string[];
  freshness_state?: string;
  proxy_state?: string;
  forecast_state?: string;
  truth_state?: string;
  truth_freshness_state?: string;
  truth_last_imported_at?: string | null;
  truth_latest_batch_id?: string | null;
  truth_risk_flag?: string | null;
  truth_gate?: {
    passed: boolean;
    state?: string;
    learning_state?: string;
    message?: string | null;
    guidance?: string | null;
    field_contracts?: Record<string, MetricContract>;
  };
  business_gate?: BusinessValidationSummary;
  business_readiness?: string;
  business_evidence_tier?: string;
  operator_context?: BusinessValidationSummary['operator_context'];
  learning_state?: string;
  outcome_learning_summary?: OutcomeLearningSummary;
  forecast_quality?: Record<string, unknown>;
  event_forecast?: {
    event_probability?: number | null;
    confidence?: number | null;
    alert_level?: string;
    lead_time_days?: number | null;
    probability_band?: string;
  };
  signal_stack_summary?: {
    peix_epi_score?: number;
    national_band?: string;
    top_drivers?: Array<{ label: string; strength_pct: number }>;
    context_signals?: Record<string, { value: number; weight: number; contribution: number }>;
    driver_groups?: Record<string, { label: string; contribution: number }>;
    decision_mode?: 'epidemic_wave' | 'mixed' | 'supply_window' | string;
    decision_mode_label?: string;
    decision_mode_reason?: string;
    math_stack?: {
      base_models?: string[];
      meta_learner?: string;
      feature_families?: string[];
    };
  };
  field_contracts?: Record<string, MetricContract>;
}

export interface MediaDecisionResponse {
  virus_typ: string;
  target_source: string;
  generated_at: string;
  weekly_decision: WeeklyDecision;
  top_recommendations: RecommendationCard[];
  campaign_summary?: {
    visible_cards?: number;
    hidden_backlog_cards?: number;
  };
  wave_run_id?: string | null;
  backtest_summary?: {
    latest_market?: BacktestResponse | null;
    latest_customer?: BacktestResponse | null;
  };
  model_lineage?: import('./evidence').ModelLineage;
  truth_coverage?: TruthCoverage;
  business_validation?: BusinessValidationSummary;
  operator_context?: BusinessValidationSummary['operator_context'];
}
