import {
  deriveBriefingState,
  regionSignalSentence,
  stageLabel,
} from './nowPageViewModel.utils';

describe('nowPageViewModel.utils', () => {
  it('blocks the briefing when workspace blockers are still open', () => {
    const result = deriveBriefingState({
      hasRegionalModel: true,
      hasActionableRecommendation: true,
      forecastTone: 'success',
      dataTone: 'success',
      businessTone: 'success',
      workspaceStatus: {
        blocker_count: 1,
        blockers: ['Forecast review fehlt noch.'],
        data_freshness: 'Beobachten',
        items: [
          {
            key: 'data_freshness',
            detail: 'Die Daten werden gerade noch abgeglichen.',
          },
        ],
      } as any,
      dataFreshnessValue: 'Beobachten',
    });

    expect(result).toEqual(expect.objectContaining({
      state: 'blocked',
      stateLabel: 'Vor Review blockiert',
      actionHint: 'Forecast review fehlt noch.',
      stale: true,
      staleLabel: 'Daten nicht ganz frisch',
      staleDetail: 'Die Daten werden gerade noch abgeglichen.',
    }));
  });

  it('builds a clear region signal sentence with rounded score and trend', () => {
    expect(regionSignalSentence('Berlin', 81.4, 'steigend')).toBe(
      'Berlin zeigt mit 81/100 aktuell die größte Dynamik, der Trend wirkt steigend.',
    );
  });

  it('maps workflow stages to the plain-language labels used in the cockpit', () => {
    expect(stageLabel('activate')).toBe('Aktivieren');
    expect(stageLabel('prepare')).toBe('Vorbereiten');
    expect(stageLabel('watch')).toBe('Beobachten');
  });
});
