import {
  BacktestResponse,
  BentoTile,
  PeixScoreSummary,
  RecommendationCard,
  RegionRecommendationRef,
  RegionTooltipData,
  SourceStatusSummary,
} from '../../types/media';

export interface MapRegion {
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
  field_contracts?: Record<string, { semantics?: string; source?: string }>;
}

export interface CockpitResponse {
  bento: { tiles: BentoTile[]; count: number };
  peix_epi_score: PeixScoreSummary;
  source_status: SourceStatusSummary;
  map: {
    has_data: boolean;
    date: string | null;
    max_viruslast: number;
    regions: Record<string, MapRegion>;
    top_regions: Array<{ code: string } & MapRegion>;
    activation_suggestions: Array<{
      region: string;
      region_name: string;
      priority: string;
      signal_score?: number;
      priority_score?: number;
      budget_shift_pct: number;
      channel_mix: Record<string, number>;
      reason: string;
      score_semantics?: string;
      field_contracts?: Record<string, { semantics?: string; source?: string }>;
    }>;
  };
  recommendations: { total: number; cards: RecommendationCard[] };
  backtest_summary: {
    latest_market: BacktestResponse | null;
    latest_customer: BacktestResponse | null;
    recent_runs: Array<Record<string, unknown>>;
  };
  data_freshness: Record<string, string | null>;
}

export type MediaCockpitView = 'decision' | 'regions' | 'campaigns' | 'evidence';

export type CampaignLaneId = 'prepare' | 'review' | 'approve' | 'sync' | 'live';

export interface CampaignLane {
  id: CampaignLaneId;
  label: string;
  description: string;
}

export const CAMPAIGN_LANES: CampaignLane[] = [
  { id: 'prepare', label: 'Entwuerfe', description: 'Neue Vorschlaege und offene Vorarbeit' },
  { id: 'review', label: 'Zu pruefen', description: 'Inhalt, Timing und Hinweise pruefen' },
  { id: 'approve', label: 'Zur Freigabe', description: 'Entscheidungsreife Vorschlaege' },
  { id: 'sync', label: 'Zur Uebergabe', description: 'Freigegeben und fuer Mediatools vorbereitet' },
  { id: 'live', label: 'Aktiv', description: 'Bereits freigegeben oder ausgespielt' },
];
