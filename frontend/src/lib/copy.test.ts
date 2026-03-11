import {
  UI_COPY,
  additionalSuggestionsText,
  decisionStateLabel,
  marketComparisonStateLabel,
} from './copy';

describe('shared copy helpers', () => {
  it('exposes the new default campaign goal', () => {
    expect(UI_COPY.defaultCampaignGoal).toBe('Sichtbarkeit aufbauen, bevor die Nachfrage steigt');
  });

  it('translates decision states into clear German labels', () => {
    expect(decisionStateLabel('GO')).toBe('Freigeben');
    expect(decisionStateLabel('WATCH')).toBe('Beobachten');
  });

  it('summarizes hidden suggestions without backlog wording', () => {
    expect(additionalSuggestionsText(9)).toBe('9 weitere Kampagnenvorschläge verfügbar.');
    expect(additionalSuggestionsText(0)).toBe('');
  });

  it('describes the market comparison state in plain language', () => {
    expect(marketComparisonStateLabel('passed')).toBe('im Zielkorridor');
    expect(marketComparisonStateLabel('watch')).toBe('weiter beobachten');
  });
});
