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
  recommendation_ref?: RegionRecommendationRef | null;
  tooltip?: RegionTooltipData | null;
  forecast_direction?: string;
  signal_drivers?: Array<{ label: string; strength_pct: number }>;
  layer_contributions?: Record<string, number>;
  budget_logic?: string;
  priority_explanation?: string;
  source_trace?: string[];
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
      budget_shift_pct: number;
      channel_mix: Record<string, number>;
      reason: string;
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
  { id: 'prepare', label: 'Vorbereiten', description: 'Signale und Drafts vorbereiten' },
  { id: 'review', label: 'Review', description: 'Guardrails, Mapping und Evidence prüfen' },
  { id: 'approve', label: 'Ready to Approve', description: 'Freigabefähige Pakete' },
  { id: 'sync', label: 'Ready to Sync', description: 'Approved und connector-ready' },
  { id: 'live', label: 'Live', description: 'Bereits aktiviert' },
];
