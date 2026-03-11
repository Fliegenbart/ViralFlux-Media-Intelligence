import { MetricContract, RegionRecommendationRef, RegionTooltipData } from './shared';

export interface MediaRegionsResponse {
  virus_typ: string;
  target_source: string;
  generated_at: string;
  map: {
    has_data: boolean;
    date: string | null;
    max_viruslast: number;
    regions: Record<string, {
      name: string;
      avg_viruslast: number;
      intensity: number;
      trend: string;
      change_pct: number;
      n_standorte: number;
      peix_score?: number;
      peix_band?: string;
      impact_probability?: number;
      signal_score?: number;
      recommendation_ref?: RegionRecommendationRef | null;
      tooltip?: RegionTooltipData | null;
      forecast_direction?: string;
      severity_score?: number;
      momentum_score?: number;
      actionability_score?: number;
      signal_drivers?: Array<{ label: string; strength_pct: number }>;
      layer_contributions?: Record<string, number>;
      budget_logic?: string;
      priority_explanation?: string;
      decision_mode?: string;
      decision_mode_label?: string;
      decision_mode_reason?: string;
      priority_rank?: number;
      source_trace?: string[];
      field_contracts?: Record<string, MetricContract>;
    }>;
    top_regions: Array<{
      code: string;
      name: string;
      trend: string;
      impact_probability?: number;
      signal_score?: number;
      peix_score?: number;
      severity_score?: number;
      momentum_score?: number;
      actionability_score?: number;
      decision_mode?: string;
      decision_mode_label?: string;
      priority_rank?: number;
      recommendation_ref?: RegionRecommendationRef | null;
      tooltip?: RegionTooltipData | null;
      field_contracts?: Record<string, MetricContract>;
    }>;
    activation_suggestions: Array<{
      region: string;
      region_name: string;
      priority: string;
      signal_score?: number;
      priority_score?: number;
      impact_probability?: number;
      budget_shift_pct: number;
      channel_mix: Record<string, number>;
      reason: string;
      score_semantics?: string;
      field_contracts?: Record<string, MetricContract>;
    }>;
  };
  top_regions: Array<{
    code: string;
    name: string;
    trend: string;
    impact_probability?: number;
    signal_score?: number;
    peix_score?: number;
    recommendation_ref?: RegionRecommendationRef | null;
    tooltip?: RegionTooltipData | null;
  }>;
  decision_state?: string;
}
