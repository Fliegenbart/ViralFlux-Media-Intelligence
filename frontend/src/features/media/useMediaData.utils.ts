import {
  MediaDecisionResponse,
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastPrediction,
  RegionalForecastResponse,
  RecommendationCard,
} from '../../types/media';

function numericValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function predictionRank(prediction: RegionalForecastPrediction): number {
  return Number(prediction.decision_rank ?? prediction.rank ?? Number.MAX_SAFE_INTEGER);
}

export function forecastAbsoluteGrowth(
  prediction: RegionalForecastPrediction | null | undefined,
): number | null {
  const current = numericValue(prediction?.current_known_incidence);
  const expected = numericValue(prediction?.expected_target_incidence);

  if (current == null || expected == null) {
    return null;
  }

  return expected - current;
}

export function deriveNowFocusRegionCode(
  decision: MediaDecisionResponse | null,
  forecast: RegionalForecastResponse | null,
  allocation: RegionalAllocationResponse | null,
  campaignRecommendations: RegionalCampaignRecommendationsResponse | null,
): string | null {
  const weeklyDecision = decision?.weekly_decision;
  const topCard = decision?.top_recommendations?.[0] || null;
  const strongestGrowthPrediction = findStrongestGrowthPrediction(forecast);
  const sortedPredictions = sortRegionalPredictions(forecast);
  return strongestGrowthPrediction?.bundesland
    || weeklyDecision?.top_regions?.[0]?.code
    || campaignRecommendations?.recommendations?.[0]?.bundesland
    || campaignRecommendations?.recommendations?.[0]?.region
    || topCard?.region_codes?.[0]
    || allocation?.recommendations?.[0]?.bundesland
    || sortedPredictions[0]?.bundesland
    || null;
}

export function findStrongestGrowthPrediction(
  forecast: RegionalForecastResponse | null | undefined,
): RegionalForecastPrediction | null {
  const positiveGrowthPredictions = (forecast?.predictions || []).filter((prediction) => {
    const growth = forecastAbsoluteGrowth(prediction);
    return growth != null && growth > 0;
  });

  if (!positiveGrowthPredictions.length) {
    return null;
  }

  return [...positiveGrowthPredictions].sort((left, right) => {
    const growthDelta = (forecastAbsoluteGrowth(right) || 0) - (forecastAbsoluteGrowth(left) || 0);
    if (growthDelta !== 0) return growthDelta;

    const expectedDelta = (numericValue(right.expected_target_incidence) || 0)
      - (numericValue(left.expected_target_incidence) || 0);
    if (expectedDelta !== 0) return expectedDelta;

    const probabilityDelta = (numericValue(right.event_probability) || 0)
      - (numericValue(left.event_probability) || 0);
    if (probabilityDelta !== 0) return probabilityDelta;

    return predictionRank(left) - predictionRank(right);
  })[0] || null;
}

export function findRecommendationCardForRegion(
  cards: RecommendationCard[] | null | undefined,
  regionCode?: string | null,
  regionName?: string | null,
): RecommendationCard | null {
  if (!cards?.length) return null;

  return cards.find((card) => (
    (regionCode && (
      card.region_codes?.includes(regionCode)
      || card.region === regionCode
      || card.decision_brief?.recommendation?.primary_region === regionCode
    ))
    || (regionName && (
      card.region === regionName
      || card.decision_brief?.recommendation?.primary_region === regionName
      || card.region_codes_display?.includes(regionName)
    ))
  )) || null;
}

export function sortRegionalPredictions(
  forecast: RegionalForecastResponse | null | undefined,
): RegionalForecastPrediction[] {
  return [...(forecast?.predictions || [])].sort((left, right) => {
    return predictionRank(left) - predictionRank(right);
  });
}
