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
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LandingPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Datenstatus:/i)).toBeInTheDocument();
    });

    expect(
      screen.getByRole('heading', { name: 'Die Wochensteuerung für PEIX x GELO' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('ViralFlux zeigt zuerst, welche Bundesländer jetzt Aufmerksamkeit verdienen, welche Maßnahme als Nächstes sinnvoll ist und worauf sich diese Einordnung stützt.'),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Zum Wochenplan/i })[0]).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Wochenplan' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Evidenz' })).toBeInTheDocument();
    expect(screen.getByText('Wo zuerst hinschauen')).toBeInTheDocument();
    expect(screen.getByText('Was diese Woche tun')).toBeInTheDocument();
    expect(screen.getByText('Warum wir das vertreten')).toBeInTheDocument();
  });

  it('shows footer status, version and docs link', async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
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
