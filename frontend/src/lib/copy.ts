export const UI_COPY = {
  ai: 'KI',
  signalScore: 'Signalscore',
  signalScoreWithSource: 'Signalscore (PeixEpiScore)',
  marketComparison: 'Marktvergleich',
  customerData: 'Kundendaten',
  customerDataFreshness: 'Stand Kundendaten',
  additionalSuggestions: 'Weitere Vorschlaege',
  handoff: 'Uebergabe',
  weeklyReport: 'Wochenbericht',
  defaultCampaignGoal: 'Sichtbarkeit aufbauen, bevor die Nachfrage steigt',
} as const;

export function decisionStateLabel(state?: string | null): string {
  return String(state || '').toUpperCase() === 'GO' ? 'Freigeben' : 'Beobachten';
}

export function marketComparisonStateLabel(state?: string | null): string {
  return String(state || '').toLowerCase() === 'passed' ? 'im Zielkorridor' : 'weiter beobachten';
}

export function additionalSuggestionsText(count: number, noun = 'Kampagnenvorschlaege'): string {
  if (count <= 0) return '';
  return `${count} weitere ${noun} verfuegbar.`;
}
