import { format, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';

import { OPERATOR_LABELS } from '../../constants/operatorLabels';
import { UI_COPY } from '../../lib/copy';
import { BacktestResponse, MetricContract, RecommendationCard, TruthCoverage } from '../../types/media';
import { CampaignLaneId } from './types';

export const VIRUS_OPTIONS = ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A'];

export const WORKFLOW_TRANSITIONS: Record<string, string> = {
  DRAFT: 'READY',
  READY: 'APPROVED',
  APPROVED: 'ACTIVATED',
};

export const STATUS_ACTION_LABELS: Record<string, string> = {
  READY: 'Zur Prüfung geben',
  APPROVED: 'Freigeben',
  ACTIVATED: 'Als aktiv markieren',
};

const KPI_LABELS: Record<string, string> = {
  Reach: 'Reichweite',
  CTR: 'Klickrate',
  'Qualified Clicks': 'Qualifizierte Klicks',
  'Qualified Visits': 'Qualifizierte Besuche',
  'Completed Views': 'Vollständige Videoaufrufe',
  Awareness: 'Bekanntheit',
};

const METRIC_SEMANTIC_LABELS: Record<string, string> = {
  ranking_signal: OPERATOR_LABELS.ranking_signal,
  activation_priority: OPERATOR_LABELS.activation_priority,
  signal_confidence: OPERATOR_LABELS.signal_confidence,
  forecast_event_probability: OPERATOR_LABELS.forecast_event_probability,
  observed_outcome_signal: OPERATOR_LABELS.observed_outcome_signal,
  outcome_learning_confidence: OPERATOR_LABELS.outcome_learning_confidence,
  truth_readiness: OPERATOR_LABELS.truth_readiness,
  business_validation_gate: OPERATOR_LABELS.business_validation_gate,
  business_evidence_tier: OPERATOR_LABELS.business_evidence_tier,
};

const METRIC_SEMANTIC_BADGES: Record<string, string> = {
  ranking_signal: OPERATOR_LABELS.ranking_signal,
  activation_priority: OPERATOR_LABELS.activation_priority,
  signal_confidence: OPERATOR_LABELS.signal_confidence,
  forecast_event_probability: OPERATOR_LABELS.forecast_event_probability,
  observed_outcome_signal: OPERATOR_LABELS.observed_outcome_signal,
  outcome_learning_confidence: OPERATOR_LABELS.outcome_learning_confidence,
  truth_readiness: OPERATOR_LABELS.truth_readiness,
  business_validation_gate: OPERATOR_LABELS.business_validation_gate,
  business_evidence_tier: OPERATOR_LABELS.business_evidence_tier,
};

const METRIC_SEMANTIC_NOTES: Record<string, string> = {
  ranking_signal: 'Hilft beim Vergleichen und Priorisieren, ist aber keine Eintrittswahrscheinlichkeit.',
  activation_priority: 'Ordnet, welcher Arbeitsfall zuerst geprüft werden sollte. Das ist keine Wahrscheinlichkeitszahl.',
  signal_confidence: 'Beschreibt, wie stabil das Signal wirkt, nicht die Modellwahrscheinlichkeit.',
  forecast_event_probability: 'Beschreibt die kalibrierte Wahrscheinlichkeit für das definierte Forecast-Ereignis.',
  observed_outcome_signal: 'Beschreibt ein beobachtetes Wirkungssignal aus Kundendaten, keine Forecast-Wahrscheinlichkeit.',
  outcome_learning_confidence: 'Beschreibt die Sicherheit des Outcome-Lernsignals, nicht die Modellkalibrierung.',
  truth_readiness: 'Beschreibt, wie belastbar der Kundendaten-Layer bereits angeschlossen ist.',
  business_validation_gate: 'Beschreibt, ob aus einem Signal schon eine operative Freigabe werden darf.',
  business_evidence_tier: 'Beschreibt den Reifegrad der Business- und Outcome-Evidenz.',
};

export function formatDateTime(value?: string | null): string {
  if (!value) return '-';
  try {
    return format(parseISO(value), 'dd.MM.yyyy HH:mm', { locale: de });
  } catch {
    return value;
  }
}

export function formatDateShort(value?: string | null): string {
  if (!value) return '-';
  try {
    return format(parseISO(value), 'dd.MM.yyyy', { locale: de });
  } catch {
    return value;
  }
}

export function formatCurrency(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  return `${value.toFixed(digits)}%`;
}

export function primarySignalScore(
  item?: { signal_score?: number | null; peix_score?: number | null; impact_probability?: number | null } | null,
): number {
  if (!item) return 0;
  return Number(item.signal_score ?? item.peix_score ?? item.impact_probability ?? 0);
}

export function signalConfidencePercent(
  signalConfidencePct?: number | null,
  confidence?: number | null,
): number | null {
  if (signalConfidencePct != null && !Number.isNaN(signalConfidencePct)) {
    return Math.round(signalConfidencePct);
  }
  if (confidence == null || Number.isNaN(confidence)) return null;
  return Math.round(confidence <= 1 ? confidence * 100 : confidence);
}

function metricContract(
  contracts: Record<string, MetricContract> | undefined,
  key: string,
): MetricContract | undefined {
  return contracts?.[key];
}

export function metricContractLabel(
  contracts: Record<string, MetricContract> | undefined,
  key: string,
  fallback: string,
): string {
  const label = metricContract(contracts, key)?.label;
  return typeof label === 'string' && label.trim().length > 0 ? label : fallback;
}

export function metricContractSemantics(
  contracts: Record<string, MetricContract> | undefined,
  key: string,
): string | null {
  const semantics = metricContract(contracts, key)?.semantics;
  return typeof semantics === 'string' && semantics.trim().length > 0 ? semantics : null;
}

export function metricContractDisplayLabel(
  contracts: Record<string, MetricContract> | undefined,
  key: string,
  fallback: string,
): string {
  const semantics = metricContractSemantics(contracts, key);
  if (semantics && METRIC_SEMANTIC_LABELS[semantics]) {
    return METRIC_SEMANTIC_LABELS[semantics];
  }
  return metricContractLabel(contracts, key, fallback);
}

export function metricContractBadge(
  contracts: Record<string, MetricContract> | undefined,
  key: string,
  fallback = 'Kennzahl',
): string {
  const semantics = metricContractSemantics(contracts, key);
  if (semantics && METRIC_SEMANTIC_BADGES[semantics]) {
    return METRIC_SEMANTIC_BADGES[semantics];
  }
  return fallback;
}

export function metricContractNote(
  contracts: Record<string, MetricContract> | undefined,
  key: string,
  fallback = 'Die Bedeutung dieser Kennzahl ist noch nicht dokumentiert.',
): string {
  const semantics = metricContractSemantics(contracts, key);
  if (semantics && METRIC_SEMANTIC_NOTES[semantics]) {
    return METRIC_SEMANTIC_NOTES[semantics];
  }
  const note = metricContract(contracts, key)?.note;
  if (typeof note === 'string' && note.trim().length > 0) {
    return note;
  }
  return fallback;
}

export function statusTone(status?: string | null): { background: string; color: string; border: string } {
  const normalized = String(status || '').toUpperCase();
  if (normalized === 'ACTIVATED' || normalized === 'LIVE') {
    return {
      background: 'var(--status-success-bg, rgba(16, 185, 129, 0.10))',
      color: 'var(--status-success, #047857)',
      border: '1px solid rgba(16, 185, 129, 0.24)',
    };
  }
  if (normalized === 'APPROVED' || normalized === 'SYNC_READY') {
    return {
      background: 'rgba(10, 132, 255, 0.12)',
      color: 'var(--accent-violet)',
      border: '1px solid rgba(10, 132, 255, 0.24)',
    };
  }
  if (normalized === 'READY' || normalized === 'APPROVE') {
    return {
      background: 'var(--status-success-bg, rgba(16, 185, 129, 0.08))',
      color: 'var(--status-success, #047857)',
      border: '1px solid rgba(16, 185, 129, 0.20)',
    };
  }
  if (normalized === 'REVIEW') {
    return {
      background: 'var(--status-warning-bg, rgba(245, 158, 11, 0.12))',
      color: 'var(--status-warning, #b45309)',
      border: '1px solid rgba(245, 158, 11, 0.24)',
    };
  }
  if (normalized === 'EXPIRED' || normalized === 'ARCHIVED') {
    return {
      background: 'rgba(99, 102, 241, 0.08)',
      color: 'var(--text-muted)',
      border: '1px solid rgba(148, 163, 184, 0.24)',
    };
  }
  return {
    background: 'rgba(10, 132, 255, 0.10)',
    color: 'var(--accent-violet)',
    border: '1px solid rgba(10, 132, 255, 0.2)',
  };
}

export function readinessTone(isGo: boolean): { background: string; color: string; border: string } {
  if (isGo) {
    return {
      background: 'var(--status-success-bg, rgba(16, 185, 129, 0.10))',
      color: 'var(--status-success, #047857)',
      border: '1px solid rgba(16, 185, 129, 0.24)',
    };
  }
  return {
    background: 'var(--status-warning-bg, rgba(245, 158, 11, 0.12))',
    color: 'var(--status-warning, #b45309)',
    border: '1px solid rgba(245, 158, 11, 0.24)',
  };
}

export function truthLayerLabel(backtestOrCoverage?: BacktestResponse | TruthCoverage | null): string {
  const readiness = String((backtestOrCoverage as TruthCoverage | undefined)?.trust_readiness || '').trim().toLowerCase();
  if (readiness === 'belastbar') return 'belastbar';
  if (readiness === 'im_aufbau') return 'im Aufbau';
  if (readiness === 'erste_signale') return 'erste Signale';
  if (readiness === 'noch_nicht_angeschlossen') return 'noch nicht angeschlossen';

  const coverageWeeks = Number((backtestOrCoverage as TruthCoverage | undefined)?.coverage_weeks || 0);
  if (coverageWeeks > 0) {
    if (coverageWeeks >= 52) return 'belastbar';
    if (coverageWeeks >= 26) return 'im Aufbau';
    return 'erste Signale';
  }

  const points = Number((backtestOrCoverage as BacktestResponse | undefined)?.metrics?.data_points || 0);
  if (points >= 52) return 'belastbar';
  if (points >= 26) return 'im Aufbau';
  if (points > 0) return 'erste Signale';
  return 'noch nicht angeschlossen';
}

export function truthFreshnessLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'fresh') return 'aktuell';
  if (normalized === 'stale') return 'veraltet';
  if (normalized === 'missing') return 'noch keine Kundendaten';
  if (normalized === 'unknown') return 'noch unklar';
  return normalized || '-';
}

export function learningStateLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'belastbar') return 'belastbar';
  if (normalized === 'im_aufbau') return 'im Aufbau';
  if (normalized === 'explorative') return 'explorativ';
  if (normalized === 'missing') return 'noch nicht angeschlossen';
  if (normalized === 'stale') return 'veraltet';
  return value ? String(value) : '-';
}

export function businessValidationLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'passed_holdout_validation') return 'mit Vergleichsgruppe bestätigt';
  if (normalized === 'pending_holdout_validation') return 'Vergleichsgruppe bereit';
  if (normalized === 'pending_holdout_design') return 'Vergleichsgruppe fehlt';
  if (normalized === 'pending_activation_history') return 'zu wenig Kampagnenhistorie';
  if (normalized === 'building_truth_layer') return 'Kundendatenbasis im Aufbau';
  if (normalized === 'pending_truth_connection') return 'noch nicht angeschlossen';
  return value ? String(value) : '-';
}

export function evidenceTierLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'commercially_validated') return 'kommerziell bestätigt';
  if (normalized === 'holdout_ready') return 'Vergleichsgruppe bereit';
  if (normalized === 'truth_backed') return 'durch Kundendaten gestützt';
  if (normalized === 'observational') return 'beobachtend';
  if (normalized === 'no_truth') return 'keine Kundendatenbasis';
  return value ? String(value) : '-';
}

export function decisionScopeLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'validated_budget_activation') return 'Budgetfreigabe möglich';
  if (normalized === 'decision_support_only') return 'nur Entscheidungshilfe';
  return value ? String(value) : '-';
}

export function recommendationLane(card: RecommendationCard): CampaignLaneId {
  const lifecycle = String(card.lifecycle_state || '').toUpperCase();
  if (lifecycle === 'LIVE') return 'live';
  if (lifecycle === 'SYNC_READY') return 'sync';
  if (lifecycle === 'APPROVE') return 'approve';
  if (lifecycle === 'REVIEW') return 'review';
  if (lifecycle === 'EXPIRED' || lifecycle === 'ARCHIVED') return 'prepare';

  const status = String(card.status || '').toUpperCase();
  if (status === 'ACTIVATED') return 'live';
  if (status === 'APPROVED') return 'sync';
  if (status === 'READY') return 'approve';
  if (status === 'NEW' || status === 'URGENT') return 'review';
  if (String(card.mapping_status || '').toLowerCase() === 'needs_review') return 'review';
  return 'prepare';
}

export function nextWorkflowStatus(status?: string | null): string | null {
  const normalized = String(status || '').toUpperCase();
  return WORKFLOW_TRANSITIONS[normalized] || null;
}

export function workflowLabel(status?: string | null): string {
  const normalized = String(status || '').toUpperCase();
  if (normalized === 'DRAFT' || normalized === 'PREPARE') return 'Entwurf';
  if (normalized === 'READY' || normalized === 'REVIEW') return 'Zu prüfen';
  if (normalized === 'APPROVE') return 'Zur Freigabe';
  if (normalized === 'APPROVED' || normalized === 'SYNC_READY') return 'Bereit zur Übergabe';
  if (normalized === 'ACTIVATED' || normalized === 'LIVE') return 'Aktiv';
  if (normalized === 'EXPIRED') return 'Abgelaufen';
  if (normalized === 'ARCHIVED' || normalized === 'DISMISSED') return 'Archiviert';
  return status ? String(status) : 'Status offen';
}

export function readinessStateLabel(state?: string | null, canSyncNow = false): string {
  if (canSyncNow) return 'Bereit zur Übergabe';

  const normalized = String(state || '').toLowerCase();
  if (normalized === 'ready') return 'Bereit zur Übergabe';
  if (normalized === 'approval_required') return 'Freigabe nötig';
  if (normalized === 'needs_work') return 'Nachschärfen';
  if (normalized === 'review') return 'In Prüfung';
  return state ? String(state) : 'In Prüfung';
}

export function kpiLabel(value?: string | null): string {
  const raw = String(value || '').trim();
  if (!raw) return 'noch offen';
  return KPI_LABELS[raw] || raw;
}

export function aiModelLabel(provider?: string | null, model?: string | null): string {
  const providerText = String(provider || '').trim().toLowerCase();
  const modelText = String(model || '').trim().toLowerCase();

  if (providerText.includes('qwen') || modelText.includes('qwen')) {
    return `${UI_COPY.ai}-Unterstützung: lokal`;
  }
  if (providerText.includes('openai') || modelText.includes('gpt')) {
    return `${UI_COPY.ai}-Unterstützung: OpenAI`;
  }
  if (providerText) {
    return `${UI_COPY.ai}-Unterstützung: ${String(provider || '').trim()}`;
  }
  if (modelText) {
    return `${UI_COPY.ai}-Plan: ${String(model || '').trim()}`;
  }
  return `${UI_COPY.ai}-Plan`;
}
