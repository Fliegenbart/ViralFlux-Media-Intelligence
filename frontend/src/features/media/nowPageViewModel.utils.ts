import { explainInPlainGerman } from '../../lib/plainLanguage';
import {
  StructuredReasonItem,
  WorkspaceStatusSummary,
} from '../../types/media';
import { NowPageRecommendationState } from './useMediaData.types';

export function uniqueText(values: Array<string | null | undefined>, limit = 4): string[] {
  const seen = new Set<string>();

  return values
    .map((value) => String(value || '').trim())
    .filter((value) => {
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    })
    .slice(0, limit);
}

export function explainedEntries(
  values: Array<string | StructuredReasonItem | null | undefined>,
  limit = 4,
): string[] {
  const seen = new Set<string>();
  return values
    .map((value) => explainInPlainGerman(value))
    .filter((value) => {
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    })
    .slice(0, limit);
}

export function preferredReasonEntries(
  details?: StructuredReasonItem[] | null,
  fallback?: string[] | null,
): Array<string | StructuredReasonItem> {
  if (details && details.length > 0) return details;
  return fallback || [];
}

export function findReasonMentioningRegion(
  values: Array<string | StructuredReasonItem | null | undefined>,
  regionName?: string | null,
): string {
  const normalizedRegion = explainInPlainGerman(regionName).toLowerCase();
  return explainedEntries(values, values.length || 4).find((item) => (
    normalizedRegion ? item.toLowerCase().includes(normalizedRegion) : false
  )) || '';
}

export function cleanCopy(value?: string | StructuredReasonItem | null): string {
  return explainInPlainGerman(value);
}

export function firstCleanText(...values: Array<string | StructuredReasonItem | null | undefined>): string {
  return values.map((value) => cleanCopy(value)).find(Boolean) || '-';
}

export function textMentionsRegion(text: string, regionName?: string | null): boolean {
  const cleanedRegionName = cleanCopy(regionName);
  if (!text || !cleanedRegionName || cleanedRegionName === '-') return false;
  return text.toLowerCase().includes(cleanedRegionName.toLowerCase());
}

export function regionTrendLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'rising' || normalized === 'up' || normalized === 'steigend') return 'steigend';
  if (normalized === 'falling' || normalized === 'down' || normalized === 'fallend') return 'fallend';
  if (normalized === 'flat' || normalized === 'stabil') return 'stabil';
  return normalized || '';
}

export function regionSignalSentence(
  regionName?: string | null,
  signalScore?: number | null,
  trend?: string | null,
): string {
  const cleanedName = cleanCopy(regionName);
  const roundedScore = signalScore == null || Number.isNaN(signalScore) ? null : Math.round(signalScore);
  const trendLabel = regionTrendLabel(trend);

  if (cleanedName && roundedScore != null && trendLabel) {
    return `${cleanedName} zeigt mit ${roundedScore}/100 aktuell die größte Dynamik, der Trend wirkt ${trendLabel}.`;
  }
  if (cleanedName && roundedScore != null) {
    return `${cleanedName} liegt mit ${roundedScore}/100 im Wochenvergleich klar vorne.`;
  }
  return '';
}

export function buildNowPageNote(stage: string): string {
  if (stage === 'Aktivieren') {
    return 'Du kannst hier direkt in den nächsten Schritt gehen. Die wichtigsten Hinweise stehen direkt darunter.';
  }
  if (stage === 'Vorbereiten') {
    return 'Die Lage ist wichtig, aber noch nicht ganz freigegeben. Unten siehst du sofort, was du prüfen solltest.';
  }
  return 'Im Moment geht es vor allem um Beobachtung. Du siehst trotzdem direkt, welche Region zuerst wichtig wird und was noch offen ist.';
}

export function probabilityPercent(value?: number | null): number | null {
  if (value == null || Number.isNaN(value)) return null;
  return value <= 1 ? value * 100 : value;
}

export function stageLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'activate' || normalized === 'go') return 'Aktivieren';
  if (normalized === 'prepare') return 'Vorbereiten';
  return 'Beobachten';
}

export function stageTone(value?: string | null): 'success' | 'warning' | 'neutral' {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'activate' || normalized === 'go') return 'success';
  if (normalized === 'prepare') return 'warning';
  return 'neutral';
}

export function forecastStatusTone(value: string): 'success' | 'warning' | 'neutral' {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'stabil' || normalized === 'freigabe bereit') return 'success';
  if (normalized === 'beobachten') return 'warning';
  return 'neutral';
}

export function businessTrustTone(value: string): 'success' | 'warning' | 'neutral' {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'bereit') return 'success';
  if (normalized === 'im aufbau') return 'warning';
  return 'neutral';
}

export function recommendationStateLabel(state: NowPageRecommendationState): string {
  if (state === 'strong') return 'Bereit für Review';
  if (state === 'guarded') return 'Mit Vorsicht prüfen';
  if (state === 'weak') return 'Noch keine belastbare Empfehlung';
  return 'Vor Review blockiert';
}

export function deriveBriefingState({
  hasRegionalModel,
  hasActionableRecommendation,
  forecastTone,
  dataTone,
  businessTone,
  workspaceStatus,
  dataFreshnessValue,
}: {
  hasRegionalModel: boolean;
  hasActionableRecommendation: boolean;
  forecastTone: 'success' | 'warning' | 'neutral';
  dataTone: 'success' | 'warning' | 'neutral';
  businessTone: 'success' | 'warning' | 'neutral';
  workspaceStatus: WorkspaceStatusSummary | null;
  dataFreshnessValue: string;
}): {
  state: NowPageRecommendationState;
  stateLabel: string;
  actionHint: string | null;
  summary: string;
  stale: boolean;
  staleLabel: string | null;
  staleDetail: string | null;
} {
  const blockers = workspaceStatus?.blockers || [];
  const hasBlockers = (workspaceStatus?.blocker_count || 0) > 0 || blockers.length > 0;
  const stale = workspaceStatus?.data_freshness === 'Beobachten' || dataFreshnessValue === 'Beobachten';
  const strongSignals = forecastTone === 'success' && dataTone === 'success' && businessTone === 'success';
  const weakSignals = !hasRegionalModel
    || !hasActionableRecommendation
    || (forecastTone === 'neutral' && dataTone !== 'success' && businessTone === 'neutral');

  const state: NowPageRecommendationState = hasBlockers
    ? 'blocked'
    : strongSignals
      ? 'strong'
      : weakSignals
        ? 'weak'
        : 'guarded';

  const stateLabel = recommendationStateLabel(state);
  const actionHint = state === 'blocked'
    ? blockers[0] || 'Vor dem Review liegt noch mindestens ein offener Blocker vor.'
    : state === 'weak'
      ? 'Die Richtung ist sichtbar, aber die Datenlage reicht noch nicht für eine belastbare Wochenempfehlung.'
      : state === 'guarded'
        ? 'Die Empfehlung ist prüfbar, sollte aber noch mit Evidenz und Freigabe gespiegelt werden.'
        : null;
  const summary = state === 'blocked'
    ? 'Die Empfehlung ist sichtbar, aber vor dem Review liegen noch offene Punkte auf dem Tisch.'
    : state === 'strong'
      ? 'Forecast, Datenlage und Freigabe tragen die Empfehlung aktuell klar genug für den nächsten Review.'
      : state === 'weak'
        ? 'Es gibt erste Richtungen, aber noch keine wirklich belastbare Wochenempfehlung.'
        : 'Die Empfehlung ist vorhanden, braucht aber noch einen vorsichtigen Blick auf Evidenz und Freigabe.';

  return {
    state,
    stateLabel,
    actionHint,
    summary,
    stale,
    staleLabel: stale ? 'Daten nicht ganz frisch' : null,
    staleDetail: stale
      ? workspaceStatus?.items.find((item) => item.key === 'data_freshness')?.detail || 'Die Datenbasis braucht noch einen kurzen Frische-Check.'
      : null,
  };
}
