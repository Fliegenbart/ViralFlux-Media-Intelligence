import {
  buildPredictionNarrative,
  normalizeGermanText,
} from './plainLanguage';

describe('plain language helpers', () => {
  it('replaces ASCII fallbacks and Denglish in visible copy', () => {
    expect(normalizeGermanText('Forecast-Monitoring')).toBe('Prüfung der Vorhersage');
    expect(normalizeGermanText('Media Intelligence Curator')).toBe('Frühwarnung für regionale Nachfrage');
    expect(normalizeGermanText('Learning-State')).toBe('Lernstand');
    expect(normalizeGermanText('Koennen wir die Vorschlaege oeffnen?')).toBe('Können wir die Vorschläge öffnen?');
  });

  it('builds an assertive prediction narrative for stable states', () => {
    const narrative = buildPredictionNarrative({
      horizonDays: 7,
      regionName: 'Berlin',
      forecastStatus: 'Freigabe bereit',
      proofPoints: ['7 Tage Vorhersage', 'Berlin liegt im Ranking vorn'],
    });

    expect(narrative.assertive).toBe(true);
    expect(narrative.headline).toContain('7-Tage-Fenster');
    expect(narrative.headline).toContain('Berlin');
    expect(narrative.proofPoints).toEqual(['7 Tage Vorhersage', 'Berlin liegt im Ranking vorn']);
  });

  it('builds a careful prediction narrative for warning states', () => {
    const narrative = buildPredictionNarrative({
      horizonDays: 5,
      regionName: 'Bayern',
      forecastStatus: 'Beobachten',
      proofPoints: ['Quellenlage wird noch geprüft'],
    });

    expect(narrative.assertive).toBe(false);
    expect(narrative.headline).toContain('5-Tage-Fenster');
    expect(narrative.supportingText).toContain('Vor einer Freigabe');
  });
});
