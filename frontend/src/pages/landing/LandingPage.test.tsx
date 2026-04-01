import '@testing-library/jest-dom';
import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
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
  const landingPayload = {
    generated_at: '2026-03-28T10:30:00Z',
    regions: {
      NW: { region_name: 'Nordrhein-Westfalen', score_0_100: 78, trend: 'steigend' },
      BY: { region_name: 'Bayern', score_0_100: 52, trend: 'steigend' },
      BE: { region_name: 'Berlin', score_0_100: 31, trend: 'stabil' },
    },
  };

  let consoleErrorSpy: jest.SpyInstance;
  let resolveFetch: ((value: unknown) => void) | null;

  beforeEach(() => {
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    resolveFetch = null;
    global.fetch = jest.fn().mockImplementation(() => (
      new Promise((resolve) => {
        resolveFetch = resolve;
      })
    )) as jest.Mock;
  });

  afterEach(() => {
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
    jest.resetAllMocks();
  });

  const resolveLandingFetch = async () => {
    await act(async () => {
      resolveFetch?.({
        ok: true,
        json: async () => landingPayload,
      });
      await Promise.resolve();
      await Promise.resolve();
    });
  };

  it('prioritizes the weekly decision and demotes feature marketing copy', async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LandingPage />
      </MemoryRouter>,
    );

    await resolveLandingFetch();

    await waitFor(() => {
      expect(screen.getByText(/Datenstatus:/i)).toBeInTheDocument();
    });

    expect(
      screen.getByRole('heading', { name: 'Was PEIX x GELO diese Woche entscheiden sollte' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Die Einstiegsseite zeigt die Wochenlage in wenigen Signalen. Die eigentliche Arbeitsfläche öffnet direkt den Wochenplan mit Fokusländern, Richtung und Evidenz.',
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Wochenplan öffnen/i })[0]).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Wochenplan' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Evidenz' })).toBeInTheDocument();
    expect(screen.getByText('Vor dem Einstieg sichtbar')).toBeInTheDocument();
    expect(screen.getByText('Wochenfokus für Bundesländer')).toBeInTheDocument();
    expect(screen.getByText('Evidenz bleibt sichtbar')).toBeInTheDocument();
    expect(screen.queryByText('Wo zuerst hinschauen')).not.toBeInTheDocument();
    expect(screen.queryByText('Was diese Woche tun')).not.toBeInTheDocument();
    expect(screen.queryByText('Warum wir das vertreten')).not.toBeInTheDocument();
  });

  it('shows footer status, version and docs link', async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LandingPage />
      </MemoryRouter>,
    );

    await resolveLandingFetch();

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
