import {
  MediaDecisionResponse,
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastPrediction,
  RegionalForecastResponse,
} from '../../types/media';

export function deriveNowFocusRegionCode(
  decision: MediaDecisionResponse | null,
  forecast: RegionalForecastResponse | null,
  allocation: RegionalAllocationResponse | null,
  campaignRecommendations: RegionalCampaignRecommendationsResponse | null,
): string | null {
  const weeklyDecision = decision?.weekly_decision;
  const topCard = decision?.top_recommendations?.[0] || null;
  const sortedPredictions = sortRegionalPredictions(forecast);
  return weeklyDecision?.top_regions?.[0]?.code
    || campaignRecommendations?.recommendations?.[0]?.bundesland
    || campaignRecommendations?.recommendations?.[0]?.region
    || topCard?.region_codes?.[0]
    || allocation?.recommendations?.[0]?.bundesland
    || sortedPredictions[0]?.bundesland
    || null;
}

export function sortRegionalPredictions(
  forecast: RegionalForecastResponse | null | undefined,
): RegionalForecastPrediction[] {
  return [...(forecast?.predictions || [])].sort((left, right) => {
    const leftRank = Number(left.decision_rank ?? left.rank ?? Number.MAX_SAFE_INTEGER);
    const rightRank = Number(right.decision_rank ?? right.rank ?? Number.MAX_SAFE_INTEGER);
    return leftRank - rightRank;
  });
}
