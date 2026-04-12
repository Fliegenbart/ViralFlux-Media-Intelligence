import {
  buildSignalTiles,
  buildTrendInsight,
  resolveRegionStage,
} from './virusRadarWorkspace.utils';

jest.mock('./cockpitUtils', () => ({
  formatCurrency: (value: number | null | undefined) => (value == null ? '-' : `${value} EUR`),
  formatPercent: (value: number) => `${Math.round(value)}%`,
}));

describe('virusRadarWorkspace.utils', () => {
  it('builds the radar tape from workspace, evidence and campaign state', () => {
    const tiles = buildSignalTiles({
      workspaceStatus: {
        data_freshness: 'Aktuell',
        summary: 'Die Kernquellen sind frisch genug.',
        blocker_count: 2,
        open_blockers: '2 offen',
      } as any,
      evidence: {
        truth_gate: {
          state: 'Aktiv',
          passed: true,
          message: 'Die Truth-Lage ist für diese Woche belastbar.',
        },
      } as any,
      campaigns: {
        summary: {
          publishable_cards: 3,
          active_cards: 5,
        },
      } as any,
      topPrediction: {
        event_probability: 0.82,
        trend: 'steigend',
      },
    });

    expect(tiles).toEqual([
      expect.objectContaining({
        label: 'Signalstärke',
        value: '82%',
        detail: 'Trend steigend',
        tone: 'danger',
      }),
      expect.objectContaining({
        label: 'Evidenz',
        value: 'Aktiv',
        tone: 'neutral',
      }),
      expect.objectContaining({
        label: 'Datenfrische',
        value: 'Aktuell',
        tone: 'success',
      }),
      expect.objectContaining({
        label: 'Kampagnen-Reife',
        value: '3',
        detail: '5 aktive Vorschläge',
        tone: 'neutral',
      }),
      expect.objectContaining({
        label: 'Blocker',
        value: '2',
        detail: '2 offen',
        tone: 'neutral',
      }),
    ]);
  });

  it('describes a sharply rising focus-region trend in plain language', () => {
    expect(buildTrendInsight({
      regionName: 'Berlin',
      changePct: 31.2,
      trend: 'steigend',
      virus: 'Influenza A',
      hasTimeline: true,
    })).toEqual(expect.objectContaining({
      tone: 'rising',
      headline: 'Signal baut sich deutlich auf.',
      metricValue: '+31.2%',
      metricDetail: 'Berlin · Trend steigend',
    }));
  });

  it('falls back to probability thresholds when no stage labels are present', () => {
    expect(resolveRegionStage(null, null, 0.8)).toBe('Aktivieren');
    expect(resolveRegionStage(null, null, 0.52)).toBe('Vorbereiten');
    expect(resolveRegionStage(null, null, 0.2)).toBe('Beobachten');
  });
});
