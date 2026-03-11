import { RecommendationCard } from './recommendations';

export interface MediaCampaignsResponse {
  generated_at: string;
  cards: RecommendationCard[];
  archived_cards: RecommendationCard[];
  summary: {
    total_cards: number;
    active_cards: number;
    deduped_cards: number;
    publishable_cards: number;
    expired_cards: number;
    visible_cards?: number;
    hidden_backlog_cards?: number;
    states: Record<string, number>;
    learning_state?: string;
    outcome_signal_score?: number | null;
    outcome_confidence_pct?: number | null;
  };
}
