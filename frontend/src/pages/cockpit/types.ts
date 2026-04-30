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

/**
 * After the 2026-04-17 two-block refactor, the cockpit synthesises a headline
 * readiness that expresses the ranking/lead-time dichotomy explicitly:
 *   - GO_RANKING: BL-ranking is usable AND lead-time is defensible (lag >= 0
 *     against the selected truth target).
 *   - RANKING_OK: ranking is usable but the forecast still lags the selected
 *     truth target in time.
 *   - LEAD_ONLY: lead-time is defensible but the BL-ranking precision is
 *     too low to trust.
 *   - WATCH: neither currently defensible.
 *   - UNKNOWN: no backtest data at all.
 *
 * 2026-04-21 Integrity-Fix: two new severe states that override the banner
 * regardless of ranking/lead; both map to `gateTone === 'watch'` in UI code.
 *   - DATA_STALE: newest ml_forecasts row is older than FORECAST_MAX_STALE_DAYS.
 *     The cockpit is rendering a retrospective fan, not a forward forecast.
 *   - DRIFT_WARN: the daily `forecast_accuracy_log` reports drift=true or
 *     live Pearson correlation below ACCURACY_CORRELATION_MIN. Ranking must
 *     not be trusted even when the older ranking backtest looks fine.
 */
export type ForecastReadiness =
  | 'GO_RANKING'
  | 'RANKING_OK'
  | 'LEAD_ONLY'
  | 'WATCH'
  | 'DATA_STALE'
  | 'DRIFT_WARN'
  | 'SEASON_OFF'
  | 'UNKNOWN';

/** 2026-04-21 Pfad-C: season-stratified bucket (peak or post). */
export interface AccuracyBucket {
  samples: number;
  mae?: number | null;
  rmse?: number | null;
  mape?: number | null;
  correlation?: number | null;
  driftDetected?: boolean | null;
}

/** 2026-04-21 Calibration-Impact: in-sample estimate of what today's
 * calibrator would do to the monitor metrics. Marked clearly — the
 * real out-of-sample improvement lands when the first post-deploy
 * calibrated forecasts enter the eval window (~7 days). */
export interface AccuracyCalibrationImpact {
  evaluated: boolean;
  rawMape: number | null;
  calibratedMape: number | null;
  expectedMapeImprovementPp: number | null;
  calibratedDriftDetected: boolean | null;
  alpha: number | null;
  beta: number | null;
  reason: string | null;
  note: string | null;
}

/** 2026-04-21 Scale-Kalibrierung: post-hoc linear transform applied to
 * the raw model output. ``applied=false`` means the cockpit is showing
 * the raw forecast (either no calibrator fitted yet, or fit did not
 * improve RMSE). */
export interface ScaleCalibration {
  applied: boolean;
  alpha: number | null;
  beta: number | null;
  samples: number | null;
  rmseBefore: number | null;
  rmseAfter: number | null;
  rmseImprovementPct: number | null;
  rawPrediction: number | null;
  calibratedPrediction: number | null;
  fallbackReason: string | null;
}

/** Latest row from the daily forecast_accuracy_log monitor. */
export interface AccuracyLatest {
  /** Pearson correlation between forecast and observed wastewater signal. */
  correlation: number | null;
  /** Mean Absolute Percentage Error in percent. */
  mape: number | null;
  /** Drift-detector flag. */
  driftDetected: boolean | null;
  samples: number | null;
  /** ISO timestamp of the monitor run that produced this row. */
  computedAt: string | null;
  /** 2026-04-21 Pfad-C: season-aware blocks — null when the monitor row
   * predates the stratification rollout. UI renders peak/post side-by-side. */
  currentSeason?: 'peak' | 'post' | null;
  peak?: AccuracyBucket | null;
  post?: AccuracyBucket | null;
  /** 2026-04-21 Calibration-Impact block. ``evaluated=false`` when there
   * was no fit, otherwise ``calibratedMape`` + ``expectedMapeImprovementPp``
   * tell the user how much today's calibrator would move the needle. */
  calibrationImpact?: AccuracyCalibrationImpact | null;
}

/** How stale the newest persisted forecast is (ml_forecasts.max(forecast_date)). */
export interface ForecastFreshness {
  /** ISO date of the newest persisted forecast point. */
  latestForecastDate: string | null;
  /** Negative = in the past (retrospective fan); positive = real future point. */
  daysFromToday: number | null;
  /** True when newest forecast is older than FORECAST_MAX_STALE_DAYS. */
  isStale: boolean;
  /** True when the newest forecast lies in the future. */
  isFuture: boolean;
  /** 2026-04-21 A1 Root-Cause-Fix: AMELAG-cutoff of the last real feature.
   * ``null`` when no forecast row carries the freshness block (pre-fix rows). */
  featureAsOf?: string | null;
  /** How many days of forward-fill the nowcast-extension applied to reach today. */
  daysForwardFilled?: number | null;
  /** today - featureAsOf, in days. Useful for "AMELAG 13 Tage alt"-style labels. */
  featureLagDays?: number | null;
}
export type CalibrationMode = 'calibrated' | 'heuristic' | 'skipped' | 'unknown';

/**
 * Ranking-Block — how well we order the 16 Bundesländer. Populated from the
 * regional-panel training summary at h=7 (the only regional artefact set
 * that exists today).
 */
export interface ModelRankingStatus {
  horizonDays: number;
  /** Stable identifier for the upstream model family. */
  source: string;
  /** Human-readable label for the banner. */
  sourceLabel: string;
  /** Precision of the top-3 Bundesländer-ranking against truth. */
  precisionAtTop3: number | null;
  /** Area under the precision-recall curve. */
  prAuc: number | null;
  /** Expected Calibration Error. */
  ece: number | null;
  dataPoints: number | null;
  /** ISO timestamp of the training run that produced this row. */
  trainedAt: string | null;
}

/**
 * Lead-Block — how far ahead we see the wave against a fast-truth target.
 * Populated from the most recent successful backtest_runs row for
 * (virus_typ, horizon, target_source).
 */
export interface ModelLeadStatus {
  horizonDays: number;
  /** "ATEMWEGSINDEX" | "RKI_ARE" | "SURVSTAT" | etc. */
  targetSource: string;
  /** Human-readable label. */
  targetLabel: string;
  bestLagDays: number | null;
  correlationAtHorizon: number | null;
  correlationAtBestLag: number | null;
  maeVsPersistencePct: number | null;
  maeVsSeasonalPct: number | null;
  overallPassed: boolean;
  baselinePassed: boolean;
  intervalCoverage80Pct: number | null;
  intervalCoverage95Pct: number | null;
  backtestEndDate: string | null;
  backtestCalibrationMode: CalibrationMode;
  hasRun: boolean;
}

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
  /**
   * Decision label from the regional decision engine.
   * `'TrainingPending'` is a snapshot-builder placeholder emitted when the
   * regional service could not score a Bundesland (usually because the
   * pooled panel lacks coverage for that region). Such tiles must be
   * rendered as muted "Training pending" placeholders rather than
   * mistaken for a zero-signal forecast.
   */
  decisionLabel?: 'Watch' | 'Prepare' | 'Activate' | 'TrainingPending' | null;
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
   * 2026-04-21 B1-Fix: ranking-separation score on [0.15, 0.85]. Linear in
   * |top_delta| with a hard floor and ceiling. NOT a statistical confidence
   * — we renamed the field away from ``confidence`` so UI copy stops
   * implying model uncertainty. Legacy ``confidence`` alias kept for
   * backwards compatibility.
   */
  signalScore?: number;
  /**
   * Legacy alias for ``signalScore``. New UI should prefer ``signalScore``
   * and call the value what it is: a ranking-separation score, not a
   * calibrated probability.
   */
  confidence: number;
  /** Expected reach uplift. Null when there is no media-effect model. */
  expectedReachUplift: number | null;
  why: string;
  primary?: boolean;
  /**
   * True when the recommendation comes from the live ranking-signal
   * pair (top-riser / top-faller) rather than from a budget-anchored
   * optimiser. Signal-mode rec always has amountEur=null — the Demo-
   * Szene rechnet einen hypothetischen Betrag auf Wunsch nach.
   */
  signalMode?: boolean;
}

export interface TimelinePoint {
  date: string;
  /**
   * Primary observed series — since 2026-04-21 on the
   * ``wastewater_aggregated.viruslast`` scale (the same scale the forecast
   * model outputs). Before the Chart-Skalen-Fix this used to be SURVSTAT
   * weekly incidence, which is on a completely different scale and made
   * the fan-chart look like a 2-3x over-prediction artefact.
   */
  observed: number | null;
  nowcast: number | null;
  /**
   * Secondary truth signal: Notaufnahme (AKTIN) ARI 7-day moving average,
   * national, all age groups. Null where unavailable or not applicable to
   * the current virus scope. Lead-time story — this series tracks the
   * real disease burden 7–10 days ahead of the RKI-meldewesen observed
   * line.
   */
  edActivity: number | null;
  /**
   * SURVSTAT weekly incidence (per 100k), linear-interpolated to daily.
   * Different scale than ``observed`` — kept as a separate series so the
   * frontend can render a "Meldewesen"-overlay on a secondary y-axis.
   */
  survstatIncidence?: number | null;
  q10: number | null;
  q50: number | null;
  q90: number | null;
  /**
   * True when this point's q-values were linearly interpolated between two
   * forecast anchors whose span exceeds the backend's honesty threshold
   * (>3 days), OR when they come from a single-anchor nearest-fallback that
   * is not on the exact target day. The chart renders these segments as
   * dashed lines so users can see where the fan stops being an actual
   * forecast and starts being a bridge between two model runs.
   */
  interpolated?: boolean;
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
 *
 * Top-level fields (horizonDays, bestLagDays, etc.) are kept as aliases of
 * the `lead` block for backwards compatibility with existing UI code.
 * New code should read the structured `ranking` and `lead` blocks directly.
 */
export interface ModelStatus {
  virusTyp: string;
  /** Synthesised readiness headline — combines ranking + lead state. */
  forecastReadiness: ForecastReadiness;
  /** Calibration label applied to the lead-time backtest's event score. */
  calibrationMode: CalibrationMode;
  /** Whether a regional (per-BL) model exists for this virus. */
  regionalAvailable: boolean;

  /** Alias of lead.horizonDays for backwards compat. */
  horizonDays: number;
  overallPassed: boolean;
  baselinePassed: boolean;
  bestLagDays: number | null;
  correlationAtHorizon: number | null;
  maeVsPersistencePct: number | null;
  intervalCoverage80Pct: number | null;
  intervalCoverage95Pct: number | null;
  /** Training-window end of the currently promoted artifact. */
  trainingWindowEnd: string | null;

  /** New: structured blocks for the two-source banner. */
  ranking: ModelRankingStatus;
  lead: ModelLeadStatus;
  /** Training-panel maturity badge. Surfaces how big the national training set is
   * so we can label Phase-1 pilots honestly. Always populated; `unknown` tier
   * when metadata is missing. */
  trainingPanel: ModelTrainingPanel;
  /** Honest label for the forecast trajectory method so the UI does not imply
   * native per-day inferences while the direct-stacking model only delivers
   * a T+7 endpoint. */
  trajectorySource: ForecastTrajectorySource;

  /** 2026-04-21 Integrity-Fix: live accuracy + freshness blocks. Both are
   * always populated (fields may be null when no row exists). UI must render
   * a red badge and surface the `note` copy when readiness === 'DATA_STALE'
   * or 'DRIFT_WARN'. */
  accuracyLatest?: AccuracyLatest;
  forecastFreshness?: ForecastFreshness;
  /** 2026-04-21 Scale-Kalibrierung: post-hoc linear transform on the raw
   * national forecast output. When ``applied=true`` the cockpit should
   * show a "Kalibrator aktiv · RMSE −X %" badge so the transform is
   * never hidden from the reader. */
  scaleCalibration?: ScaleCalibration;

  note?: string | null;
}

/**
 * Forecast-trajectory provenance. Today the backend interpolates six daily
 * points between today and T+7 (linear) with a sqrt-expanding uncertainty
 * cone. Once the native h=1..6 artefacts are wired into the cockpit path,
 * `nativeHorizonsAvailable` flips to true and `mode` moves to
 * `"native_per_horizon"`.
 */
export type TrajectoryMode =
  | 'interpolated_from_h7_endpoint'
  | 'native_per_horizon'
  | 'unknown';

export interface ForecastTrajectorySource {
  mode: TrajectoryMode;
  /** Short label for inline UI kickers, e.g. "7-Punkt-Trajektorie aus T+7-Modell". */
  label: string;
  /** One-sentence detail for tooltips or captions. */
  detail: string;
  /** True only when the backend pulled native h=1..6 predictions. */
  nativeHorizonsAvailable: boolean;
}

/**
 * Training-panel transparency badge — derived from the national XGBoost
 * metadata.json. Classifies the virus into `pilot` (N<100), `beta` (100-199),
 * or `production` (≥200) so the UI can render "Phase-1-Pilot · N=57" style
 * labels without back-end UX copy changes.
 */
export type MaturityTier = 'pilot' | 'beta' | 'production' | 'unknown';

export interface ModelTrainingPanel {
  trainingSamples: number | null;
  maturityTier: MaturityTier;
  /** Ready-to-render short label, e.g. "Phase-1-Pilot · N=57". */
  maturityLabel: string;
  /** ISO-8601 timestamp of the last training run, or null if unknown. */
  trainedAt: string | null;
  modelVersion: string | null;
}

export interface MediaPlanStatus {
  /** True if a real client media plan is connected and feeding EUR values. */
  connected: boolean;
  totalWeeklySpendEur: number | null;
  note?: string | null;
}

export type EvidenceComponentStatus = 'pass' | 'warn' | 'block' | 'unknown';

export interface EvidenceComponent {
  key: string;
  label: string;
  score: number | null;
  status: EvidenceComponentStatus;
  detail: string;
  blockers: string[];
}

export interface VirusWaveTruthSource {
  phase?: string | null;
  phase_label?: string | null;
  phaseLabel?: string | null;
  onset_date?: string | null;
  onsetDate?: string | null;
  peak_date?: string | null;
  peakDate?: string | null;
  latest_date?: string | null;
  latestDate?: string | null;
  status?: string | null;
  confidence?: number | null;
  lead_days?: number | null;
  leadDays?: number | null;
}

export interface VirusWaveTruthAlignment {
  lead_lag_days?: number | null;
  leadLagDays?: number | null;
  alignment_score?: number | null;
  alignmentScore?: number | null;
  divergence_score?: number | null;
  divergenceScore?: number | null;
  amelag_lead_days?: number | null;
  amelagLeadDays?: number | null;
}

export interface VirusWaveEvidenceWeights {
  amelag?: number | null;
  survstat?: number | null;
  [key: string]: number | null | undefined;
}

export interface VirusWaveTruthEvidence {
  effective_weights?: VirusWaveEvidenceWeights | null;
  effectiveWeights?: VirusWaveEvidenceWeights | null;
  confidence_method?: string | null;
  confidenceMethod?: string | null;
  confidence?: number | null;
  method?: string | null;
  summary?: string[] | null;
}

export interface VirusWaveTruth {
  schema?: string | null;
  engine_version?: string | null;
  engineVersion?: string | null;
  status?: string | null;
  reason?: string | null;
  scope?: {
    virus?: string | null;
    region?: string | null;
    lookback_weeks?: number | null;
    lookbackWeeks?: number | null;
  } | null;
  sourceStatus?: Record<string, unknown> | null;
  source_status?: Record<string, unknown> | null;
  survstat?: VirusWaveTruthSource | null;
  amelag?: VirusWaveTruthSource | null;
  alignment?: VirusWaveTruthAlignment | null;
  evidence?: VirusWaveTruthEvidence | null;
}

export interface SiteEarlyWarningAlert {
  standort: string;
  bundesland: string;
  datum: string;
  typ: string;
  stage: 'yellow' | 'red' | 'none' | string;
  metric?: string | null;
  current_value?: number | null;
  currentValue?: number | null;
  baseline_value?: number | null;
  baselineValue?: number | null;
  change_pct?: number | null;
  changePct?: number | null;
  previous_value?: number | null;
  previousValue?: number | null;
  previous_date?: string | null;
  previousDate?: string | null;
  unter_bg?: string | null;
  unterBg?: string | null;
  laborwechsel?: string | null;
  reasons?: string[] | string | null;
  quality_flags?: string[] | null;
  qualityFlags?: string[] | null;
}

export interface SiteEarlyWarningPayload {
  measurements_evaluated?: number | null;
  measurementsEvaluated?: number | null;
  site_virus_series?: number | null;
  siteVirusSeries?: number | null;
  historical_alerts?: number | null;
  historicalAlerts?: number | null;
  active_alerts?: SiteEarlyWarningAlert[] | number | null;
  activeAlerts?: SiteEarlyWarningAlert[] | null;
  active_alert_count?: number | null;
  activeAlertCount?: number | null;
  active_red_alerts?: number | null;
  activeRedAlerts?: number | null;
  active_yellow_alerts?: number | null;
  activeYellowAlerts?: number | null;
  active_since_date?: string | null;
  activeSinceDate?: string | null;
  latest_measurement_date?: string | null;
  latestMeasurementDate?: string | null;
  source?: string | null;
  config?: Record<string, unknown> | null;
}

export interface EvidenceValidationStatus {
  research_only?: boolean | null;
  researchOnly?: boolean | null;
  candidate_status?: string | null;
  candidateStatus?: string | null;
  recommendation?: 'go_for_simulation' | 'review' | 'no_go' | string | null;
  onset_gain_days?: number | null;
  onsetGainDays?: number | null;
  false_warning_risk?: number | null;
  falseWarningRisk?: number | null;
  phase_accuracy?: number | null;
  phaseAccuracy?: number | null;
  survstat_only?: Record<string, unknown> | null;
  survstatOnly?: Record<string, unknown> | null;
  amelag_survstat?: Record<string, unknown> | null;
  amelagSurvstat?: Record<string, unknown> | null;
}

export interface CockpitSystemStatus {
  diagnostic_only?: boolean | null;
  diagnosticOnly?: boolean | null;
  can_change_budget?: boolean | null;
  canChangeBudget?: boolean | null;
  budget_can_change?: boolean | null;
  budgetCanChange?: boolean | null;
  global_status?: string | null;
  globalStatus?: string | null;
  budget_mode?: string | null;
  budgetMode?: string | null;
  latest_amelag_date?: string | null;
  latestAmelagDate?: string | null;
  latest_survstat_date?: string | null;
  latestSurvstatDate?: string | null;
}


export type MediaSpendingGlobalStatus =
  | 'blocked'
  | 'watch_only'
  | 'planner_assist'
  | 'spendable';

export type MediaSpendingReleaseMode =
  | 'blocked'
  | 'shadow_only'
  | 'limited'
  | 'approved';

export type MediaSpendingBudgetPermission =
  | 'blocked'
  | 'manual_approval_required'
  | 'approved_with_cap';

export type MediaSpendingTruthStatus =
  | 'increase_approved'
  | 'preposition_approved'
  | 'maintain'
  | 'cap_or_reduce'
  | 'decrease_approved'
  | 'watch_only'
  | 'blocked';

export interface MediaSpendingTruthRegion {
  region_code: Bundesland | string;
  region_name: string;
  media_spending_truth: MediaSpendingTruthStatus | string;
  budget_permission?: MediaSpendingBudgetPermission | string;
  recommended_action: string;
  recommended_delta_pct: number;
  shadow_delta_pct?: number;
  shadowDeltaPct?: number;
  approved_delta_pct?: number;
  approvedDeltaPct?: number;
  execution_status?: MediaSpendingReleaseMode | 'blocked' | string;
  executionStatus?: MediaSpendingReleaseMode | 'blocked' | string;
  max_delta_pct: number;
  surge_probability_7d?: number | null;
  expected_growth_score?: number | null;
  confidence: number;
  budget_opportunity_score: number;
  forecast_class?: string | null;
  reason_codes: string[];
  limiting_factors: string[];
  manual_approval_required: boolean;
  planner_assist?: boolean;
  research_only?: boolean;
  limitations?: string[];
}

export interface MediaSpendingTruthGateComponent {
  name?: string;
  status: 'passed' | 'failed' | 'warning' | 'blocked' | 'insufficient_evidence' | string;
  observed?: number | null;
  threshold?: number | null;
  direction?: 'higher_is_better' | 'lower_is_better' | string;
}

export interface MediaSpendingTruthGateEvaluation {
  gate: string;
  status: 'passed' | 'failed' | 'warning' | 'blocked' | 'insufficient_evidence' | string;
  threshold?: Record<string, unknown>;
  observed?: Record<string, unknown>;
  severity?: 'hard' | 'limited' | 'soft' | string;
  reason?: string;
  components?: Record<string, MediaSpendingTruthGateComponent>;
  explanation?: string;
}

export interface MediaSpendingTruthPayload {
  schema_version: 'media_spending_truth_v1' | string;
  schemaVersion?: string;
  engine_version?: string;
  engineVersion?: string;
  decision_date?: string;
  decisionDate?: string;
  valid_until?: string;
  validUntil?: string;
  pathogen_scope?: string;
  horizon_days?: number;
  global_status: MediaSpendingGlobalStatus | string;
  globalStatus?: MediaSpendingGlobalStatus | string;
  globalDecision?: MediaSpendingReleaseMode | string;
  release_mode?: MediaSpendingReleaseMode | string;
  releaseMode?: MediaSpendingReleaseMode | string;
  max_approved_delta_pct?: number;
  maxApprovedDeltaPct?: number;
  budget_permission: MediaSpendingBudgetPermission | string;
  budgetPermission?: MediaSpendingBudgetPermission | string;
  can_change_budget?: boolean | null;
  canChangeBudget?: boolean | null;
  budget_can_change?: boolean | null;
  budgetCanChange?: boolean | null;
  diagnostic_only?: boolean | null;
  diagnosticOnly?: boolean | null;
  data_quality?: string;
  forecast_evidence?: string;
  forecastEvidence?: string;
  decision_policy?: Record<string, unknown>;
  forecast_gate?: Record<string, unknown>;
  forecastGate?: Record<string, unknown>;
  decision_backtest?: Record<string, unknown>;
  decisionBacktest?: Record<string, unknown>;
  blocked_because?: string[];
  blockedBecause?: string[];
  gate_evaluations?: MediaSpendingTruthGateEvaluation[];
  gateEvaluations?: MediaSpendingTruthGateEvaluation[];
  gateTrace?: MediaSpendingTruthGateEvaluation[];
  regions: MediaSpendingTruthRegion[];
  limitations?: string[];
  virusWaveTruth?: VirusWaveTruth | null;
}

export interface EvidenceScore {
  /** 0..100 decision-support score. Not a probability. */
  overallScore: number | null;
  releaseStatus: 'releasable' | 'candidate_only' | 'blocked' | string;
  label: string;
  components: EvidenceComponent[];
  blockers: string[];
  alignmentSummary?: {
    total_rows?: number;
    status_counts?: Record<string, number>;
  } | null;
  businessValidation?: {
    validated_for_budget_activation?: boolean;
    rows?: number;
    weeks?: number;
    regions?: number;
    media_spend_eur?: number;
    missing_requirements?: string[];
  } | null;
  plainLanguage: string;
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
  /** Legacy alias for averageWaveProbability. Kept for backwards compat. */
  averageConfidence: number | null;
  /**
   * Durchschnittliche Steige-Wahrscheinlichkeit über alle Bundesländer
   * (Mittelwert pRising). Post-Saison naturgemäß niedrig — darf nicht
   * als "Modell-Konfidenz" gelesen werden. Der Begleit-String
   * `averageWaveProbabilityContext` liefert die Einordnung.
   */
  averageWaveProbability?: number | null;
  averageWaveProbabilityContext?: string;
  primaryRecommendation: ShiftRecommendation | null;
  secondaryRecommendations: ShiftRecommendation[];
  regions: RegionForecast[];
  timeline: TimelinePoint[];
  sources: SourceStatus[];
  topDrivers: { label: string; value: string; subtitle?: string }[];
  /** Always populated — UI uses this for WATCH banners, calibration warnings, etc. */
  modelStatus: ModelStatus;
  /** Decision-support trust layer: signal + freshness + H5/H7 + business gate. */
  evidenceScore?: EvidenceScore | null;
  /** MediaSpendingTruth v1: final media-planning action layer. */
  mediaSpendingTruth?: MediaSpendingTruthPayload | null;
  /** Raw H5/H7 alignment snapshot for future UI drilldowns. */
  horizonAlignment?: unknown;
  /** Always populated — UI uses this to decide whether to show EUR values or "—". */
  mediaPlan: MediaPlanStatus;
  /** Free-form operator notes, shown in a small "facts" strip. */
  notes: string[];
  /** Optional evidence-first cockpit blocks. Older snapshots omit them. */
  systemStatus?: CockpitSystemStatus | null;
  virusWaveTruth?: VirusWaveTruth | null;
  siteEarlyWarning?: SiteEarlyWarningPayload | null;
  site_early_warning?: SiteEarlyWarningPayload | null;
  backtestResearch?: EvidenceValidationStatus | null;
  backtest_research?: EvidenceValidationStatus | null;
}
