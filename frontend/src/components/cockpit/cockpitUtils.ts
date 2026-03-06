import { format, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';

import { BacktestResponse, RecommendationCard } from '../../types/media';
import { CampaignLaneId } from './types';

export const VIRUS_OPTIONS = ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A'];

export const WORKFLOW_TRANSITIONS: Record<string, string> = {
  DRAFT: 'READY',
  READY: 'APPROVED',
  APPROVED: 'ACTIVATED',
};

export const STATUS_ACTION_LABELS: Record<string, string> = {
  READY: 'In Prüfung geben',
  APPROVED: 'Freigeben',
  ACTIVATED: 'Als live markieren',
};

const KPI_LABELS: Record<string, string> = {
  Reach: 'Reichweite',
  CTR: 'Klickrate',
  'Qualified Clicks': 'Qualifizierte Klicks',
  'Qualified Visits': 'Qualifizierte Besuche',
  'Completed Views': 'Abgeschlossene Views',
  Awareness: 'Awareness',
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

export function statusTone(status?: string | null): { background: string; color: string; border: string } {
  const normalized = String(status || '').toUpperCase();
  if (normalized === 'ACTIVATED') {
    return {
      background: 'rgba(16, 185, 129, 0.10)',
      color: '#047857',
      border: '1px solid rgba(16, 185, 129, 0.24)',
    };
  }
  if (normalized === 'APPROVED') {
    return {
      background: 'rgba(10, 132, 255, 0.12)',
      color: 'var(--accent-violet)',
      border: '1px solid rgba(10, 132, 255, 0.24)',
    };
  }
  if (normalized === 'READY') {
    return {
      background: 'rgba(245, 158, 11, 0.12)',
      color: '#b45309',
      border: '1px solid rgba(245, 158, 11, 0.24)',
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
      background: 'rgba(16, 185, 129, 0.10)',
      color: '#047857',
      border: '1px solid rgba(16, 185, 129, 0.24)',
    };
  }
  return {
    background: 'rgba(245, 158, 11, 0.12)',
    color: '#b45309',
    border: '1px solid rgba(245, 158, 11, 0.24)',
  };
}

export function truthLayerLabel(backtest?: BacktestResponse | null): string {
  const points = Number(backtest?.metrics?.data_points || 0);
  if (points >= 52) return 'belastbar';
  if (points >= 26) return 'im Aufbau';
  if (points > 0) return 'erste Signale';
  return 'noch nicht angeschlossen';
}

export function recommendationLane(card: RecommendationCard): CampaignLaneId {
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
  if (normalized === 'DRAFT') return 'Vorbereitung';
  if (normalized === 'READY') return 'In Prüfung';
  if (normalized === 'APPROVED') return 'Freigegeben';
  if (normalized === 'ACTIVATED') return 'Live';
  return status ? String(status) : 'Status offen';
}

export function readinessStateLabel(state?: string | null, canSyncNow = false): string {
  if (canSyncNow) return 'Sync-bereit';

  const normalized = String(state || '').toLowerCase();
  if (normalized === 'ready') return 'Sync-bereit';
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
    return 'KI-Plan: Qwen lokal';
  }
  if (providerText.includes('openai') || modelText.includes('gpt')) {
    return 'KI-Plan: OpenAI';
  }
  if (providerText) {
    return `KI-Plan: ${String(provider || '').trim()}`;
  }
  if (modelText) {
    return `KI-Plan: ${String(model || '').trim()}`;
  }
  return 'KI-Plan';
}
