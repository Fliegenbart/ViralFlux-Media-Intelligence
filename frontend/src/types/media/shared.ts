export type WorkflowStatus =
  | 'DRAFT'
  | 'READY'
  | 'APPROVED'
  | 'ACTIVATED'
  | 'DISMISSED'
  | 'EXPIRED';

export type CampaignLifecycleState =
  | 'PREPARE'
  | 'REVIEW'
  | 'APPROVE'
  | 'SYNC_READY'
  | 'LIVE'
  | 'EXPIRED'
  | 'ARCHIVED';

export interface MetricContract {
  label?: string;
  semantics?: string;
  source?: string;
  unit?: string;
  calibrated?: boolean;
  derived_from?: string;
  note?: string;
}

export type StructuredReasonParamPrimitive = string | number | boolean | null;
export type StructuredReasonParamValue =
  | StructuredReasonParamPrimitive
  | StructuredReasonParamPrimitive[];

export interface StructuredReasonItem {
  code: string;
  message: string;
  params?: Record<string, StructuredReasonParamValue>;
}

export interface SourceStatusItem {
  source_key: string;
  label: string;
  last_updated?: string | null;
  age_days?: number | null;
  sla_days: number;
  feed_reachable?: boolean;
  feed_status_color?: 'green' | 'amber' | 'red';
  freshness_state?: 'live' | 'stale' | 'no_data';
  is_live: boolean;
  status_color: 'green' | 'amber' | 'red';
}

export interface SourceStatusSummary {
  items: SourceStatusItem[];
  live_count: number;
  total: number;
  live_ratio: number;
}

export type WorkspaceStatusKey =
  | 'forecast_status'
  | 'data_freshness'
  | 'customer_data_status'
  | 'open_blockers';

export type WorkspaceStatusTone = 'success' | 'warning' | 'neutral';

export interface WorkspaceStatusItem {
  key: WorkspaceStatusKey;
  question: string;
  value: string;
  detail: string;
  tone: WorkspaceStatusTone;
}

export interface WorkspaceStatusSummary {
  forecast_status: string;
  data_freshness: string;
  customer_data_status: string;
  open_blockers: string;
  last_import_at: string | null;
  blocker_count: number;
  blockers: string[];
  summary: string;
  items: WorkspaceStatusItem[];
}

export interface PredictionNarrative {
  headline: string;
  supportingText: string;
  proofPoints: string[];
  cautionText: string;
  assertive: boolean;
}

export interface PeixDriver {
  label: string;
  strength_pct: number;
}

export interface PeixRegionScore {
  region_code: string;
  region_name: string;
  score_0_100: number;
  risk_band: string;
  impact_probability: number;
  score_semantics?: string;
  impact_probability_semantics?: string;
  impact_probability_deprecated?: boolean;
  field_contracts?: Record<string, MetricContract>;
  top_drivers: PeixDriver[];
  layer_contributions: Record<string, number>;
}

export interface PeixVirusScoreInfo {
  epi_score: number;
  weight: number;
  contribution: number;
}

export interface PeixContextSignalInfo {
  value: number;
  weight: number;
  contribution: number;
}

export interface PeixScoreSummary {
  national_score: number;
  national_band: string;
  national_impact_probability: number;
  score_semantics?: string;
  impact_probability_semantics?: string;
  impact_probability_deprecated?: boolean;
  virus_scores?: Record<string, PeixVirusScoreInfo>;
  context_signals?: Record<string, PeixContextSignalInfo>;
  confidence?: number;
  confidence_label?: string;
  weights_source?: string;
  field_contracts?: Record<string, MetricContract>;
  top_drivers: PeixDriver[];
  regions: Record<string, PeixRegionScore>;
  generated_at: string;
}

export interface RegionRecommendationRef {
  card_id: string;
  detail_url: string;
  status?: string;
  urgency_score?: number;
  brand?: string;
  product?: string;
}

export interface RegionTooltipData {
  region_name: string;
  recommendation_text: string;
  epi_outlook: string;
  recommended_product: string;
  peix_score: number;
  peix_band: string;
  impact_probability: number;
  urgency_label: string;
  trend: string;
  change_pct: number;
  virus_typ: string;
}

export interface BentoTile {
  id: string;
  title: string;
  value: string | number | null;
  unit?: string;
  subtitle?: string;
  signal_score?: number;
  impact_probability: number;
  score_semantics?: string;
  field_contracts?: Record<string, MetricContract>;
  data_source?: string;
  is_live?: boolean;
  last_updated?: string | null;
}
