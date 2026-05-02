export type TriLayerMode = 'research' | 'shadow';

export type TriLayerBudgetPermissionState =
  | 'blocked'
  | 'calibration_window'
  | 'shadow_only'
  | 'limited'
  | 'approved';

export type TriLayerWavePhase =
  | 'baseline'
  | 'early_growth'
  | 'acceleration'
  | 'peak'
  | 'decline'
  | 'unknown';

export type TriLayerGateState = 'pass' | 'watch' | 'fail' | 'not_available';

export type TriLayerSourceConnectionState = 'connected' | 'partial' | 'not_connected';

export interface TriLayerSummary {
  early_warning_score: number | null;
  commercial_relevance_score: number | null;
  budget_permission_state: TriLayerBudgetPermissionState;
  budget_can_change: false;
  reason: string;
}

export interface TriLayerPosterior {
  intensity_mean: number | null;
  intensity_p10: number | null;
  intensity_p90: number | null;
  growth_mean: number | null;
  uncertainty: number | null;
}

export interface TriLayerEvidenceWeights {
  wastewater: number | null;
  clinical: number | null;
  sales: number | null;
}

export interface TriLayerLeadLag {
  wastewater_to_clinical_days_mean: number | null;
  clinical_to_sales_days_mean: number | null;
  lag_uncertainty: number | null;
}

export interface TriLayerGates {
  epidemiological_signal: TriLayerGateState;
  clinical_confirmation: TriLayerGateState;
  sales_calibration: TriLayerGateState;
  coverage: TriLayerGateState;
  drift: TriLayerGateState;
  budget_isolation: TriLayerGateState;
}

export interface TriLayerRegion {
  region: string;
  region_code: string;
  early_warning_score: number | null;
  commercial_relevance_score: number | null;
  budget_permission_state: TriLayerBudgetPermissionState;
  wave_phase: TriLayerWavePhase;
  posterior: TriLayerPosterior;
  evidence_weights: TriLayerEvidenceWeights;
  lead_lag: TriLayerLeadLag;
  gates: TriLayerGates;
  explanation: string;
}

export interface TriLayerSourceStatusItem {
  status: TriLayerSourceConnectionState;
  coverage: number | null;
  freshness_days: number | null;
}

export interface TriLayerSourceStatus {
  wastewater: TriLayerSourceStatusItem;
  clinical: TriLayerSourceStatusItem;
  sales: TriLayerSourceStatusItem;
}

export interface TriLayerSnapshot {
  module: 'tri_layer_evidence_fusion';
  version: 'tlef_bicg_v0';
  mode: TriLayerMode;
  as_of: string;
  virus_typ: string;
  horizon_days: number;
  brand: string;
  summary: TriLayerSummary;
  regions: TriLayerRegion[];
  source_status: TriLayerSourceStatus;
  model_notes: string[];
}

export interface TriLayerBacktestMetrics {
  onset_detection_gain: number | null;
  peak_lead_time: number | null;
  false_early_warning_rate: number | null;
  phase_accuracy: number | null;
  sales_lift_predictiveness: number | null;
  budget_regret_reduction: number | null;
  calibration_error: number | null;
  number_of_cutoffs: number | null;
  number_of_regions?: number | null;
  gate_transition_counts: Record<string, Record<string, number>>;
}

export interface TriLayerBacktestReport {
  status: string;
  run_id: string;
  metrics: TriLayerBacktestMetrics;
  baselines: Record<string, Record<string, unknown>>;
}

export interface TriLayerBacktestStatus {
  run_id: string;
  status: string;
  report?: TriLayerBacktestReport;
  error?: string;
}
