import '@testing-library/jest-dom';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { fireEvent, render, screen } from '@testing-library/react';

import PhaseLeadResearchPage from './PhaseLeadResearchPage';
import { usePhaseLeadSnapshot } from './usePhaseLeadSnapshot';
import type { PhaseLeadSnapshot } from './types';

jest.mock('./usePhaseLeadSnapshot', () => ({
  usePhaseLeadSnapshot: jest.fn(),
}));

const mockedUsePhaseLeadSnapshot = usePhaseLeadSnapshot as jest.MockedFunction<typeof usePhaseLeadSnapshot>;

const productSnapshot: PhaseLeadSnapshot = {
  module: 'phase_lead_graph_renewal_filter',
  version: 'plgrf_live_v0',
  mode: 'research',
  as_of: '2026-05-05',
  virus_typ: 'Influenza A',
  horizons: [3, 5, 7, 10, 14],
  summary: {
    data_source: 'live_database',
    fit_mode: 'map_optimization',
    observation_count: 833,
    window_start: '2026-02-17',
    window_end: '2026-04-27',
    converged: true,
    objective_value: 1476.6,
    data_vintage_hash: 'data',
    config_hash: 'config',
    top_region: 'HE',
    warning_count: 0,
  },
  sources: {
    wastewater: { rows: 280, latest_event_date: '2026-04-22', units: ['HE', 'NI'] },
    survstat: { rows: 420, latest_event_date: '2026-04-27', units: ['HE', 'NI'] },
    are: { rows: 96, latest_event_date: '2026-04-20', units: ['HE', 'NI'] },
    notaufnahme: { rows: 37, latest_event_date: '2026-04-27', units: ['DE'] },
  },
  regions: [
    {
      region_code: 'HE',
      region: 'Hessen',
      current_level: 4.2,
      current_growth: 0.18,
      p_up_h7: 0.82,
      p_surge_h7: 0.48,
      p_front: 0.34,
      eeb: 12.5,
      gegb: 44.2,
      source_rows: 66,
    },
    {
      region_code: 'NI',
      region: 'Niedersachsen',
      current_level: 3.8,
      current_growth: 0.07,
      p_up_h7: 0.57,
      p_surge_h7: 0.18,
      p_front: 0.12,
      eeb: 8.5,
      gegb: 31.1,
      source_rows: 61,
    },
  ],
  rankings: { 'Influenza A': [{ region_id: 'HE', gegb: 44.2 }] },
  warnings: [],
};

const aggregateSnapshot = {
  ...productSnapshot,
  version: 'plgrf_aggregate_v0',
  virus_typ: 'Gesamt',
  summary: {
    ...productSnapshot.summary,
    top_region: 'NI',
  },
  regions: [
    {
      ...productSnapshot.regions[1],
      gegb: 78.4,
    },
    {
      ...productSnapshot.regions[0],
      gegb: 62.1,
    },
  ],
  rankings: { Gesamt: [{ region_id: 'NI', gegb: 78.4 }] },
  aggregate: {
    kind: 'respiratory_pressure',
    weighting: 'data_quality',
    available_viruses: ['SARS-CoV-2', 'Influenza B'],
    fallback_viruses: [],
    virus_weights: [
      { virus_typ: 'SARS-CoV-2', weight: 0.33, quality: 0.91 },
      { virus_typ: 'Influenza B', weight: 0.27, quality: 0.74 },
    ],
    drivers_by_region: {
      NI: [
        { virus_typ: 'SARS-CoV-2', contribution: 30.2, signal: 91.5, weight: 0.33 },
        { virus_typ: 'Influenza B', contribution: 24.4, signal: 90.4, weight: 0.27 },
      ],
    },
  },
} as PhaseLeadSnapshot;

function renderPage() {
  return render(
    <MemoryRouter>
      <PhaseLeadResearchPage />
    </MemoryRouter>,
  );
}

describe('PhaseLeadResearchPage', () => {
  beforeEach(() => {
    mockedUsePhaseLeadSnapshot.mockReset();
  });

  it('presents phase-lead as product decision logic instead of a research explainer', () => {
    mockedUsePhaseLeadSnapshot.mockReturnValue({
      snapshot: productSnapshot,
      loading: false,
      error: null,
      reload: jest.fn(),
    });

    renderPage();

    expect(screen.getByRole('heading', { name: /HE zuerst\./i })).toBeInTheDocument();
    expect(screen.getByText(/Regional Media Watch übersetzt Atemwegsdaten/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Gesamt' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Influenza A' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Influenza B' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'RSV A' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'SARS-CoV-2' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Hessen zuerst vorbereiten/i })).toBeInTheDocument();
    expect(screen.getByText(/Budget bleibt shadow-only bis GELO-Sales angebunden sind/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Hessen vorbereiten/i).length).toBeGreaterThan(0);
    expect(screen.getByRole('columnheader', { name: /Empfehlung/i })).toBeInTheDocument();
    expect(screen.queryByText(/Research-only Methode/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Mathematischer Kern/i)).not.toBeInTheDocument();
  });

  it('loads the selected virus snapshot when a virus is chosen', () => {
    mockedUsePhaseLeadSnapshot.mockReturnValue({
      snapshot: productSnapshot,
      loading: false,
      error: null,
      reload: jest.fn(),
    });

    renderPage();

    expect(mockedUsePhaseLeadSnapshot).toHaveBeenLastCalledWith({ virusTyp: 'Gesamt' });

    fireEvent.click(screen.getByRole('button', { name: 'RSV A' }));

    expect(screen.getByRole('button', { name: 'RSV A' })).toHaveAttribute('aria-pressed', 'true');
    expect(mockedUsePhaseLeadSnapshot).toHaveBeenLastCalledWith({ virusTyp: 'RSV A' });
  });

  it('shows aggregate score and regional drivers for the Gesamt tab', () => {
    mockedUsePhaseLeadSnapshot.mockImplementation((options) => ({
      snapshot: options?.virusTyp === 'Gesamt' ? aggregateSnapshot : productSnapshot,
      loading: false,
      error: null,
      reload: jest.fn(),
    }));

    renderPage();

    fireEvent.click(screen.getByRole('button', { name: 'Gesamt' }));

    expect(screen.getByRole('button', { name: 'Gesamt' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('heading', { name: /Niedersachsen zuerst vorbereiten/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Gesamt-Score/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Haupttreiber/i })).toBeInTheDocument();
    expect(screen.getAllByText(/SARS-CoV-2 \+ Influenza B/i).length).toBeGreaterThan(0);
  });

  it('shows a bottom chart for historical signal and forecast', () => {
    mockedUsePhaseLeadSnapshot.mockReturnValue({
      snapshot: productSnapshot,
      loading: false,
      error: null,
      reload: jest.fn(),
    });

    renderPage();

    expect(screen.getByRole('heading', { name: /Bisherige Kurve und Prognose/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Bisher/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Prognose/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Heute/i).length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/Signalverlauf und Prognose/i)).toBeInTheDocument();
  });
});
