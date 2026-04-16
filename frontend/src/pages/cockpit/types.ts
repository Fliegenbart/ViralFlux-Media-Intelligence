/**
 * Shared contracts for the peix cockpit.
 *
 * Historical note: the first iteration of this file mirrored a GELO-curated
 * fixture, with every field populated. After the 2026-04-16 math audit several
 * of those fields turned out to have no calibrated backing in the underlying
 * models, and others depend on client-specific inputs (media plan, EUR
 * budgets) that are not guaranteed to be connected. The schema below therefore
 * allows null on the "narrative" EUR- and confidence-style fields and adds a
 * `modelStatus` block so the UI can honestly surface the backend's
 * quality-gate state.
 *
 * Related backend modules:
 *   - app/services/ml/regional_forecast.py (predict_all_regions)
 *   - app/services/ml/regional_media_allocation_engine.py
 *   - app/services/media/cockpit/freshness.py
 *   - app/services/media/cockpit/snapshot_builder.py (added in this branch)
 */

export type Bundesland =
  | 'SH' | 'HH' | 'NI' | 'HB' | 'NW' | 'HE' | 'RP' | 'SL'
  | 'BW' | 'BY' | 'BE' | 'BB' | 'MV' | 'SN' | 'ST' | 'TH';

export type ForecastReadiness = 'GO' | 'WATCH' | 'HOLD' | 'UNKNOWN';
export type CalibrationMode = 'calibrated' | 'heuristic' | 'skipped' | 'unknown';

export interface RegionForecast {
  code: Bundesland;
  name: string;
  /** Relative change in wave indicator over the horizon (0.12 = +12%). Null when no regional model for this virus. */
  delta7d: number | null;
  /**
   * Event signal on [0,1]. Kept under the legacy name for backwards
   * compatibility; treat as "wave-rising probability" ONLY if
   * `modelStatus.calibrationMode === 'calibrated'`. Otherwise this is a
   * sigmoid-of-z-score heuristic — see the math audit.
   */
  pRising: number | null;
  /** Q10/Q50/Q90 of the forecast, normalised to 100 = today. Null when not available. */
  forecast: { q10: number; q50: number; q90: number } | null;
  /** Short reason blurb — from model reason_trace only, never invented. */
  drivers: string[];
  /** Current client media spend EUR (weekly). Null when no media plan is connected. */
  currentSpendEur: number | null;
  /** Recommended spend delta, EUR. Null when no media plan is connected. */
  recommendedShiftEur: number | null;
  /** Decision label from the regional decision engine. */
  decisionLabel?: 'Watch' | 'Prepare' | 'Activate' | null;
}

export interface ShiftRecommendation {
  id: string;
  fromCode: Bundesland;
  toCode: Bundesland;
  fromName: string;
  toName: string;
  /** EUR shift amount. Null when no media plan is connected. */
  amountEur: number | null;
  /**
   * Event signal on [0,1] that triggered this recommendation. Legacy name
   * `confidence` kept for backwards compatibility. Treat as probability ONLY
   * if `modelStatus.calibrationMode === 'calibrated'`.
   */
  confidence: number;
  /** Expected reach uplift. Null when there is no media-effect model. */
  expectedReachUplift: number | null;
  why: string;
  primary?: boolean;
}

export interface TimelinePoint {
  date: string;
  observed: number | null;
  nowcast: number | null;
  q10: number | null;
  q50: number | null;
  q90: number | null;
  horizonDays: number;
}

export interface SourceStatus {
  name: string;
  lastUpdate: string;
  latencyDays: number;
  health: 'good' | 'delayed' | 'stale';
  note?: string;
}

/**
 * Operational honesty payload — always shown in the cockpit so the user can
 * judge whether the numbers are production-grade or watch/warn state.
 */
export interface ModelStatus {
  virusTyp: string;
  horizonDays: number;
  /** From backtest_runs.metrics.quality_gate.forecast_readiness. */
  forecastReadiness: ForecastReadiness;
  overallPassed: boolean;
  /** True only if the model beats the persistence baseline on MAE. */
  baselinePassed: boolean;
  /** Lag at which correlation with truth is maximal. Negative = model lags behind reality. */
  bestLagDays: number | null;
  correlationAtHorizon: number | null;
  /** Negative = model worse than "next week = this week". */
  maeVsPersistencePct: number | null;
  /** How event-probability is derived. `heuristic`/`skipped` => do NOT label as "Konfidenz". */
  calibrationMode: CalibrationMode;
  intervalCoverage80Pct: number | null;
  intervalCoverage95Pct: number | null;
  /** Training-window end of the currently promoted artifact. */
  trainingWindowEnd: string | null;
  /** Whether a regional (per-BL) model exists for this virus. */
  regionalAvailable: boolean;
  note?: string | null;
}

export interface MediaPlanStatus {
  /** True if a real client media plan is connected and feeding EUR values. */
  connected: boolean;
  totalWeeklySpendEur: number | null;
  note?: string | null;
}

export interface CockpitSnapshot {
  client: string;
  virusTyp: string;
  virusLabel: string;
  isoWeek: string;
  generatedAt: string;
  /** Null when mediaPlan.connected === false. */
  totalSpendEur: number | null;
  /** Mean pRising across regions. Legacy field; same honesty caveat as pRising. */
  averageConfidence: number | null;
  primaryRecommendation: ShiftRecommendation | null;
  secondaryRecommendations: ShiftRecommendation[];
  regions: RegionForecast[];
  timeline: TimelinePoint[];
  sources: SourceStatus[];
  topDrivers: { label: string; value: string }[];
  /** Always populated — UI uses this for WATCH banners, calibration warnings, etc. */
  modelStatus: ModelStatus;
  /** Always populated — UI uses this to decide whether to show EUR values or "—". */
  mediaPlan: MediaPlanStatus;
  /** Free-form operator notes, shown in a small "facts" strip. */
  notes: string[];
}
