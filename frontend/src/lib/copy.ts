export const UI_COPY = {
  ai: 'KI',
  signalScore: 'Ranking-Signal',
  signalScoreWithSource: 'Ranking-Signal (PeixEpiScore)',
  eventProbability: 'Event-Wahrscheinlichkeit',
  decisionPriority: 'Entscheidungs-Priorität',
  uncertainty: 'Unsicherheit',
  insufficientTruth: 'Zu wenig Kundendaten-Evidenz',
  insufficientEvidence: 'Zu wenig Evidenz',
  stateLevelScope: 'Bundesland-Level',
  noCityForecast: 'Kein City-Forecast',
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
    label: 'Event-Wahrscheinlichkeit',
    badge: 'Kalibrierte Wahrscheinlichkeit',
    helper: 'Beschreibt die kalibrierte Wahrscheinlichkeit für das definierte Forecast-Ereignis. Das ist kein Ranking.',
  },
  rankingSignal: {
    label: 'Ranking-Signal',
    badge: 'Ranking-Signal',
    helper: 'Hilft beim Vergleichen von Bundesländern. Das ist keine Eintrittswahrscheinlichkeit.',
  },
  decisionPriority: {
    label: 'Entscheidungs-Priorität',
    badge: 'Entscheidungs-Priorität',
    helper: 'Ordnet, welcher Arbeitsfall zuerst geprüft werden sollte. Das ist keine Wahrscheinlichkeitszahl.',
  },
  uncertainty: {
    label: 'Unsicherheit',
    badge: 'Unsicherheit mit Text',
    helper: 'Unsicherheit wird immer zusätzlich erklärt und nie nur über Farbe gezeigt.',
  },
  insufficientTruth: {
    label: 'Zu wenig Kundendaten-Evidenz',
    badge: 'Kundendaten noch zu dünn',
    helper: 'Es gibt noch nicht genug Kundendaten, um das Signal kommerziell belastbar abzustützen.',
  },
  insufficientEvidence: {
    label: 'Zu wenig Evidenz',
    badge: 'Zu wenig Evidenz',
    helper: 'Es gibt noch nicht genug Quellen oder Bestätigung, um das Signal stabil einzuordnen.',
  },
  stateLevelScope: {
    label: 'Bundesland-Level',
    badge: 'Bundesland-Level',
    helper: 'Die Aussage gilt für das Bundesland als Ganzes und nicht für einzelne Städte.',
  },
  noCityForecast: {
    label: 'Kein City-Forecast',
    badge: 'Kein City-Forecast',
    helper: 'Die Oberfläche zeigt bewusst keine scheinbar punktgenaue Vorhersage für einzelne Städte.',
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
  if (normalized === 'epidemiological_only') return 'Dieses Signal stützt sich bisher nur auf Forecast- und Marktdaten.';
  if (normalized === 'no_truth') return COCKPIT_SEMANTICS.insufficientTruth.helper;
  if (normalized === 'observe_only') return 'Aktuell nur beobachten und noch keine Freigabe daraus ableiten.';
  if (normalized === 'review' || normalized === 'guarded') return 'Vor einer Freigabe ist noch eine manuelle Prüfung nötig.';
  if (normalized === 'ready' || normalized === 'released' || normalized === 'release') return 'Dieser Status erlaubt den nächsten operativen Schritt.';
  if (normalized === 'blocked' || normalized === 'block') return 'Ein blockernder Punkt verhindert aktuell den nächsten Schritt.';
  return '';
}

export function decisionStateLabel(state?: string | null): string {
  return String(state || '').toUpperCase() === 'GO' ? 'Freigeben' : 'Beobachten';
}

export function marketComparisonStateLabel(state?: string | null): string {
  return String(state || '').toLowerCase() === 'passed' ? 'belastbar' : 'noch prüfen';
}

export function additionalSuggestionsText(count: number, noun = 'Kampagnenvorschläge'): string {
  if (count <= 0) return '';
  return `${count} weitere ${noun} verfügbar.`;
}
