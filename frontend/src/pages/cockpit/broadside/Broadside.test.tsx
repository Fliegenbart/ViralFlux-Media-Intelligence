import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import Broadside from './Broadside';

jest.mock('./ChronoBar', () => () => <div data-testid="chrono">Chrono</div>);
jest.mock('./EvidenceStatusBar', () => () => <section data-testid="status">Status</section>);
jest.mock('./VirusWaveEvidencePanel', () => () => <section data-testid="evidence">Evidence</section>);
jest.mock('./CeoPitchMode', () => () => <section data-testid="summary">Management Summary</section>);
jest.mock('./AtlasSection', () => () => <section data-testid="atlas">Atlas</section>);
jest.mock('./ForecastSection', () => () => <section data-testid="forecast">Forecast</section>);
jest.mock('./BacktestSection', () => () => <section data-testid="backtest">Backtest</section>);
jest.mock('./DecisionSection', () => () => <section data-testid="decision">Media Decision</section>);
jest.mock('./ImpactSection', () => () => <section data-testid="impact">Impact</section>);
jest.mock('./NextStepsSection', () => () => <section data-testid="next">Next</section>);

const snapshot = {
  client: 'GELO',
  virusTyp: 'Influenza A',
  virusLabel: 'Influenza A',
  isoWeek: 'KW 18 / 2026',
  generatedAt: '2026-05-01T08:00:00Z',
  primaryRecommendation: null,
  secondaryRecommendations: [],
  regions: [],
  timeline: [],
  sources: [],
  topDrivers: [],
  notes: [],
  modelStatus: {
    horizonDays: 7,
    calibrationMode: 'unknown',
    forecastReadiness: 'WATCH',
  },
  mediaPlan: { connected: false },
} as any;

function expectBefore(left: HTMLElement, right: HTMLElement) {
  expect(left.compareDocumentPosition(right) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
}

describe('Broadside opening order', () => {
  it('starts with the management summary map before the evidence details', () => {
    render(
      <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <Broadside
          snapshot={snapshot}
          virusTyp="Influenza A"
          onVirusChange={jest.fn()}
          supportedViruses={['Influenza A']}
        />
      </MemoryRouter>,
    );

    expectBefore(screen.getByTestId('status'), screen.getByTestId('evidence'));
    expectBefore(screen.getByTestId('status'), screen.getByTestId('summary'));
    expectBefore(screen.getByTestId('summary'), screen.getByTestId('evidence'));
    expectBefore(screen.getByTestId('evidence'), screen.getByTestId('atlas'));
    expectBefore(screen.getByTestId('summary'), screen.getByTestId('atlas'));
    expectBefore(screen.getByTestId('backtest'), screen.getByTestId('decision'));
  });
});
