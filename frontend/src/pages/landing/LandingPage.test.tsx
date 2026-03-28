import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import LandingPage from './LandingPage';

jest.mock('../../App', () => ({
  useTheme: () => ({
    theme: 'light',
    toggle: jest.fn(),
  }),
}));

jest.mock('./LandingWidgets', () => ({
  RevealSection: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  MiniGermanyMap: () => <div data-testid="mini-germany-map">Karte</div>,
  createThemePalette: () => ({
    bg: '#fff',
    bgCard: '#fff',
    text: '#111',
    textSec: '#333',
    textMuted: '#666',
    indigo: '#4338ca',
    indigoLight: '#eef2ff',
    indigoSoft: '#eef2ff',
    border: '#ddd',
    borderLight: '#eee',
    rule: '#eee',
  }),
}));

describe('LandingPage', () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        generated_at: '2026-03-28T10:30:00Z',
        regions: {
          NW: { region_name: 'Nordrhein-Westfalen', score_0_100: 78, trend: 'steigend' },
          BY: { region_name: 'Bayern', score_0_100: 52, trend: 'steigend' },
          BE: { region_name: 'Berlin', score_0_100: 31, trend: 'stabil' },
        },
      }),
    }) as jest.Mock;
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  it('shows the simplified landing promise and primary CTA', async () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Datenstatus:/i)).toBeInTheDocument();
    });

    expect(
      screen.getByRole('heading', { name: 'Regionale Virus-Frühwarnung für Media-Entscheidungen' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('ViralFlux zeigt, wo sich Viruswellen aufbauen und was das für Kampagnen, Priorisierung und Freigabe bedeutet.'),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Zum Dashboard/i })[0]).toBeInTheDocument();
    expect(screen.getByText('Frühwarnung')).toBeInTheDocument();
    expect(screen.getByText('Entscheidungshilfe')).toBeInTheDocument();
    expect(screen.getByText('Freigabe-Gate')).toBeInTheDocument();
  });

  it('shows footer status, version and docs link', async () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Datenstatus:/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Version 1.0.0')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Docs' })).toHaveAttribute(
      'href',
      'https://github.com/Fliegenbart/ViralFlux-Media-Intelligence/blob/main/docs/OPERATORS_GUIDE.md',
    );
  });
});
