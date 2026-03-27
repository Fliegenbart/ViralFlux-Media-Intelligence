import { StructuredReasonItem } from './shared';

export type RegionalDecisionStage = 'Activate' | 'Prepare' | 'Watch' | string;

export interface RegionalDecisionComponentScore {
  key: string;
  value: number;
  score: number;
  weight: number;
  weighted_contribution: number;
  status: string;
  detail: string;
}

export interface RegionalDecisionReasonTrace {
  why: string[];
  why_details?: StructuredReasonItem[];
  contributing_signals: RegionalDecisionComponentScore[];
  uncertainty: string[];
  uncertainty_details?: StructuredReasonItem[];
  policy_overrides: string[];
  policy_override_details?: StructuredReasonItem[];
  budget_drivers?: string[];
  budget_driver_details?: StructuredReasonItem[];
  blockers?: string[];
  blocker_details?: StructuredReasonItem[];
}

export interface RegionalDecisionPayload {
  bundesland: string;
  bundesland_name: string;
  virus_typ: string;
  horizon_days: number;
  signal_stage: string;
  stage: string;
  decision_score: number;
  event_probability: number;
  forecast_confidence: number;
  source_freshness_score: number;
  source_freshness_days: number;
  source_revision_risk: number;
  trend_acceleration_score: number;
  cross_source_agreement_score: number;
  cross_source_agreement_direction: string;
  usable_source_share: number;
  source_coverage_score: number;
  explanation_summary: string;
  explanation_summary_detail?: StructuredReasonItem | null;
  uncertainty_summary: string;
  uncertainty_summary_detail?: StructuredReasonItem | null;
  components?: Record<string, number>;
  thresholds?: Record<string, number>;
  reason_trace?: RegionalDecisionReasonTrace;
  metadata?: Record<string, unknown>;
}

export interface RegionalForecastPrediction {
  bundesland: string;
  bundesland_name: string;
  virus_typ: string;
  as_of_date: string;
  target_date?: string;
  target_week_start: string;
  target_window_days: number[];
  horizon_days: number;
  event_probability_calibrated: number;
  expected_next_week_incidence?: number;
  expected_target_incidence?: number;
  prediction_interval?: {
    lower: number;
    upper: number;
  };
  current_known_incidence: number;
  seasonal_baseline?: number;
  seasonal_mad?: number;
  change_pct: number;
  quality_gate?: Record<string, unknown>;
  business_gate?: Record<string, unknown>;
  evidence_tier?: string;
  rollout_mode?: string;
  activation_policy?: string;
  signal_bundle_version?: string;
  model_version?: string;
  calibration_version?: string;
  point_in_time_snapshot?: Record<string, unknown>;
  source_coverage?: Record<string, unknown>;
  source_coverage_scope?: string | null;
  action_threshold?: number;
  activation_candidate?: boolean;
  current_load?: number;
  predicted_load?: number;
  trend: string;
  data_points?: number;
  last_data_date?: string;
  pollen_context_score?: number;
  state_population_millions?: number;
  decision?: RegionalDecisionPayload;
  decision_label?: RegionalDecisionStage;
  priority_score?: number;
  reason_trace?: RegionalDecisionReasonTrace;
  uncertainty_summary?: string;
  decision_rank?: number | null;
  rank?: number;
}

export interface RegionalDecisionSummary {
  watch_regions: number;
  prepare_regions: number;
  activate_regions: number;
  avg_priority_score: number;
  top_region: string | null;
  top_region_decision: string | null;
}

export interface RegionalBacktestTimelinePoint {
  fold?: number;
  virus_typ?: string;
  bundesland: string;
  bundesland_name?: string;
  as_of_date: string;
  target_date: string;
  target_week_start?: string;
  horizon_days: number;
  event_label?: number;
  event_probability_calibrated?: number;
  current_known_incidence: number;
  next_week_incidence?: number;
  expected_next_week_incidence?: number;
  expected_target_incidence: number;
  prediction_interval_lower?: number;
  prediction_interval_upper?: number;
  activated?: boolean;
}

export interface RegionalBacktestResponse {
  bundesland: string;
  bundesland_name: string;
  horizon_days?: number;
  total_windows?: number;
  metrics?: Record<string, number>;
  timeline?: RegionalBacktestTimelinePoint[];
  error?: string;
}

export interface RegionalForecastResponse {
  virus_typ: string;
  status?: string;
  message?: string;
  as_of_date?: string;
  horizon_days: number;
  supported_horizon_days?: number[];
  target_window_days: number[];
  quality_gate?: Record<string, unknown>;
  business_gate?: Record<string, unknown>;
  evidence_tier?: string;
  rollout_mode?: string;
  activation_policy?: string;
  signal_bundle_version?: string;
  model_version?: string;
  calibration_version?: string;
  artifact_transition_mode?: string | null;
  point_in_time_snapshot?: Record<string, unknown>;
  source_coverage?: Record<string, unknown>;
  source_coverage_scope?: string | null;
  action_threshold?: number;
  decision_policy_version?: string;
  decision_summary: RegionalDecisionSummary;
  total_regions: number;
  predictions: RegionalForecastPrediction[];
  top_5: RegionalForecastPrediction[];
  top_decisions: RegionalForecastPrediction[];
  generated_at: string;
}

export interface RegionalTruthScope {
  brand?: string;
  region_code?: string | null;
  product?: string | null;
  window_start?: string;
  window_end?: string;
}

export interface RegionalOutcomeReadiness {
  status?: string;
  score?: number;
  coverage_weeks?: number;
  notes?: string[];
  metrics_present?: string[];
  regions_present?: number;
  products_present?: number;
  spend_windows?: number;
  response_windows?: number;
}

export interface RegionalSignalOutcomeAgreement {
  status?: string;
  score?: number | null;
  signal_present?: boolean;
  historical_response_observed?: boolean;
  signal_confidence?: number | null;
  outcome_support_score?: number | null;
  outcome_confidence?: number | null;
  notes?: string[];
}

export interface RegionalTruthAssessment {
  scope?: RegionalTruthScope;
  outcome_readiness?: RegionalOutcomeReadiness;
  signal_outcome_agreement?: RegionalSignalOutcomeAgreement;
  holdout_eligibility?: {
    eligible?: boolean;
    ready?: boolean;
    holdout_groups?: string[];
    reason?: string;
  };
  evidence_status?: string;
  evidence_confidence?: number;
  commercial_gate?: {
    budget_decision_allowed?: boolean;
    decision_scope?: string;
    message?: string;
  };
  metadata?: Record<string, unknown>;
}

export interface RegionalAllocationRecommendation {
  bundesland: string;
  bundesland_name: string;
  rank?: number;
  decision_rank?: number | null;
  priority_rank?: number | null;
  action: string;
  intensity: string;
  recommended_activation_level: RegionalDecisionStage;
  spend_readiness?: string;
  event_probability?: number;
  decision_label?: RegionalDecisionStage;
  priority_score?: number;
  allocation_score?: number;
  confidence?: number;
  reason_trace?: RegionalDecisionReasonTrace | Record<string, unknown> | string[] | string;
  allocation_reason_trace?: RegionalDecisionReasonTrace | Record<string, unknown> | string[] | string;
  uncertainty_summary?: string;
  decision?: RegionalDecisionPayload;
  change_pct?: number;
  trend?: string;
  budget_share?: number;
  suggested_budget_share: number;
  budget_eur?: number;
  suggested_budget_eur?: number;
  suggested_budget_amount: number;
  channels: string[];
  products: string[];
  product_clusters?: Array<Record<string, unknown>>;
  keyword_clusters?: Array<Record<string, unknown>>;
  timeline?: string;
  current_load?: number;
  predicted_load?: number;
  quality_gate?: Record<string, unknown>;
  business_gate?: Record<string, unknown>;
  evidence_tier?: string;
  rollout_mode?: string;
  activation_policy?: string;
  activation_threshold?: number;
  allocation_policy_version?: string;
  as_of_date?: string;
  target_week_start?: string;
  truth_layer_enabled?: boolean;
  truth_scope?: RegionalTruthScope;
  outcome_readiness?: RegionalOutcomeReadiness;
  evidence_status?: string;
  evidence_confidence?: number;
  signal_outcome_agreement?: RegionalSignalOutcomeAgreement;
  spend_gate_status?: string;
  budget_release_recommendation?: string;
  commercial_gate?: Record<string, unknown>;
  truth_assessments?: RegionalTruthAssessment[];
}

export interface RegionalAllocationSummary {
  activate_regions: number;
  prepare_regions: number;
  watch_regions: number;
  total_budget_allocated: number;
  budget_share_total: number;
  weekly_budget: number;
  quality_gate?: Record<string, unknown>;
  business_gate?: Record<string, unknown>;
  evidence_tier?: string;
  rollout_mode?: string;
  activation_policy?: string;
  allocation_policy_version?: string;
  spend_enabled?: boolean;
  spend_blockers?: string[];
}

export interface RegionalTruthLayerRollup {
  enabled: boolean;
  lookback_weeks?: number;
  scopes_evaluated?: number;
  evidence_status_counts?: Record<string, number>;
  spend_gate_status_counts?: Record<string, number>;
  budget_release_recommendation_counts?: Record<string, number>;
}

export interface RegionalAllocationResponse {
  virus_typ: string;
  status?: string;
  message?: string;
  headline: string;
  summary: RegionalAllocationSummary;
  allocation_config?: Record<string, unknown>;
  horizon_days: number;
  supported_horizon_days?: number[];
  target_window_days?: number[];
  truth_layer?: RegionalTruthLayerRollup;
  generated_at: string;
  recommendations: RegionalAllocationRecommendation[];
}

export interface CampaignClusterSelection {
  cluster_key: string;
  label: string;
  fit_score: number;
  products?: string[];
  keywords?: string[];
  metadata?: Record<string, unknown>;
}

export interface CampaignRecommendationRationale {
  why: string[];
  why_details?: StructuredReasonItem[];
  product_fit: string[];
  product_fit_details?: StructuredReasonItem[];
  keyword_fit: string[];
  keyword_fit_details?: StructuredReasonItem[];
  budget_notes: string[];
  budget_note_details?: StructuredReasonItem[];
  evidence_notes: string[];
  evidence_note_details?: StructuredReasonItem[];
  guardrails: string[];
  guardrail_details?: StructuredReasonItem[];
}

export interface RegionalCampaignRecommendation {
  region: string;
  region_name: string;
  bundesland?: string;
  bundesland_name?: string;
  virus_typ?: string;
  activation_level: RegionalDecisionStage;
  priority_rank: number;
  suggested_budget_share: number;
  suggested_budget_amount: number;
  confidence: number;
  evidence_class: string;
  recommended_product_cluster: CampaignClusterSelection;
  recommended_keyword_cluster: CampaignClusterSelection;
  recommendation_rationale: CampaignRecommendationRationale;
  channels: string[];
  timeline?: string | null;
  products: string[];
  keywords: string[];
  spend_guardrail_status: string;
  metadata?: Record<string, unknown>;
}

export interface RegionalCampaignRecommendationSummary {
  total_recommendations: number;
  ready_recommendations: number;
  guarded_recommendations: number;
  observe_only_recommendations: number;
  top_region: string | null;
  top_product_cluster: string | null;
  campaign_recommendation_policy_version?: string;
}

export interface RegionalCampaignRecommendationsResponse {
  virus_typ: string;
  status?: string;
  message?: string;
  headline: string;
  summary: RegionalCampaignRecommendationSummary;
  config?: Record<string, unknown>;
  allocation_summary?: RegionalAllocationSummary;
  truth_layer?: RegionalTruthLayerRollup;
  generated_at: string;
  horizon_days?: number;
  target_window_days?: number[];
  recommendations: RegionalCampaignRecommendation[];
}
