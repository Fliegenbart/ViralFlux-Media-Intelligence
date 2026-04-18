/**
 * Shape of the /api/v1/media/cockpit/backtest response — the pitch-story
 * payload that drives Drawer V "Backtest".
 *
 * Mirrors backend/app/services/media/cockpit/backtest_builder.py.
 */

export interface BacktestWindow {
  start: string | null;       // "2019-01-07"
  end: string | null;         // "2026-04-12"
  folds: number;              // count of unique walk-forward dates
  weeks: number;              // same as folds when weekly step
}

export interface BacktestHeadline {
  precision_at_top3: number | null;
  precision_at_top5: number | null;
  pr_auc: number | null;
  brier_score: number | null;
  ece: number | null;
  activation_false_positive_rate: number | null;
  median_lead_days: number | null;
}

export interface BacktestBaselines {
  persistence_precision_at_top3: number | null;
  persistence_pr_auc: number | null;
}

export interface BacktestCalibration {
  tau: number | null;
  kappa: number | null;
  action_threshold: number | null;
}

export interface BacktestQualityGate {
  forecast_readiness: string | null;
  overall_passed: boolean | null;
  checks: Record<string, boolean>;
}

export interface BacktestBLRow {
  code: string;
  name: string;
  windows: number | null;
  precision_at_top3: number | null;
  precision: number | null;
  recall: number | null;
  pr_auc: number | null;
  brier_score: number | null;
  ece: number | null;
  activations: number | null;
  events: number | null;
}

export interface BacktestWeeklyHit {
  as_of_date: string;
  target_date: string;
  predicted_top: Array<{ code: string; probability: number | null }>;
  observed_top: string[];
  hits: string[];
  misses: string[];
  false_negatives: string[];
  was_hit: boolean;
}

export interface BacktestPayload {
  virus_typ: string;
  horizon_days: number;
  event_definition_version: string | null;
  available: boolean;
  reason?: string;
  window: BacktestWindow;
  headline: BacktestHeadline;
  baselines: BacktestBaselines;
  calibration: BacktestCalibration;
  quality_gate: BacktestQualityGate | null;
  per_bundesland: BacktestBLRow[];
  weekly_hits: BacktestWeeklyHit[];
}
