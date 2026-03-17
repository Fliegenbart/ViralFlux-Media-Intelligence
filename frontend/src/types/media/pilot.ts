import { BacktestResponse } from './backtest';
import { BusinessValidationSummary, TruthCoverage } from './evidence';
import { RegionalAllocationResponse, RegionalCampaignRecommendationsResponse, RegionalForecastResponse } from './regional';

export interface PilotReportingWindow {
  start?: string | null;
  end?: string | null;
  lookback_weeks?: number;
  region_code?: string | null;
  product?: string | null;
  include_draft?: boolean;
}

export interface PilotReportingSummaryBlock {
  total_recommendations?: number;
  activated_recommendations?: number;
  region_scopes?: number;
  regions_covered?: number;
  products_covered?: number;
  comparisons_with_evidence?: number;
  supportive_comparisons?: number;
}

export interface PilotReportingMetricBlock {
  value?: number | null;
  average?: number | null;
  median?: number | null;
  supportive?: number;
  assessed?: number;
  supportive_or_directional?: number;
  assessed_high_priority?: number;
  priority_threshold?: number | null;
  agreeing_scopes?: number;
  definition?: string;
}

export interface PilotRecommendationStatusChange {
  timestamp?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  source?: string | null;
  audit_action?: string | null;
  audit_reason?: string | null;
}

export interface PilotRecommendationHistoryItem {
  opportunity_id?: string | number | null;
  created_at?: string | null;
  updated_at?: string | null;
  current_status?: string | null;
  status_history?: PilotRecommendationStatusChange[];
  brand?: string | null;
  product?: string | null;
  region_codes?: string[];
  region_names?: string[];
  priority_score?: number | null;
  signal_score?: number | null;
  signal_confidence_pct?: number | null;
  event_probability_pct?: number | null;
  activation_window?: {
    start?: string | null;
    end?: string | null;
  };
  lead_time_days?: number | null;
  playbook_key?: string | null;
  playbook_title?: string | null;
  trigger_event?: string | null;
  recommendation_summary?: string | null;
  mapping_status?: string | null;
  guardrail_notes?: string[];
}

export interface PilotActivationHistoryItem {
  opportunity_id?: string | number | null;
  current_status?: string | null;
  approved_at?: string | null;
  activated_at?: string | null;
  activation_window?: {
    start?: string | null;
    end?: string | null;
  };
  lead_time_days?: number | null;
  product?: string | null;
  region_codes?: string[];
  region_names?: string[];
  weekly_budget_eur?: number | null;
  total_flight_budget_eur?: number | null;
  primary_kpi?: string | null;
  campaign_name?: string | null;
}

export interface PilotTruthAssessment {
  evidence_status?: string | null;
  evidence_confidence?: number | null;
  outcome_readiness?: Record<string, unknown>;
  signal_outcome_agreement?: {
    status?: string | null;
    score?: number | null;
    signal_present?: boolean;
    historical_response_observed?: boolean;
    signal_confidence?: number | null;
    outcome_support_score?: number | null;
    outcome_confidence?: number | null;
    notes?: string[];
  };
  commercial_gate?: {
    budget_decision_allowed?: boolean;
    decision_scope?: string | null;
    message?: string | null;
  };
}

export interface PilotBeforeAfterComparison {
  comparison_id?: string | null;
  opportunity_id?: string | number | null;
  region_code?: string | null;
  region_name?: string | null;
  product?: string | null;
  current_status?: string | null;
  is_activated?: boolean;
  priority_score?: number | null;
  lead_time_days?: number | null;
  before_window?: { start?: string | null; end?: string | null };
  after_window?: { start?: string | null; end?: string | null };
  before?: {
    source_mode?: string;
    observation_count?: number;
    coverage_weeks?: number;
    metrics?: Record<string, number>;
  };
  after?: {
    source_mode?: string;
    observation_count?: number;
    coverage_weeks?: number;
    metrics?: Record<string, number>;
  };
  primary_metric?: string | null;
  before_value?: number | null;
  after_value?: number | null;
  delta_absolute?: number | null;
  delta_pct?: number | null;
  outcome_support_status?: string | null;
  truth_assessment?: PilotTruthAssessment;
}

export interface PilotRegionEvidenceItem {
  region_code?: string | null;
  region_name?: string | null;
  recommendations?: number;
  activations?: number;
  avg_priority_score?: number | null;
  avg_lead_time_days?: number | null;
  avg_after_delta_pct?: number | null;
  hit_rate?: number | null;
  agreement_with_outcome_signals?: number | null;
  dominant_evidence_status?: string | null;
  top_products?: string[];
  evidence_status_counts?: Record<string, number>;
}

export interface PilotReportingResponse {
  brand?: string;
  generated_at?: string;
  reporting_window?: PilotReportingWindow;
  summary?: PilotReportingSummaryBlock;
  pilot_kpi_summary?: {
    hit_rate?: PilotReportingMetricBlock;
    early_warning_lead_time_days?: PilotReportingMetricBlock;
    share_of_correct_regional_prioritizations?: PilotReportingMetricBlock;
    agreement_with_outcome_signals?: PilotReportingMetricBlock;
  };
  recommendation_history?: PilotRecommendationHistoryItem[];
  activation_history?: PilotActivationHistoryItem[];
  region_evidence_view?: PilotRegionEvidenceItem[];
  before_after_comparison?: PilotBeforeAfterComparison[];
  methodology?: {
    version?: string;
    recommendation_history_source?: string;
    outcome_source_preference?: string;
    before_after_definition?: string;
    strict_hit_definition?: string;
  };
}
