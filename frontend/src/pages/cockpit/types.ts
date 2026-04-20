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
 */
export type ForecastReadiness =
  | 'GO_RANKING'
  | 'RANKING_OK'
  | 'LEAD_ONLY'
  | 'WATCH'
  | 'UNKNOWN';
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
  /**
   * Secondary truth signal: Notaufnahme (AKTIN) ARI 7-day moving average,
   * national, all age groups. Null where unavailable or not applicable to
   * the current virus scope. Lead-time story — this series tracks the
   * real disease burden 7–10 days ahead of the RKI-meldewesen observed
   * line.
   */
  edActivity: number | null;
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
  topDrivers: { label: string; value: string; subtitle?: string }[];
  /** Always populated — UI uses this for WATCH banners, calibration warnings, etc. */
  modelStatus: ModelStatus;
  /** Always populated — UI uses this to decide whether to show EUR values or "—". */
  mediaPlan: MediaPlanStatus;
  /** Free-form operator notes, shown in a small "facts" strip. */
  notes: string[];
}
