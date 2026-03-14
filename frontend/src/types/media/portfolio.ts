export interface RegionalBenchmarkMetrics {
  precision_at_top3?: number;
  precision_at_top5?: number;
  pr_auc?: number;
  brier_score?: number;
  ece?: number;
  median_lead_days?: number;
  activation_false_positive_rate?: number;
  action_threshold?: number;
}

export interface RegionalQualityGate {
  overall_passed?: boolean;
  forecast_readiness?: string;
  checks?: Record<string, boolean>;
}

export interface RegionalBenchmarkItem {
  virus_typ: string;
  status: 'trained' | 'no_model' | string;
  trained_at?: string | null;
  states?: number;
  rows?: number;
  truth_source?: string | string[] | null;
  aggregate_metrics?: RegionalBenchmarkMetrics;
  quality_gate?: RegionalQualityGate;
  selection?: Record<string, unknown>;
  delta_vs_reference?: Record<string, number>;
  benchmark_score?: number;
  rank?: number;
}

export interface RegionalBenchmarkResponse {
  reference_virus: string;
  generated_at: string;
  trained_viruses: number;
  go_viruses: number;
  benchmark: RegionalBenchmarkItem[];
}

export interface RegionalPortfolioOpportunity {
  virus_typ: string;
  bundesland: string;
  bundesland_name: string;
  rank_within_virus: number;
  portfolio_action: 'activate' | 'prepare' | 'prioritize' | 'watch' | string;
  portfolio_intensity: 'high' | 'medium' | 'low' | string;
  portfolio_priority_score: number;
  event_probability_calibrated: number;
  expected_next_week_incidence: number;
  prediction_interval?: {
    lower?: number;
    upper?: number;
  };
  current_known_incidence?: number;
  change_pct?: number;
  trend?: string;
  quality_gate?: RegionalQualityGate;
  benchmark_rank?: number;
  benchmark_score?: number;
  aggregate_metrics?: RegionalBenchmarkMetrics;
  products: string[];
  channels: string[];
  as_of_date: string;
  target_week_start: string;
  rank?: number;
}

export interface RegionalPortfolioRegionRollup {
  bundesland: string;
  bundesland_name: string;
  leading_virus: string;
  leading_probability: number;
  leading_priority_score: number;
  top_signals: Array<{
    virus_typ: string;
    portfolio_action: string;
    portfolio_priority_score: number;
    event_probability_calibrated: number;
  }>;
}

export interface RegionalPortfolioVirusRollup {
  virus_typ: string;
  rank?: number;
  benchmark_score?: number;
  quality_gate?: RegionalQualityGate;
  aggregate_metrics?: RegionalBenchmarkMetrics;
  top_region?: string;
  top_region_name?: string;
  top_event_probability?: number;
  top_change_pct?: number;
  products?: string[];
}

export interface RegionalPortfolioResponse {
  generated_at: string;
  reference_virus: string;
  latest_as_of_date?: string | null;
  summary: {
    trained_viruses: number;
    go_viruses: number;
    total_opportunities: number;
    watchlist_opportunities: number;
    priority_opportunities: number;
    validated_opportunities: number;
  };
  benchmark: RegionalBenchmarkItem[];
  virus_rollup: RegionalPortfolioVirusRollup[];
  region_rollup: RegionalPortfolioRegionRollup[];
  top_opportunities: RegionalPortfolioOpportunity[];
}
