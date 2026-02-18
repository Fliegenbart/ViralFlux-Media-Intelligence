export type WorkflowStatus =
  | 'DRAFT'
  | 'READY'
  | 'APPROVED'
  | 'ACTIVATED'
  | 'DISMISSED'
  | 'EXPIRED';

export interface CampaignBudgetPreview {
  weekly_budget_eur?: number;
  shift_pct?: number;
  shift_value_eur?: number;
  total_flight_budget_eur?: number;
}

export interface CampaignPreview {
  campaign_name?: string;
  activation_window?: {
    start?: string | null;
    end?: string | null;
  };
  budget?: CampaignBudgetPreview;
  primary_kpi?: string;
  recommended_product?: string;
  mapping_status?: string;
  playbook_key?: string;
  playbook_title?: string;
  ai_generation_status?: string;
}

export interface RecommendationCard {
  id: string;
  status: WorkflowStatus | string;
  type: string;
  urgency_score: number;
  brand: string;
  product: string;
  region?: string;
  region_codes?: string[];
  budget_shift_pct: number;
  channel_mix: Record<string, number>;
  activation_window?: {
    start?: string | null;
    end?: string | null;
  };
  reason?: string;
  confidence?: number;
  campaign_name?: string;
  primary_kpi?: string;
  recommended_product?: string;
  mapping_status?: string;
  mapping_confidence?: number | null;
  mapping_reason?: string;
  mapping_rule_source?: string | null;
  condition_key?: string;
  condition_label?: string;
  mapping_candidate_product?: string | null;
  peix_context?: {
    region_code?: string;
    score?: number;
    band?: string;
    impact_probability?: number;
    drivers?: Array<{ label: string; strength_pct: number }>;
    trigger_event?: string;
  };
  playbook_key?: string;
  playbook_title?: string;
  trigger_snapshot?: {
    source?: string;
    event?: string;
    details?: string;
    lead_time_days?: number;
    values?: Record<string, number | string | boolean>;
  };
  guardrail_notes?: string[];
  ai_generation_status?: string;
  strategy_mode?: string;
  campaign_preview?: CampaignPreview;
  detail_url?: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CampaignChannelPlanItem {
  channel: string;
  role: string;
  share_pct: number;
  budget_eur?: number;
  formats?: string[];
  message_angle?: string;
  kpi_primary?: string;
  kpi_secondary?: string[];
}

export interface CampaignPack {
  meta?: {
    version?: string;
    generated_at?: string;
    generator?: string;
  };
  campaign?: {
    campaign_name?: string;
    objective?: string;
    status?: WorkflowStatus | string;
    priority?: string;
  };
  targeting?: {
    region_scope?: string;
    audience_segments?: string[];
  };
  activation_window?: {
    start?: string;
    end?: string;
    flight_days?: number;
  };
  budget_plan?: {
    weekly_budget_eur?: number;
    budget_shift_pct?: number;
    budget_shift_value_eur?: number;
    total_flight_budget_eur?: number;
    currency?: string;
  };
  channel_plan?: CampaignChannelPlanItem[];
  message_framework?: {
    hero_message?: string;
    support_points?: string[];
    compliance_note?: string;
    cta?: string;
    copy_status?: string;
    library_version?: string;
    library_source?: string;
  };
  playbook?: {
    key?: string;
    title?: string;
    kind?: string;
    message_direction?: string;
    condition_key?: string;
  };
  trigger_snapshot?: {
    source?: string;
    event?: string;
    details?: string;
    lead_time_days?: number;
    values?: Record<string, number | string | boolean>;
  };
  trigger_evidence?: {
    source?: string;
    event?: string;
    details?: string;
    lead_time_days?: number;
    confidence?: number;
  };
  product_mapping?: {
    recommended_product?: string;
    mapping_status?: string;
    mapping_confidence?: number | null;
    mapping_reason?: string;
    condition_key?: string;
    condition_label?: string;
    candidate_product?: string | null;
  };
  measurement_plan?: {
    primary_kpi?: string;
    secondary_kpis?: string[];
    reporting_cadence?: string;
    success_criteria?: string;
  };
  peix_context?: {
    region_code?: string;
    score?: number;
    band?: string;
    impact_probability?: number;
    drivers?: Array<{ label: string; strength_pct: number }>;
    trigger_event?: string;
  };
  ai_plan?: {
    campaign_name?: string;
    objective?: string;
    budget_shift_pct?: number;
    activation_window_days?: number;
    channel_plan?: CampaignChannelPlanItem[];
    keyword_clusters?: string[];
    creative_angles?: string[];
    kpi_targets?: {
      primary_kpi?: string;
      secondary_kpis?: string[];
      success_criteria?: string;
    };
    next_steps?: Array<{
      task?: string;
      owner?: string;
      eta?: string;
    }>;
    compliance_hinweis?: string;
  };
  guardrail_report?: {
    passed?: boolean;
    notes?: string[];
    applied_fixes?: string[];
  };
  ai_meta?: {
    generated_at?: string;
    model?: string;
    provider?: string;
    status?: string;
    fallback_used?: boolean;
    error?: string;
  };
  execution_checklist?: Array<{
    task?: string;
    owner?: string;
    eta?: string;
    status?: string;
  }>;
}

export interface RecommendationDetail extends RecommendationCard {
  campaign_pack: CampaignPack;
  trigger_evidence?: CampaignPack['trigger_evidence'];
  target_audience?: string[];
}

export interface CatalogProduct {
  id: number;
  brand: string;
  product_name: string;
  active: boolean;
  source_url?: string;
  last_seen_at?: string | null;
  updated_at?: string | null;
}

export interface ProductConditionMapping {
  mapping_id: number;
  brand: string;
  product_id: number;
  product_name: string;
  product_active: boolean;
  condition_key: string;
  condition_label: string;
  rule_source?: string;
  fit_score: number;
  mapping_reason?: string;
  is_approved: boolean;
  priority: number;
  notes?: string | null;
  updated_at?: string | null;
}

export interface SourceStatusItem {
  source_key: string;
  label: string;
  last_updated?: string | null;
  age_days?: number | null;
  sla_days: number;
  feed_reachable?: boolean;
  feed_status_color?: 'green' | 'red';
  freshness_state?: 'live' | 'stale' | 'no_data';
  is_live: boolean;
  status_color: 'green' | 'red';
}

export interface SourceStatusSummary {
  items: SourceStatusItem[];
  live_count: number;
  total: number;
  live_ratio: number;
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
  top_drivers: PeixDriver[];
  layer_contributions: Record<string, number>;
}

export interface PeixScoreSummary {
  national_score: number;
  national_band: string;
  national_impact_probability: number;
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

export interface BentoTile {
  id: string;
  title: string;
  value: string | number | null;
  unit?: string;
  subtitle?: string;
  impact_probability: number;
  data_source?: string;
  is_live?: boolean;
  last_updated?: string | null;
}
