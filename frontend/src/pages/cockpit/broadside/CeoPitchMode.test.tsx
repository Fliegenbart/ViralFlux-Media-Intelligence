import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import CeoPitchMode from './CeoPitchMode';

jest.mock('./AtlasChoropleth', () => () => <div data-testid="atlas-map" />);
jest.mock('./MediaPlanUploadModal', () => () => null);

const snapshot = {
  client: 'GELO',
  virusTyp: 'Influenza A',
  virusLabel: 'Influenza A',
  isoWeek: 'KW 18 / 2026',
  generatedAt: '2026-05-01T08:00:00Z',
  primaryRecommendation: {
    id: 'rec-1',
    fromCode: 'HB',
    toCode: 'HH',
    fromName: 'Bremen',
    toName: 'Hamburg',
    amountEur: null,
    confidence: 0.74,
    signalScore: 0.74,
    expectedReachUplift: null,
    why: 'Hamburg steigt, Bremen faellt.',
    signalMode: true,
  },
  secondaryRecommendations: [],
  regions: [
    {
      code: 'HH',
      name: 'Hamburg',
      delta7d: 0.24,
      pRising: 0.81,
      forecast: null,
      drivers: [],
      currentSpendEur: null,
      recommendedShiftEur: null,
      decisionLabel: 'Prepare',
    },
    {
      code: 'HB',
      name: 'Bremen',
      delta7d: -0.08,
      pRising: 0.25,
      forecast: null,
      drivers: [],
      currentSpendEur: null,
      recommendedShiftEur: null,
      decisionLabel: 'Watch',
    },
  ],
  modelStatus: {
    horizonDays: 7,
    forecastReadiness: 'GO_RANKING',
    forecastFreshness: { featureLagDays: 2 },
    ranking: { precisionAtTop3: 0.68, prAuc: 0.71 },
    lead: { bestLagDays: 7, targetLabel: 'SurvStat' },
  },
  mediaPlan: { connected: false },
  systemStatus: {
    diagnostic_only: true,
    can_change_budget: false,
    budget_status: 'diagnostic_only',
    science_status: 'review',
  },
  mediaSpendingTruth: {
    schema_version: 'media_spending_truth_v1',
    global_status: 'blocked',
    budget_permission: 'blocked',
    can_change_budget: false,
    budget_can_change: false,
    diagnostic_only: true,
    regions: [],
  },
} as any;

describe('CeoPitchMode consistency copy', () => {
  it('frames a strong regional signal as diagnostic instead of budget-active', () => {
    render(<CeoPitchMode snapshot={snapshot} supportedViruses={['Influenza A']} />);

    expect(
      screen.getByRole('heading', {
        name: /Management Summary:\s+Hamburg als Signal-Kandidat prüfen/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Hamburg zeigt Atemwegsdruck/)).toBeInTheDocument();
    expect(screen.getByText(/Ob daraus GELO-Sales werden/)).toBeInTheDocument();
    expect(screen.getByText('Budget-Automation deaktiviert')).toBeInTheDocument();
    expect(screen.getByText(/Funktioniert\. Wartet auf eure Daten/)).toBeInTheDocument();
    expect(screen.getByText(/Wir sind uns zu 74 % sicher/)).toBeInTheDocument();
    expect(screen.getAllByText('Sales-Validierung offen').length).toBeGreaterThan(0);
    expect(screen.getByText(/keine automatische Budgetänderung/)).toBeInTheDocument();

    expect(screen.queryByText(/Ranking-Score, keine kalibrierte Wahrscheinlichkeit/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Signalrichtung sichtbar/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Budget-Prüfung/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Handlungsfähig$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Hamburg priorisieren/)).not.toBeInTheDocument();
  });
});
