import {
  buildSimplifiedDecisionModel,
  findFocusPrediction,
  trendLabel,
} from './simplifiedDecisionWorkspace.utils';

describe('buildSimplifiedDecisionModel', () => {
  const baseView = {
    hasData: true,
    generatedAt: '2026-04-14T08:00:00Z',
    title: 'Decision',
    summary: 'Sachsen zeigt aktuell die staerkste Dynamik.',
    note: '',
    proof: null,
    primaryActionLabel: 'Empfehlung pruefen',
    primaryRecommendationId: 'rec-1',
    heroRecommendation: {
      headline: 'Budget erhoehen',
      actionLabel: 'Empfehlung pruefen',
      direction: 'Budget erhoehen',
      region: 'Sachsen',
      regionCode: 'SN',
      context: 'Influenza A',
      whyNow: 'Der Verlauf steigt und die Prognose zeigt weiter nach oben.',
      state: 'strong',
      stateLabel: 'Bereit fuer Review',
      actionHint: null,
      ctaDisabled: false,
    },
    secondaryMoves: [
      { code: 'HH', name: 'Hamburg', stage: 'Beobachten', probabilityLabel: '38%', reason: 'Noch nicht stark genug.' },
    ],
    briefingTrust: {
      summary: 'Forecast und Datenlage tragen die Empfehlung.',
      items: [
        { key: 'reliability', label: 'Belastbarkeit', value: 'Mittel', detail: 'Die Prognose ist brauchbar.', tone: 'warning' },
      ],
    },
    supportState: { stale: false, label: null, detail: null },
    primaryCampaignTitle: '',
    primaryCampaignContext: '',
    primaryCampaignCopy: '',
    focusRegion: {
      code: 'SN',
      name: 'Sachsen',
      stage: 'Aktivieren',
      reason: 'Die Dynamik ist am staerksten.',
      product: 'GELO',
      probabilityLabel: '81%',
      budgetLabel: '55.000 EUR',
      recommendationId: 'rec-1',
    },
    metrics: [],
    trustChecks: [],
    reasons: ['Sachsen fuehrt Forecast und Signal an.'],
    risks: ['Kundendaten sind noch im Aufbau.'],
    quality: [],
    relatedRegions: [],
    emptyState: null,
  } as any;

  it('builds a go decision for strong recommendations', () => {
    const model = buildSimplifiedDecisionModel({
      view: baseView,
      forecast: {
        predictions: [
          {
            bundesland: 'SN',
            bundesland_name: 'Sachsen',
            event_probability: 0.81,
            change_pct: 12.4,
            trend: 'steigend',
          },
        ],
      } as any,
    });

    expect(model.state).toBe('go');
    expect(model.headline).toBe('Diese Woche Budget in Sachsen erhoehen.');
    expect(model.facts.map((item) => item.label)).toEqual(['Region', 'Trend', 'Vertrauen']);
    expect(model.summary).toBe('Der Verlauf steigt und die Prognose zeigt weiter nach oben.');
  });

  it('builds a watch decision for guarded or blocked recommendations', () => {
    const model = buildSimplifiedDecisionModel({
      view: {
        ...baseView,
        heroRecommendation: {
          ...baseView.heroRecommendation,
          state: 'guarded',
          whyNow: 'Es gibt erste Signale, aber noch nicht genug Sicherheit.',
        },
      },
      forecast: {
        predictions: [
          {
            bundesland: 'SN',
            bundesland_name: 'Sachsen',
            event_probability: 0.44,
            change_pct: 3.1,
            trend: 'stabil',
          },
        ],
      } as any,
    });

    expect(model.state).toBe('watch');
    expect(model.headline).toBe('Diese Woche Sachsen weiter beobachten.');
  });

  it('builds a no-call decision for weak recommendations', () => {
    const model = buildSimplifiedDecisionModel({
      view: {
        ...baseView,
        primaryRecommendationId: null,
        heroRecommendation: {
          ...baseView.heroRecommendation,
          state: 'weak',
          whyNow: 'Die Datenlage reicht noch nicht fuer eine ehrliche Aktivierung.',
        },
      },
      forecast: { predictions: [] } as any,
    });

    expect(model.state).toBe('no_call');
    expect(model.headline).toBe('Aktuell keine belastbare regionale Budgetempfehlung.');
    expect(model.detailSections.risks[0]).toContain('Kundendaten');
  });

  it('uses the updated helper contracts for forecast lookup and derived facts', () => {
    expect(trendLabel(12.4)).toBe('Steigend');
    expect(trendLabel(-3.1)).toBe('Stabil');
    expect(trendLabel(0)).toBe('Stabil');
    expect(findFocusPrediction(null, 'SN', 'Sachsen')).toBeNull();

    const model = buildSimplifiedDecisionModel({
      view: {
        ...baseView,
        briefingTrust: {
          ...baseView.briefingTrust,
          items: [
            {
              key: 'reliability',
              label: 'Belastbarkeit',
              value: 'Hoch',
              detail: 'Die Prognose ist belastbar.',
              tone: 'warning',
            },
          ],
        },
        secondaryMoves: [
          ...baseView.secondaryMoves,
          { code: 'BE', name: 'Berlin', stage: 'Vorbereiten', probabilityLabel: '51%', reason: 'Signal zieht an.' },
          { code: 'BY', name: 'Bayern', stage: 'Pruefen', probabilityLabel: '47%', reason: 'Noch nicht sicher.' },
          { code: 'NW', name: 'Nordrhein-Westfalen', stage: 'Beobachten', probabilityLabel: '42%', reason: 'Signal bleibt gemischt.' },
          { code: 'HE', name: 'Hessen', stage: 'Beobachten', probabilityLabel: '39%', reason: 'Zu früh fuer Aktivierung.' },
        ],
        relatedRegions: [
          { code: 'TH', name: 'Thueringen', stage: 'Vorbereiten', probabilityLabel: '48%', reason: 'Nachlaufender Effekt.' },
          { code: 'MV', name: 'Mecklenburg-Vorpommern', stage: 'Beobachten', probabilityLabel: '36%', reason: 'Noch flach.' },
          { code: 'ST', name: 'Sachsen-Anhalt', stage: 'Beobachten', probabilityLabel: '33%', reason: 'Kein klarer Trend.' },
          { code: 'HB', name: 'Bremen', stage: 'Beobachten', probabilityLabel: '31%', reason: 'Sehr geringe Dynamik.' },
        ],
        risks: ['Kundendaten sind noch im Aufbau.', 'Forecast ist noch jung.', 'Regionale Basis ist klein.', 'Weitere Absicherung fehlt.'],
        summary: 'Die Lage bleibt klar, aber noch nicht final.',
        note: 'Hinweistext als Zusatz.',
        heroRecommendation: {
          ...baseView.heroRecommendation,
          whyNow: '',
        },
      },
      forecast: {
        predictions: [
          {
            bundesland: 'SN',
            bundesland_name: 'Anderer Name',
            event_probability: 0.81,
            change_pct: 12.4,
            trend: 'steigend',
          },
        ],
      } as any,
    });

    expect(model.summary).toBe('Die Lage bleibt klar, aber noch nicht final.');
    expect(model.facts[2]).toEqual({
      label: 'Vertrauen',
      value: 'Hoch',
      detail: 'Die Prognose ist belastbar.',
    });
    expect(model.detailSections.why).toEqual([
      'Die Lage bleibt klar, aber noch nicht final.',
      'Sachsen fuehrt Forecast und Signal an.',
    ]);
    expect(model.detailSections.alternatives).toEqual([
      'Hamburg · Beobachten · 38%',
      'Berlin · Vorbereiten · 51%',
      'Bayern · Pruefen · 47%',
      'Thueringen · Vorbereiten · 48%',
      'Mecklenburg-Vorpommern · Beobachten · 36%',
      'Sachsen-Anhalt · Beobachten · 33%',
    ]);
    expect(model.detailSections.risks).toEqual([
      'Kundendaten sind noch im Aufbau.',
      'Forecast ist noch jung.',
      'Regionale Basis ist klein.',
      'Belastbarkeit: Die Prognose ist belastbar.',
    ]);
    expect(model.facts[0].value).toBe('Sachsen');
  });

  it('accepts a missing forecast and falls back for summary when needed', () => {
    const model = buildSimplifiedDecisionModel({
      view: {
        ...baseView,
        heroRecommendation: {
          ...baseView.heroRecommendation,
          whyNow: '',
          stateLabel: '',
        },
        briefingTrust: {
          ...baseView.briefingTrust,
          items: [],
        },
        summary: '',
        note: 'Kurznotiz als letzter Fallback.',
      },
      forecast: null,
    });

    expect(model.focusPrediction).toBeNull();
    expect(model.summary).toBe('Kurznotiz als letzter Fallback.');
    expect(model.facts[2].value).toBe('Noch offen');
  });

  it('finds focus predictions by exact region identity only', () => {
    const prediction = findFocusPrediction(
      {
        predictions: [
          {
            bundesland: 'XX',
            bundesland_name: 'Other Region',
            event_probability: 0.21,
            change_pct: 1.2,
            trend: 'stabil',
          },
          {
            bundesland: 'SN',
            bundesland_name: 'Sachsen',
            event_probability: 0.81,
            change_pct: 12.4,
            trend: 'steigend',
          },
        ],
      } as any,
      ' sn ',
      'sachsen',
    );

    expect(prediction?.bundesland).toBe('XX');
  });
});
