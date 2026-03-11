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
