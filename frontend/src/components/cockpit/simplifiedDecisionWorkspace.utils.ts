import { NowPageViewModel } from '../../features/media/useMediaData.types';
import { RegionalForecastPrediction, RegionalForecastResponse } from '../../types/media';

export type SimplifiedDecisionState = 'go' | 'watch' | 'no_call';

export interface SimplifiedDecisionFact {
  label: 'Region' | 'Trend' | 'Vertrauen';
  value: string | undefined;
  detail?: string;
}

export interface SimplifiedDecisionModel {
  state: SimplifiedDecisionState;
  headline: string;
  summary: string;
  facts: SimplifiedDecisionFact[];
  detailSections: {
    why: string[];
    alternatives: string[];
    risks: string[];
  };
  focusPrediction: RegionalForecastPrediction | null;
}

export function uniqueItems(items: Array<string | null | undefined>): string[] {
  return Array.from(new Set(items.map((item) => (item || '').trim()).filter(Boolean)));
}

export function trendLabel(changePct?: number | null): 'Steigend' | 'Fallend' | 'Stabil' {
  if (changePct == null || Number.isNaN(changePct) || (changePct <= 5 && changePct >= -5)) {
    return 'Stabil';
  }
  return changePct > 5 ? 'Steigend' : 'Fallend';
}

export function findFocusPrediction(
  forecast: RegionalForecastResponse | null,
  regionCode?: string | null,
  regionName?: string | null,
): RegionalForecastPrediction | null {
  const predictions = forecast?.predictions || [];
  if (!predictions.length) return null;

  const code = regionCode ?? null;
  const name = regionName ?? null;

  if (code) {
    const byCode = predictions.find((prediction) => prediction.bundesland === code);
    if (byCode) return byCode;
  }

  if (name) {
    const byName = predictions.find((prediction) => prediction.bundesland_name === name);
    if (byName) return byName;
  }

  return predictions[0] || null;
}

function readRegionName(
  view: NowPageViewModel,
): string {
  return view.focusRegion?.name
    || view.heroRecommendation?.region
    || 'dieser Region';
}

function buildGoHeadline(regionName: string): string {
  return `Diese Woche Budget in ${regionName} erhoehen.`;
}

function buildWatchHeadline(regionName: string): string {
  return `Diese Woche ${regionName} weiter beobachten.`;
}

function buildFacts(
  view: NowPageViewModel,
  prediction: RegionalForecastPrediction | null,
): SimplifiedDecisionFact[] {
  return [
    {
      label: 'Region',
      value: readRegionName(view),
      detail: view.focusRegion?.reason || view.heroRecommendation?.whyNow || view.summary,
    },
    {
      label: 'Trend',
      value: trendLabel(prediction?.change_pct),
      detail: prediction?.change_pct != null ? `${prediction.change_pct}% Veränderung` : view.heroRecommendation?.context || '',
    },
    {
      label: 'Vertrauen',
      value: view.briefingTrust?.items?.[0]?.value || view.heroRecommendation?.stateLabel || 'Noch offen',
      detail: view.briefingTrust?.items?.[0]?.detail || undefined,
    },
  ];
}

function buildDetailSections(view: NowPageViewModel, summary: string): SimplifiedDecisionModel['detailSections'] {
  const secondaryMoves = (view.secondaryMoves || [])
    .slice(0, 3)
    .map((move) => `${move.name} · ${move.stage} · ${move.probabilityLabel}`);
  const relatedRegions = (view.relatedRegions || [])
    .slice(0, 3)
    .map((region) => `${region.name} · ${region.stage} · ${region.probabilityLabel}`);
  const riskItems = [
    ...(view.risks || []).slice(0, 3),
    ...(view.briefingTrust?.items || [])
      .filter((item) => item.tone !== 'success')
      .map((item) => `${item.label}: ${item.detail}`),
  ];

  return {
    why: uniqueItems([summary, ...(view.reasons || []).slice(0, 2)]),
    alternatives: uniqueItems([...secondaryMoves, ...relatedRegions]),
    risks: uniqueItems(riskItems),
  };
}

export function buildSimplifiedDecisionModel({
  view,
  forecast,
}: {
  view: NowPageViewModel;
  forecast: RegionalForecastResponse | null;
}): SimplifiedDecisionModel {
  const focusPrediction = findFocusPrediction(forecast, view.focusRegion?.code, view.focusRegion?.name);
  const state = view.heroRecommendation?.state === 'strong'
    ? 'go'
    : view.heroRecommendation?.state === 'weak'
      ? 'no_call'
      : 'watch';
  const regionName = readRegionName(view);
  const headline = state === 'go'
    ? buildGoHeadline(regionName)
    : state === 'watch'
      ? buildWatchHeadline(regionName)
      : 'Aktuell keine belastbare regionale Budgetempfehlung.';
  const summary = view.heroRecommendation?.whyNow
    || view.summary
    || view.note
    || 'Die aktuellen Signale werden noch eingeordnet.';

  return {
    state,
    headline,
    summary,
    facts: buildFacts(view, focusPrediction),
    detailSections: buildDetailSections(view, summary),
    focusPrediction,
  };
}
