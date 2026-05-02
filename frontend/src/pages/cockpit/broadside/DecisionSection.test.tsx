import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import DecisionSection from './DecisionSection';

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
    confidence: 0.78,
    signalScore: 0.78,
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
    horizonDays: 14,
    calibrationMode: 'heuristic',
    forecastReadiness: 'GO_RANKING',
    lead: { bestLagDays: 9, targetLabel: 'SurvStat' },
  },
  mediaPlan: { connected: false },
  systemStatus: {
    diagnostic_only: true,
    can_change_budget: false,
  },
  evidenceScore: {
    overallScore: 63,
    releaseStatus: 'blocked',
    label: 'Signal sichtbar, Budget wartet',
    components: [],
    blockers: ['missing_media_spend'],
    businessValidation: {
      validated_for_budget_activation: false,
      weeks: 0,
      regions: 0,
      missing_requirements: ['missing_media_spend'],
    },
    plainLanguage: 'Budget bleibt blockiert, bis Business-Daten reichen.',
  },
  mediaSpendingTruth: {
    schema_version: 'media_spending_truth_v1',
    global_status: 'blocked',
    release_mode: 'shadow_only',
    budget_permission: 'blocked',
    can_change_budget: false,
    budget_can_change: false,
    diagnostic_only: true,
    max_approved_delta_pct: 0,
    regions: [],
  },
} as any;

describe('DecisionSection gate discipline', () => {
  it('shows the four gates before any budget action', () => {
    render(<DecisionSection snapshot={snapshot} />);

    expect(screen.getAllByText(/Eine Budget-Empfehlung muss vier Gates passieren/).length).toBeGreaterThan(0);
    expect(screen.getByText('Signal-Konfidenz')).toBeInTheDocument();
    expect(screen.getAllByText('Lead-Time').length).toBeGreaterThan(0);
    expect(screen.getByText('Sales-Validierung')).toBeInTheDocument();
    expect(screen.getAllByText('Coverage').length).toBeGreaterThan(0);
    expect(screen.getByText('Schwelle: 12 Wochen Daten')).toBeInTheDocument();
    expect(screen.getByText('Shadow-Lauf läuft mit. Echtgeld pausiert.')).toBeInTheDocument();
    expect(screen.getByText('Modus: Kalibrierungsfenster')).toBeInTheDocument();
  });
});
