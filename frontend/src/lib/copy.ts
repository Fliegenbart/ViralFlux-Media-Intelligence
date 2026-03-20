export const UI_COPY = {
  ai: 'KI',
  signalScore: 'Signalwert',
  signalScoreWithSource: 'Signalwert (PeixEpiScore)',
  marketComparison: 'Marktvergleich',
  customerData: 'Kundendaten',
  customerDataFreshness: 'Stand Kundendaten',
  additionalSuggestions: 'Weitere Vorschläge',
  handoff: 'Übergabe',
  weeklyReport: 'Bericht exportieren',
  defaultCampaignGoal: 'Sichtbarkeit aufbauen, bevor die Nachfrage steigt',
} as const;

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
