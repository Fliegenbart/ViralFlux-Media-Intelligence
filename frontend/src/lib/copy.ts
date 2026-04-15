import { OPERATOR_LABELS } from '../constants/operatorLabels';

export const UI_COPY = {
  ai: 'KI',
  signalScore: OPERATOR_LABELS.ranking_signal,
  signalScoreWithSource: `${OPERATOR_LABELS.ranking_signal} (Ranking-Signal)`,
  eventProbability: OPERATOR_LABELS.forecast_event_probability,
  decisionPriority: OPERATOR_LABELS.activation_priority,
  uncertainty: 'Unsicherheit',
  insufficientTruth: 'Zu wenig Kundendaten-Evidenz',
  insufficientEvidence: 'Zu wenig Evidenz',
  stateLevelScope: 'Bundesland-Ansicht',
  noCityForecast: 'Keine Stadt-Prognose',
  marketComparison: 'Marktvergleich',
  customerData: 'Kundendaten',
  customerDataFreshness: 'Stand Kundendaten',
  additionalSuggestions: 'Weitere Vorschläge',
  handoff: 'Übergabe',
  weeklyReport: 'Bericht exportieren',
  defaultCampaignGoal: 'Sichtbarkeit aufbauen, bevor die Nachfrage steigt',
} as const;

export const COCKPIT_SEMANTICS = {
  eventProbability: {
    label: `${OPERATOR_LABELS.forecast_event_probability} (Forecast)`,
    badge: OPERATOR_LABELS.forecast_event_probability,
    helper: 'Schätzt, wie wahrscheinlich das definierte Ereignis ist und ist kein Rangplatz.',
  },
  rankingSignal: {
    label: `${OPERATOR_LABELS.ranking_signal} (Ranking-Signal)`,
    badge: OPERATOR_LABELS.ranking_signal,
    helper: 'Hilft beim Vergleichen von Bundesländern und ist keine Event-Wahrscheinlichkeit.',
  },
  decisionPriority: {
    label: `${OPERATOR_LABELS.activation_priority} (Entscheidungs-Priorität)`,
    badge: OPERATOR_LABELS.activation_priority,
    helper: 'Zeigt, was zuerst geprüft werden sollte und ist keine Prozentzahl.',
  },
  uncertainty: {
    label: 'Unsicherheit',
    badge: 'Unsicherheit mit Text',
    helper: 'Unsicherheit wird immer zusätzlich erklärt und nie nur über Farbe gezeigt.',
  },
  insufficientTruth: {
    label: 'Zu wenig Kundendaten-Evidenz',
    badge: 'Kundendaten noch zu dünn',
    helper: 'Es gibt noch nicht genug Kundendaten, um das Signal verlässlich abzustützen.',
  },
  insufficientEvidence: {
    label: 'Zu wenig Evidenz',
    badge: 'Zu wenig Evidenz',
    helper: 'Es gibt noch nicht genug Quellen oder Bestätigung, um das Signal stabil einzuordnen.',
  },
  stateLevelScope: {
    label: 'Bundesland-Ansicht (Bundesland-Level)',
    badge: 'Bundesland-Ansicht',
    helper: 'Gilt für das ganze Bundesland, nicht für einzelne Städte.',
  },
  noCityForecast: {
    label: 'Keine Stadt-Prognose (City-Forecast)',
    badge: 'Keine Stadt-Prognose',
    helper: 'Es gibt bewusst keine Vorhersage für einzelne Städte.',
  },
} as const;

export function evidenceStatusLabel(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'truth_backed') return 'Mit Kundendaten gestützt';
  if (normalized === 'epidemiological_only') return 'Noch ohne Kundendaten';
  if (normalized === 'no_truth') return UI_COPY.insufficientTruth;
  if (normalized === 'ready' || normalized === 'released' || normalized === 'release') return 'Freigabe bereit';
  if (normalized === 'review' || normalized === 'guarded') return 'Manuell prüfen';
  if (normalized === 'observe_only') return 'Nur beobachten';
  if (normalized === 'blocked' || normalized === 'block') return 'Blockiert';
  return value ? String(value) : '-';
}

export function evidenceStatusHelper(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'truth_backed') return 'Dieses Signal wird zusätzlich durch Kundendaten gestützt.';
  if (normalized === 'epidemiological_only') return 'Dieses Signal stützt sich bisher nur auf Vorhersage- und Marktdaten.';
  if (normalized === 'no_truth') return COCKPIT_SEMANTICS.insufficientTruth.helper;
  if (normalized === 'observe_only') return 'Aktuell nur beobachten und noch keine Freigabe daraus ableiten.';
  if (normalized === 'review' || normalized === 'guarded') return 'Vor einer Freigabe ist noch eine manuelle Prüfung nötig.';
  if (normalized === 'ready' || normalized === 'released' || normalized === 'release') return 'Dieser Status erlaubt den nächsten operativen Schritt.';
  if (normalized === 'blocked' || normalized === 'block') return 'Ein offener Stopper (Blocker) verhindert aktuell den nächsten Schritt.';
  return '';
}

export function decisionStateLabel(state?: string | null): string {
  return String(state || '').toUpperCase() === 'GO' ? 'Freigeben' : 'Beobachten';
}

export function additionalSuggestionsText(count: number, noun = 'Kampagnenvorschläge'): string {
  if (count <= 0) return '';
  return `${count} weitere ${noun} verfügbar.`;
}
