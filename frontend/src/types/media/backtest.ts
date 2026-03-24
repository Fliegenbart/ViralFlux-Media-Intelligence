export type BacktestChartMode = 'validation' | 'vintage' | 'planning';

export interface BacktestMetrics {
  r2_score?: number;
  correlation?: number;
  correlation_pct?: number;
  mae?: number;
  rmse?: number;
  smape?: number;
  data_points?: number;
  date_range?: {
    start?: string;
    end?: string;
  };
}

export interface BacktestVintageMetrics {
  configured_horizon_days?: number;
  median_lead_days?: number;
  p90_abs_error?: number;
  oos_points?: number;
}

export interface BacktestDecisionMetrics {
  event_threshold_pct?: number;
  alerts?: number;
  events?: number;
  hits?: number;
  false_alarms?: number;
  misses?: number;
  hit_rate_pct?: number;
  recall_pct?: number;
  false_alarm_rate_pct?: number;
  median_ttd_days?: number;
  p90_abs_error?: number;
  median_y_true_last_12w?: number;
  error_relative_pct?: number;
  readiness_score_0_100?: number;
  analyzed_points?: number;
}

export interface BacktestQualityGate {
  ttd_target_days?: number;
  hit_rate_target_pct?: number;
  p90_error_relative_target_pct?: number;
  lead_target_days?: number;
  ttd_passed?: boolean;
  hit_rate_passed?: boolean;
  error_passed?: boolean;
  lead_passed?: boolean;
  overall_passed?: boolean;
}

export interface BacktestForecastRecord {
  issue_date: string;
  target_date: string;
  lead_days?: number;
  y_hat?: number;
  y_hat_level?: number;
  y_hat_lead?: number;
  p_event?: number;
  selected_variant?: 'level' | 'lead' | 'blend';
  y_true?: number;
  horizon_days?: number;
  region?: string;
}

export interface BacktestTimingMetrics {
  configured_horizon_days?: number;
  best_lag_days?: number;
  corr_at_best_lag?: number;
  corr_at_horizon?: number;
  lead_passed?: boolean;
  lag_step_days?: number;
  aligned_points?: number;
}

export interface BacktestChartPoint {
  date: string;
  issue_date?: string;
  target_date?: string;
  issue_date_hint?: string;
  real_qty?: number | null;
  predicted_qty?: number | null;
  forecast_qty?: number | null;
  baseline_persistence?: number | null;
  baseline_seasonal?: number | null;
  ci_80_lower?: number | null;
  ci_80_upper?: number | null;
  ci_95_lower?: number | null;
  ci_95_upper?: number | null;
  ci_80_base?: number | null;
  ci_80_range?: number | null;
  ci_95_base?: number | null;
  ci_95_range?: number | null;
  is_forecast?: boolean;
  bio?: number | null;
  psycho?: number | null;
  context?: number | null;
  based_on?: string;
  region?: string;
  lead_days?: number;
  plot_date?: string;
  is_future_vintage?: boolean;
  amelag_viruslast?: number | null;
}

export interface WaveRadarRegion {
  bundesland: string;
  wave_start?: string | null;
  wave_week?: string | null;
  peak_week?: string | null;
  peak_incidence?: number | null;
  baseline_avg?: number | null;
  threshold?: number | null;
  total_incidence?: number | null;
  data_points?: number | null;
  wave_rank?: number | null;
}

export interface WaveRadarSummaryPoint {
  bundesland?: string | null;
  date?: string | null;
}

export interface WaveRadarSummary {
  first_onset?: WaveRadarSummaryPoint | null;
  last_onset?: WaveRadarSummaryPoint | null;
  spread_days?: number | null;
  regions_affected?: number | null;
  regions_total?: number | null;
}

export interface WaveRadarHeatmapRow {
  week_label: string;
  [bundesland: string]: string | number;
}

export interface WaveRadarResponse {
  disease?: string;
  season?: string;
  threshold_pct?: number;
  summary?: WaveRadarSummary | null;
  regions?: WaveRadarRegion[];
  heatmap?: WaveRadarHeatmapRow[];
  error?: string;
  available?: string[];
}

export interface BacktestResponse {
  run_id?: string;
  mode?: string;
  status?: string;
  virus_typ?: string;
  target_source?: string;
  target_key?: string;
  target_label?: string;
  metrics?: BacktestMetrics;
  chart_data?: BacktestChartPoint[];
  forecast_records?: BacktestForecastRecord[];
  decision_forecast_records?: BacktestForecastRecord[];
  vintage_metrics?: BacktestVintageMetrics;
  decision_metrics?: BacktestDecisionMetrics;
  timing_metrics?: BacktestTimingMetrics;
  quality_gate?: BacktestQualityGate;
  forecast_weeks?: number;
  proof_text?: string;
  llm_insight?: string;
  model_type?: string;
  created_at?: string;
  lead_lag?: {
    best_lag_points?: number;
    best_lag_days?: number;
    lag_step_days?: number;
    lag_correlation?: number;
    bio_leads_target?: boolean;
    relative_lag_days?: number;
    horizon_days?: number;
    effective_lead_days?: number;
    bio_leads_target_effective?: boolean;
    target_leads_bio_effective?: boolean;
  };
  walk_forward?: {
    enabled?: boolean;
    folds?: number;
    horizon_days?: number;
    min_train_points?: number;
    strict_vintage_mode?: boolean;
  };
  planning_curve?: {
    lead_days?: number;
    correlation?: number;
    curve?: Array<{
      date: string;
      based_on?: string;
      issue_date?: string;
      target_date?: string;
      planning_qty?: number;
    }>;
  };
}
