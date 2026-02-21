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

export interface ProductAttributePayload {
  sku?: string | null;
  target_segments?: string[];
  conditions?: string[];
  forms?: string[];
  age_min_months?: number | null;
  age_max_months?: number | null;
  audience_mode?: 'b2c' | 'b2b' | 'both';
  channel_fit?: string[];
  compliance_notes?: string | null;
}

export interface CatalogProduct {
  id: number;
  brand: string;
  product_name: string;
  active: boolean;
  source_url?: string;
  source_hash?: string;
  last_seen_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  sku?: string | null;
  target_segments: string[];
  conditions: string[];
  forms: string[];
  age_min_months: number | null;
  age_max_months: number | null;
  audience_mode: 'b2c' | 'b2b' | 'both' | string;
  channel_fit: string[];
  compliance_notes: string | null;
  review_state: string;
  last_change: string | null;
}

export interface CatalogProductCreateInput {
  brand: string;
  product_name: string;
  source_url?: string;
  source_hash?: string;
  active: boolean;
  sku?: string | null;
  target_segments: string[];
  conditions: string[];
  forms: string[];
  age_min_months?: number | null;
  age_max_months?: number | null;
  audience_mode: 'b2c' | 'b2b' | 'both';
  channel_fit: string[];
  compliance_notes?: string | null;
  extra_data?: Record<string, unknown>;
}

export interface CatalogProductUpdateInput {
  brand?: string;
  product_name?: string;
  source_url?: string;
  source_hash?: string;
  active?: boolean;
  sku?: string | null;
  target_segments?: string[];
  conditions?: string[];
  forms?: string[];
  age_min_months?: number | null;
  age_max_months?: number | null;
  audience_mode?: 'b2c' | 'b2b' | 'both' | string;
  channel_fit?: string[];
  compliance_notes?: string | null;
  extra_data?: Record<string, unknown>;
  last_seen_at?: string | null;
}

export interface ProductMatchCandidate {
  opportunity_id: string;
  opportunity_type: string;
  status: string;
  region_target?: Record<string, unknown>;
  urgency_score?: number;
  trigger_event?: string;
  candidate_product?: string | null;
  recommended_product?: string | null;
  mapping_status: string;
  mapping_confidence?: number | null;
  mapping_reason?: string;
  condition_key?: string;
  condition_label?: string;
  rule_source?: string;
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

export interface DecisionFact {
  key: string;
  label: string;
  value: string | number | boolean | null;
  source?: string;
}

export interface DecisionExpectation {
  condition_key?: string;
  condition_label?: string;
  region_codes?: string[];
  impact_probability?: number;
  peix_score?: number;
  confidence_pct?: number;
  rationale?: string;
}

export interface DecisionRecommendation {
  primary_product?: string;
  primary_region?: string;
  secondary_regions?: string[];
  secondary_products?: string[];
  budget_shift_pct?: number;
  mapping_status?: string;
  mapping_reason?: string;
  action_required?: 'review_mapping' | 'ready_for_activation' | string;
}

export interface RecommendationDecisionBrief {
  summary_sentence?: string;
  horizon?: {
    min_days?: number;
    max_days?: number;
    model_lead_time_days?: number | null;
  };
  facts?: DecisionFact[];
  expectation?: DecisionExpectation;
  recommendation?: DecisionRecommendation;
}

export interface RecommendationDetail extends RecommendationCard {
  campaign_pack: CampaignPack;
  trigger_evidence?: CampaignPack['trigger_evidence'];
  target_audience?: string[];
  decision_brief?: RecommendationDecisionBrief;
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
  virus_scores?: Record<string, PeixVirusScoreInfo>;
  context_signals?: Record<string, PeixContextSignalInfo>;
  confidence?: number;
  confidence_label?: string;
  weights_source?: string;
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
  impact_probability: number;
  data_source?: string;
  is_live?: boolean;
  last_updated?: string | null;
}
