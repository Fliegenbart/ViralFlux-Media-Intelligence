export interface PhaseLeadSummary {
  data_source: 'live_database';
  fit_mode: 'fast_initialization' | 'map_optimization';
  observation_count: number;
  window_start: string;
  window_end: string;
  converged: boolean;
  objective_value: number;
  data_vintage_hash: string;
  config_hash: string;
  top_region: string | null;
  warning_count: number;
}

export interface PhaseLeadSourceStatus {
  rows: number;
  latest_event_date: string | null;
  units: string[];
}

export interface PhaseLeadRegion {
  region_code: string;
  region: string;
  current_level: number;
  current_growth: number;
  p_up_h7: number;
  p_surge_h7: number;
  p_front: number;
  eeb: number;
  gegb: number;
  source_rows: number;
}

export interface PhaseLeadRankingItem {
  region_id: string;
  gegb: number;
}

export interface PhaseLeadAggregateWeight {
  virus_typ: string;
  weight: number;
  quality: number;
  observation_score?: number;
  coverage_score?: number;
  freshness_score?: number;
  model_score?: number;
  warning_factor?: number;
}

export interface PhaseLeadAggregateDriver {
  virus_typ: string;
  weight: number;
  signal: number;
  contribution: number;
}

export interface PhaseLeadAggregateMeta {
  kind: 'respiratory_pressure';
  weighting: 'data_quality';
  available_viruses: string[];
  fallback_viruses: string[];
  virus_weights: PhaseLeadAggregateWeight[];
  drivers_by_region: Record<string, PhaseLeadAggregateDriver[]>;
}

export interface PhaseLeadSnapshot {
  module: 'phase_lead_graph_renewal_filter';
  version: 'plgrf_live_v0' | 'plgrf_aggregate_v0';
  mode: 'research';
  as_of: string;
  virus_typ: string;
  horizons: number[];
  summary: PhaseLeadSummary;
  sources: Record<string, PhaseLeadSourceStatus>;
  regions: PhaseLeadRegion[];
  rankings: Record<string, PhaseLeadRankingItem[]>;
  warnings: string[];
  aggregate?: PhaseLeadAggregateMeta;
}
