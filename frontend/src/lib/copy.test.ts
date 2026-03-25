import {
  COCKPIT_SEMANTICS,
  UI_COPY,
  evidenceStatusHelper,
  evidenceStatusLabel,
} from './copy';

describe('cockpit copy semantics', () => {
  it('defines the core operator semantics in one consistent vocabulary', () => {
    expect(UI_COPY.signalScore).toBe('Ranking-Signal');
    expect(UI_COPY.eventProbability).toBe('Event-Wahrscheinlichkeit');
    expect(UI_COPY.decisionPriority).toBe('Entscheidungs-Priorität');
    expect(UI_COPY.stateLevelScope).toBe('Bundesland-Level');
    expect(UI_COPY.noCityForecast).toBe('Kein City-Forecast');
    expect(COCKPIT_SEMANTICS.eventProbability.badge).toBe('Kalibrierte Wahrscheinlichkeit');
  });

  it('maps evidence and release states to readable operator labels', () => {
    expect(evidenceStatusLabel('truth_backed')).toBe('Mit Kundendaten gestützt');
    expect(evidenceStatusLabel('epidemiological_only')).toBe('Noch ohne Kundendaten');
    expect(evidenceStatusLabel('no_truth')).toBe('Zu wenig Kundendaten-Evidenz');
    expect(evidenceStatusLabel('observe_only')).toBe('Nur beobachten');
    expect(evidenceStatusHelper('epidemiological_only')).toContain('Forecast- und Marktdaten');
  });
});
