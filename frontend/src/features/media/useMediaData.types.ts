import { PredictionNarrative } from '../../types/media';

export function noop() {}

export interface ToastLike {
  (message: string, type?: 'success' | 'error' | 'info'): void;
}

export interface NowPageMetric {
  label: string;
  value: string;
  tone: 'success' | 'warning' | 'neutral';
}

export interface NowPageTrustCheck {
  key: 'forecast' | 'data' | 'business';
  question: string;
  value: string;
  detail: string;
  tone: 'success' | 'warning' | 'neutral';
}

export interface NowPageFocusRegion {
  code: string | null;
  name: string;
  stage: string;
  reason: string;
  product: string;
  probabilityLabel: string;
  budgetLabel: string;
  recommendationId: string | null;
}

export interface NowPageRelatedRegion {
  code: string;
  name: string;
  stage: string;
  probabilityLabel: string;
  reason: string;
}

export type NowPageRecommendationState = 'strong' | 'guarded' | 'weak' | 'blocked';

export interface NowPageHeroRecommendation {
  headline: string;
  actionLabel: string;
  direction: string;
  region: string;
  regionCode: string | null;
  context: string;
  whyNow: string;
  state: NowPageRecommendationState;
  stateLabel: string;
  actionHint: string | null;
  ctaDisabled: boolean;
}

export interface NowPageSecondaryMove {
  code: string;
  name: string;
  stage: string;
  probabilityLabel: string;
  reason: string;
}

export interface NowPageBriefingTrustItem {
  key: 'reliability' | 'evidence' | 'readiness';
  label: string;
  value: string;
  detail: string;
  tone: 'success' | 'warning' | 'neutral';
}

export interface NowPageBriefingTrust {
  summary: string;
  items: NowPageBriefingTrustItem[];
}

export interface NowPageSupportState {
  stale: boolean;
  label: string | null;
  detail: string | null;
}

export interface NowPageViewModel {
  hasData: boolean;
  generatedAt: string | null;
  title: string;
  summary: string;
  note: string;
  proof: PredictionNarrative | null;
  primaryActionLabel: string;
  primaryRecommendationId: string | null;
  heroRecommendation: NowPageHeroRecommendation | null;
  secondaryMoves: NowPageSecondaryMove[];
  briefingTrust: NowPageBriefingTrust;
  supportState: NowPageSupportState;
  primaryCampaignTitle: string;
  primaryCampaignContext: string;
  primaryCampaignCopy: string;
  focusRegion: NowPageFocusRegion | null;
  metrics: NowPageMetric[];
  trustChecks: NowPageTrustCheck[];
  reasons: string[];
  risks: string[];
  quality: Array<{ label: string; value: string }>;
  relatedRegions: NowPageRelatedRegion[];
  emptyState: {
    title: string;
    body: string;
  } | null;
}
