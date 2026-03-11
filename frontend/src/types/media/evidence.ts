import { BacktestResponse } from './backtest';
import { MetricContract, SourceStatusSummary } from './shared';

export interface TruthCoverage {
  coverage_weeks: number;
  latest_week?: string | null;
  regions_covered: number;
  products_covered: number;
  outcome_fields_present: string[];
  required_fields_present?: string[];
  conversion_fields_present?: string[];
  trust_readiness: string;
  truth_freshness_state?: 'fresh' | 'stale' | 'missing' | 'unknown' | string;
  source_labels?: string[];
  last_imported_at?: string | null;
  latest_batch_id?: string | null;
  latest_source_label?: string | null;
}

export interface TruthImportIssue {
  row_number?: number | null;
  field_name?: string | null;
  issue_code: string;
  message: string;
  raw_row?: Record<string, unknown> | null;
  created_at?: string | null;
}

export interface TruthImportBatchSummary {
  batch_id: string;
  brand: string;
  source_label: string;
  file_name?: string | null;
  status: 'validated' | 'imported' | 'partial_success' | 'failed' | string;
  rows_total: number;
  rows_valid: number;
  rows_imported: number;
  rows_rejected: number;
  rows_duplicate: number;
  week_min?: string | null;
  week_max?: string | null;
  coverage_after_import?: TruthCoverage;
  uploaded_at?: string | null;
}

export interface TruthImportResponse {
  imported: number;
  batch_id?: string | null;
  batch_summary?: TruthImportBatchSummary;
  issues: TruthImportIssue[];
  preview_only: boolean;
  coverage_after_import?: TruthCoverage;
  coverage?: TruthCoverage;
  message?: string;
}

export interface TruthImportBatchDetailResponse {
  batch: TruthImportBatchSummary;
  issues: TruthImportIssue[];
}

export interface OutcomeLearningSummary {
  learning_state?: string;
  coverage_weeks?: number;
  outcome_signal_score?: number | null;
  outcome_confidence_pct?: number | null;
  top_product_learnings?: Array<{
    product?: string;
    product_key?: string;
    outcome_signal_score?: number | null;
    outcome_confidence_pct?: number | null;
    coverage_weeks?: number;
  }>;
  top_region_learnings?: Array<{
    region_code?: string;
    outcome_signal_score?: number | null;
    outcome_confidence_pct?: number | null;
    coverage_weeks?: number;
  }>;
  top_pair_learnings?: Array<{
    product?: string;
    product_key?: string;
    region_code?: string;
    outcome_signal_score?: number | null;
    outcome_confidence_pct?: number | null;
    coverage_weeks?: number;
  }>;
  field_contracts?: Record<string, MetricContract>;
}

export interface TruthSnapshot {
  brand: string;
  coverage: TruthCoverage;
  truth_gate?: {
    passed: boolean;
    state?: string;
    learning_state?: string;
    message?: string | null;
    guidance?: string | null;
    field_contracts?: Record<string, MetricContract>;
  };
  outcome_learning_summary?: OutcomeLearningSummary;
  recent_batches: TruthImportBatchSummary[];
  latest_batch?: TruthImportBatchSummary | null;
  latest_batch_issue_count?: number;
  template_url?: string;
  known_limits?: string[];
  analyst_note?: string;
}

export interface SignalStackItem {
  source_key: string;
  label: string;
  signal_group: string;
  last_available_at?: string | null;
  freshness_state: string;
  coverage_state: string;
  quality_note?: string;
  contribution_state?: string;
  is_core_signal?: boolean;
}

export interface SignalStackResponse {
  virus_typ: string;
  generated_at: string;
  items: SignalStackItem[];
  summary: {
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
}

export interface ModelLineage {
  virus_typ: string;
  model_family: string;
  base_estimators: string[];
  meta_learner: string;
  model_version: string;
  trained_at?: string | null;
  feature_set_version?: string;
  feature_names?: string[];
  training_window?: {
    start?: string | null;
    end?: string | null;
    points?: number;
  };
  drift_state?: 'ok' | 'warning' | 'unknown' | string;
  coverage_limits?: string[];
  latest_accuracy?: {
    computed_at?: string | null;
    samples?: number | null;
    mape?: number | null;
    rmse?: number | null;
    correlation?: number | null;
  };
  latest_forecast_created_at?: string | null;
}

export interface ForecastMonitoring {
  virus_typ: string;
  target_source: string;
  monitoring_status: 'healthy' | 'warning' | 'critical' | 'unknown' | string;
  forecast_readiness: 'GO' | 'WATCH' | string;
  drift_status: 'ok' | 'warning' | 'unknown' | string;
  freshness_status: 'fresh' | 'stale' | 'expired' | 'missing' | string;
  accuracy_freshness_status?: 'fresh' | 'stale' | 'expired' | 'missing' | string;
  backtest_freshness_status?: 'fresh' | 'stale' | 'expired' | 'missing' | string;
  issue_date?: string | null;
  model_version?: string | null;
  event_forecast?: {
    event_probability?: number | null;
    confidence?: number | null;
    confidence_label?: string | null;
    calibration_passed?: boolean | null;
  };
  latest_accuracy?: {
    computed_at?: string | null;
    window_days?: number | null;
    samples?: number | null;
    mae?: number | null;
    rmse?: number | null;
    mape?: number | null;
    correlation?: number | null;
    drift_detected?: boolean | null;
    freshness_status?: string | null;
  };
  latest_backtest?: {
    run_id?: string | null;
    created_at?: string | null;
    target_source?: string | null;
    freshness_status?: string | null;
    quality_gate?: Record<string, unknown> | null;
    interval_coverage?: Record<string, unknown> | null;
    event_calibration?: Record<string, unknown> | null;
    timing_metrics?: Record<string, unknown> | null;
    lead_lag?: Record<string, unknown> | null;
    improvement_vs_baselines?: Record<string, unknown> | null;
  };
  alerts: string[];
}

export interface MediaEvidenceResponse {
  virus_typ: string;
  target_source: string;
  generated_at: string;
  proxy_validation?: BacktestResponse | null;
  truth_validation?: BacktestResponse | null;
  truth_validation_legacy?: BacktestResponse | null;
  recent_runs: Array<Record<string, unknown>>;
  data_freshness: Record<string, string | null>;
  source_status: SourceStatusSummary;
  signal_stack: SignalStackResponse;
  model_lineage: ModelLineage;
  forecast_monitoring?: ForecastMonitoring;
  truth_coverage: TruthCoverage;
  truth_gate?: {
    passed: boolean;
    state?: string;
    learning_state?: string;
    message?: string | null;
    guidance?: string | null;
    field_contracts?: Record<string, MetricContract>;
  };
  truth_snapshot?: TruthSnapshot;
  outcome_learning_summary?: OutcomeLearningSummary;
  known_limits: string[];
}
