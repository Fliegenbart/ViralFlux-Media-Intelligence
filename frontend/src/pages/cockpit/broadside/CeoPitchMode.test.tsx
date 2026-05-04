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
  it('frames a strong regional signal as calibration-window instead of budget-active', () => {
    render(<CeoPitchMode snapshot={snapshot} supportedViruses={['Influenza A']} />);

    expect(
      screen.getByRole('heading', {
        name: /Atemwegsdruck steigt in Hamburg\. Freigabe wartet auf Sales-Kalibrierung\./i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Das Cockpit zeigt das aktuelle regionale Signal/)).toBeInTheDocument();
    expect(screen.getByText(/Der Tri-Layer bewertet konservativer/)).toBeInTheDocument();
    expect(screen.getAllByText('Budget-Gate geschlossen').length).toBeGreaterThan(0);
    expect(screen.getByText(/Funktioniert\. Wartet auf eure Daten/)).toBeInTheDocument();
    expect(screen.getByText('Signal-Evidenz öffnen')).toBeInTheDocument();
    expect(screen.getByText('Signal-Status')).toBeInTheDocument();
    expect(screen.getByText('1 Region riser')).toBeInTheDocument();
    expect(screen.getByText('Daten-Reife')).toBeInTheDocument();
    expect(screen.getByText('0 / 12 Wochen Sell-Out')).toBeInTheDocument();
    expect(screen.getByText('Nächster Schritt')).toBeInTheDocument();
    expect(screen.getByText('Alle Metriken anzeigen')).toBeInTheDocument();

    expect(screen.queryByText(/Ranking-Score, keine kalibrierte Wahrscheinlichkeit/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Signalrichtung sichtbar/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Budget-Prüfung/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Handlungsfähig$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Hamburg priorisieren/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Management Summary/)).not.toBeInTheDocument();
    expect(screen.getByText('Kalibrierungsfenster')).toBeInTheDocument();
  });

  it('uses the insufficient-data state when there is no signal and no sell-out history', () => {
    render(
      <CeoPitchMode
        snapshot={{
          ...snapshot,
          primaryRecommendation: null,
          regions: [
            { ...snapshot.regions[0], delta7d: 0.01, decisionLabel: 'Watch' },
            { ...snapshot.regions[1], delta7d: -0.01, decisionLabel: 'Watch' },
          ],
        }}
        supportedViruses={['Influenza A']}
      />,
    );

    expect(
      screen.getByRole('heading', {
        name: /Datenlage zu eng für eine Empfehlung\. System sammelt weiter\./i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('Erste GELO-CSV hochladen')).toBeInTheDocument();
  });
});
