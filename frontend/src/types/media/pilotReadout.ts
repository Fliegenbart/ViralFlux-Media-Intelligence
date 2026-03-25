import { StructuredReasonItem } from './shared';

export type PilotSurfaceScope = 'forecast' | 'allocation' | 'recommendation' | 'evidence';
export type PilotSurfaceStageFilter = 'ALL' | 'Activate' | 'Prepare' | 'Watch';
export type PilotReadoutStatus = 'GO' | 'WATCH' | 'NO_GO';

export interface PilotReadoutRegion {
  region_code?: string;
  region_name?: string;
  decision_stage?: string;
  forecast_scope_readiness?: PilotReadoutStatus;
  priority_rank?: number | null;
  priority_score?: number | null;
  event_probability?: number | null;
  allocation_score?: number | null;
  confidence?: number | null;
  budget_share?: number | null;
  budget_amount_eur?: number | null;
  recommended_product?: string | null;
  recommended_keywords?: string | null;
  campaign_recommendation?: string | null;
  channels?: string[];
  uncertainty_summary?: string | null;
  uncertainty_summary_detail?: StructuredReasonItem | null;
  reason_trace?: string[];
  reason_trace_details?: StructuredReasonItem[];
  quality_gate?: Record<string, unknown>;
  business_gate?: Record<string, unknown>;
  spend_gate_status?: string | null;
  budget_release_recommendation?: string | null;
}

export interface PilotReadoutGateSnapshot {
  scope_readiness?: PilotReadoutStatus;
  forecast_readiness?: PilotReadoutStatus;
  epidemiology_status?: PilotReadoutStatus;
  commercial_data_status?: PilotReadoutStatus;
  commercial_validation_status?: PilotReadoutStatus;
  holdout_status?: PilotReadoutStatus;
  budget_release_status?: PilotReadoutStatus;
  pilot_mode?: string | null;
  budget_mode?: string | null;
  validation_disclaimer?: string | null;
  missing_requirements?: string[];
  coverage_weeks?: number | null;
  truth_freshness_state?: string | null;
  validation_status?: string | null;
  quality_gate_failed_checks?: string[];
  forecast_gate_outcome?: string | null;
  latest_evaluation?: {
    available?: boolean;
    run_id?: string | null;
    generated_at?: string | null;
    selected_experiment_name?: string | null;
    calibration_mode?: string | null;
    gate_outcome?: string | null;
    retained?: boolean | null;
    archive_dir?: string | null;
  };
}

export interface PilotReadoutResponse {
  brand?: string;
  virus_typ?: string;
  horizon_days?: number;
  weekly_budget_eur?: number;
  generated_at?: string;
  run_context?: {
    brand?: string;
    virus_typ?: string;
    horizon_days?: number;
    generated_at?: string | null;
    as_of_date?: string | null;
    target_week_start?: string | null;
    model_version?: string | null;
    calibration_version?: string | null;
    artifact_transition_mode?: string | null;
    rollout_mode?: string | null;
    activation_policy?: string | null;
    forecast_readiness?: PilotReadoutStatus;
    commercial_validation_status?: PilotReadoutStatus;
    pilot_mode?: string | null;
    budget_mode?: string | null;
    validation_disclaimer?: string | null;
    scope_readiness?: PilotReadoutStatus;
    scope_readiness_by_section?: Partial<Record<PilotSurfaceScope, PilotReadoutStatus>>;
    promotion_status?: string | null;
    gate_snapshot?: PilotReadoutGateSnapshot;
  };
  executive_summary?: {
    what_should_we_do_now?: string;
    decision_stage?: string | null;
    forecast_readiness?: PilotReadoutStatus;
    commercial_validation_status?: PilotReadoutStatus;
    pilot_mode?: string | null;
    budget_mode?: string | null;
    validation_disclaimer?: string | null;
    scope_readiness?: PilotReadoutStatus;
    headline?: string | null;
    top_regions?: PilotReadoutRegion[];
    budget_recommendation?: {
      weekly_budget_eur?: number | null;
      recommended_active_budget_eur?: number | null;
      scenario_budget_eur?: number | null;
      spend_enabled?: boolean;
      budget_mode?: string | null;
      blocked_reasons?: string[];
    };
    confidence_summary?: {
      lead_region_confidence?: number | null;
      lead_region_event_probability?: number | null;
      evaluation_retained?: boolean | null;
      evaluation_gate_outcome?: string | null;
    };
    uncertainty_summary?: string | null;
    uncertainty_summary_detail?: StructuredReasonItem | null;
    reason_trace?: string[];
    reason_trace_details?: StructuredReasonItem[];
  };
  operational_recommendations?: {
    scope_readiness?: PilotReadoutStatus;
    summary?: {
      headline?: string | null;
      total_regions?: number | null;
      activate_regions?: number | null;
      prepare_regions?: number | null;
      watch_regions?: number | null;
      ready_recommendations?: number | null;
      guarded_recommendations?: number | null;
      observe_only_recommendations?: number | null;
    };
    regions?: PilotReadoutRegion[];
  };
  pilot_evidence?: {
    scope_readiness?: PilotReadoutStatus;
    evaluation?: {
      archive_dir?: string | null;
      report_path?: string | null;
      run_id?: string | null;
      generated_at?: string | null;
      selected_experiment_name?: string | null;
      calibration_mode?: string | null;
      gate_outcome?: string | null;
      retained?: boolean | null;
      baseline?: Record<string, unknown> | null;
      selected_experiment?: Record<string, unknown> | null;
      comparison_table?: Array<Record<string, unknown>>;
      validation?: Record<string, unknown> | null;
    } | null;
    readiness?: PilotReadoutGateSnapshot;
    truth_coverage?: Record<string, unknown>;
    business_validation?: Record<string, unknown>;
    operational_snapshot?: Record<string, unknown> | null;
    recent_operational_snapshots?: Array<Record<string, unknown>>;
    legacy_context?: {
      status?: string;
      sunset_date?: string;
      customer_surface_exposed?: boolean;
      note?: string;
    };
  };
  empty_state?: {
    code?: 'ready' | 'no_model' | 'no_data' | 'watch_only' | 'no_go';
    title?: string;
    body?: string;
  };
}

export interface PilotSurfaceData {
  pilotReadout: PilotReadoutResponse | null;
  loading: boolean;
}
