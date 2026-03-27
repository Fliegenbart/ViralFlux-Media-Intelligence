import { CampaignLifecycleState, MetricContract, RegionRecommendationRef, RegionTooltipData, WorkflowStatus } from './shared';

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
  signal_score?: number;
  peix_score?: number;
  signal_confidence_pct?: number | null;
  confidence_pct?: number;
  event_probability_pct?: number | null;
  field_contracts?: Record<string, MetricContract>;
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

export interface RecommendationCard {
  id: string;
  status: WorkflowStatus | string;
  status_label?: string;
  evidence_class?: string;
  type: string;
  urgency_score: number;
  brand: string;
  product: string;
  region?: string;
  region_codes?: string[];
  region_codes_display?: string[];
  display_title?: string;
  budget_shift_pct: number;
  channel_mix: Record<string, number>;
  activation_window?: {
    start?: string | null;
    end?: string | null;
  };
  reason?: string;
  confidence?: number;
  signal_score?: number;
  priority_score?: number;
  signal_confidence_pct?: number | null;
  outcome_signal_score?: number | null;
  outcome_confidence_pct?: number | null;
  learning_state?: string;
  outcome_learning_scope?: string;
  outcome_learning_explanation?: string;
  observed_response?: {
    response_units?: number | null;
    response_per_1000_eur?: number | null;
    qualified_visits?: number | null;
    avg_search_lift_index?: number | null;
  } | null;
  learned_lifts?: Array<{ label: string; value?: number | null }>;
  field_contracts?: Record<string, MetricContract>;
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
    signal_score?: number;
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
  decision_brief?: RecommendationDecisionBrief;
  detail_url?: string;
  created_at?: string | null;
  updated_at?: string | null;
  expires_at?: string | null;
  is_supply_gap_active?: boolean;
  supply_gap_match_examples?: string;
  recommended_priority_multiplier?: number;
  supply_gap_product?: string;
  lifecycle_state?: CampaignLifecycleState | string;
  freshness_state?: 'scheduled' | 'current' | 'missing_window' | 'expired' | 'stale' | string;
  evidence_strength?: 'hoch' | 'mittel' | 'niedrig' | string;
  publish_blockers?: string[];
  is_publishable?: boolean;
  dedupe_group_id?: string;
  is_primary_variant?: boolean;
  decision_link?: string;
  variant_count?: number;
  variants?: Array<{
    id: string;
    status?: string;
    lifecycle_state?: CampaignLifecycleState | string;
    display_title?: string;
  }>;
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
  decision_brief?: RecommendationDecisionBrief;
}

export interface ConnectorCatalogItem {
  key: string;
  label: string;
  status: string;
  description?: string;
  supported_channels?: string[];
  supported_objectives?: string[];
}

export interface PreparedSyncPayload {
  opportunity_id: string;
  connector_key: string;
  connector_label: string;
  generated_at: string;
  available_connectors: ConnectorCatalogItem[];
  readiness: {
    state: 'ready' | 'approval_required' | 'needs_work' | string;
    can_sync_now: boolean;
    blockers: string[];
    warnings: string[];
    connector_status?: string;
  };
  normalized_package: {
    campaign_name?: string;
    workflow_status?: string;
    brand?: string;
    objective?: string;
    recommended_product?: string;
    region_codes?: string[];
    region_labels?: string[];
    audience_segments?: string[];
    primary_kpi?: string;
    secondary_kpis?: string[];
    budget_plan?: {
      weekly_budget_eur?: number;
      budget_shift_pct?: number;
      budget_shift_value_eur?: number;
      total_flight_budget_eur?: number;
      currency?: string;
    };
    activation_window?: {
      start?: string;
      end?: string;
      flight_days?: number;
    };
    channel_plan?: CampaignChannelPlanItem[];
    message_framework?: {
      hero_message?: string;
      support_points?: string[];
      cta?: string;
      compliance_note?: string;
    };
    creative_angles?: string[];
    keyword_clusters?: string[];
    next_steps?: Array<Record<string, unknown>>;
    playbook?: {
      key?: string;
      title?: string;
      kind?: string;
    };
    trigger?: {
      source?: string;
      event?: string;
      details?: string;
      lead_time_days?: number;
    };
    guardrails?: {
      passed?: boolean;
      notes?: string[];
      applied_fixes?: string[];
    };
  };
  connector_payload: Record<string, unknown>;
}
