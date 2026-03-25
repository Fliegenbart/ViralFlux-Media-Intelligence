import {
  buildPredictionNarrative,
  explainInPlainGerman,
  normalizeGermanText,
} from './plainLanguage';

describe('plain language helpers', () => {
  it('replaces ASCII fallbacks and Denglish in visible copy', () => {
    expect(normalizeGermanText('Forecast-Monitoring')).toBe('Prüfung der Vorhersage');
    expect(normalizeGermanText('Media Intelligence Curator')).toBe('Frühwarnung für regionale Nachfrage');
    expect(normalizeGermanText('Learning-State')).toBe('Lernstand');
    expect(normalizeGermanText('Koennen wir die Vorschlaege oeffnen?')).toBe('Können wir die Vorschläge öffnen?');
    expect(normalizeGermanText('Outcome-Daten')).toBe('Kundendaten');
    expect(normalizeGermanText('Wirkungsdaten-Daten')).toBe('Wirkungsdaten');
    expect(normalizeGermanText('Kundendaten-Daten')).toBe('Kundendaten');
    expect(normalizeGermanText('Epi-Welle mit ML-Prognose und Aktivierbarkeit')).toBe('Atemwegswelle mit Modellvorhersage und Handlungsreife');
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

  it('translates raw backend explanations into plain German', () => {
    expect(explainInPlainGerman('Event probability 0.81 clears the Activate threshold 0.70.'))
      .toBe('Die Event-Wahrscheinlichkeit liegt mit 81 % über der Schwelle für eine Aktivierung.');
    expect(explainInPlainGerman('Berlin: Activate because event probability is 0.81, forecast confidence is 0.78, trend acceleration is 0.76, and cross-source direction is up.'))
      .toContain('Berlin sollte jetzt aktiviert werden');
    expect(explainInPlainGerman('Priority score and event probability drive the ranking.'))
      .toBe('Entscheidungs-Priorität und Event-Wahrscheinlichkeit treiben hier das Ranking.');
    expect(explainInPlainGerman('Forecast confidence is only 0.41.'))
      .toBe('Die Vorhersage ist mit 41 % Sicherheit noch recht unsicher.');
    expect(explainInPlainGerman('Spend guardrails are currently satisfied.'))
      .toBe('Die Budget- und Freigabegrenzen sind aktuell erfüllt.');
    expect(explainInPlainGerman('Remaining uncertainty: revision risk 0.33, no positive cross-source agreement, quality gate not passed.'))
      .toBe('Es bleibt Unsicherheit wegen Revisionsrisiko von 33 %, kein klar positiver Quellenabgleich und noch nicht bestandene Qualitätsprüfung.');
  });

  it('prefers structured reason codes over free-text guessing', () => {
    expect(explainInPlainGerman({
      code: 'decision_summary',
      message: 'raw summary',
      params: {
        bundesland_name: 'Berlin',
        stage: 'activate',
        event_probability: 0.81,
        forecast_confidence: 0.78,
        agreement_direction: 'up',
      },
    })).toContain('Berlin sollte jetzt aktiviert werden');

    expect(explainInPlainGerman({
      code: 'campaign_stage_budget_share',
      message: 'raw rationale',
      params: {
        region_name: 'Berlin',
        stage: 'activate',
        budget_share: 0.46,
      },
    })).toBe('Berlin bleibt aktuell auf Aktivieren mit 46 % Budgetanteil.');
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
