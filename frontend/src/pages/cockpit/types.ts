/**
 * Shared contracts for the peix GELO cockpit.
 * Thin TypeScript mirror of the backend's
 *   - regional_forecast_media.py
 *   - regional_media_allocation_contracts.py
 *   - forecast_contracts.py
 */

export type Bundesland =
  | 'SH' | 'HH' | 'NI' | 'HB' | 'NW' | 'HE' | 'RP' | 'SL'
  | 'BW' | 'BY' | 'BE' | 'BB' | 'MV' | 'SN' | 'ST' | 'TH';

export interface RegionForecast {
  code: Bundesland;
  name: string;
  /** Relative change in wave indicator over the next 7 days (0.12 = +12%) */
  delta7d: number;
  /** Event-probability (0..1) — calibrated wave-rising probability */
  pRising: number;
  /** Q10/Q50/Q90 of the 7d forecast, normalised to 100 = today */
  forecast: { q10: number; q50: number; q90: number };
  /** Short reason blurb for UI hover/detail */
  drivers: string[];
  /** Current GELO media spend EUR (weekly) */
  currentSpendEur: number;
  /** Recommended spend delta, EUR */
  recommendedShiftEur: number;
}

export interface ShiftRecommendation {
  id: string;
  fromCode: Bundesland;
  toCode: Bundesland;
  fromName: string;
  toName: string;
  amountEur: number;
  confidence: number; // 0..1
  expectedReachUplift: number; // 0..1
  why: string;
  primary?: boolean;
}

export interface TimelinePoint {
  /** ISO date */
  date: string;
  observed: number | null;    // null for future
  nowcast: number | null;     // only the shaded window (−14..0)
  q10: number;
  q50: number;
  q90: number;
  horizonDays: number;        // negative = past, 0 = today, +n = future
}

export interface SourceStatus {
  name: string;
  lastUpdate: string;   // ISO
  latencyDays: number;
  health: 'good' | 'delayed' | 'stale';
  note?: string;
}

export interface CockpitSnapshot {
  client: string;
  virusLabel: string;
  isoWeek: string;
  generatedAt: string;
  totalSpendEur: number;
  averageConfidence: number;
  primaryRecommendation: ShiftRecommendation;
  secondaryRecommendations: ShiftRecommendation[];
  regions: RegionForecast[];
  timeline: TimelinePoint[];
  sources: SourceStatus[];
  topDrivers: { label: string; value: string }[];
}
