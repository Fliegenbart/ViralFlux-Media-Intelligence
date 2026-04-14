import '@testing-library/jest-dom';
import React from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import LandingPage from './LandingPage';

let mockAuthenticated = false;

jest.mock('../../App', () => ({
  useTheme: () => ({
    theme: 'light',
    toggle: jest.fn(),
  }),
  useAuth: () => ({
    authenticated: mockAuthenticated,
    handleLogin: jest.fn(),
    handleLogout: jest.fn(),
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

const LocationProbe: React.FC = () => {
  const location = useLocation();

  return <div data-testid="location-probe">{location.pathname}</div>;
};

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

  const renderLandingPage = () =>
    render(
      <MemoryRouter initialEntries={['/welcome']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LocationProbe />
        <Routes>
          <Route path="/welcome" element={<LandingPage />} />
          <Route path="/login" element={<div>Login page</div>} />
          <Route path="/jetzt" element={<div>Now page</div>} />
          <Route path="/virus-radar" element={<div>Virus radar page</div>} />
        </Routes>
      </MemoryRouter>,
    );

  it('shows customer-facing product-core copy instead of internal weekly-planning language', async () => {
    mockAuthenticated = false;
    renderLandingPage();

    await resolveLandingFetch();

    await waitFor(() => {
      expect(screen.getByText(/Datenstatus:/i)).toBeInTheDocument();
    });

    expect(
      screen.getByRole('heading', { name: 'Erkennen, welche Regionen jetzt zuerst geprüft werden sollten' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'ViralFlux hilft Teams dabei, regionale Virus-Signale früher zu erkennen, die Lage für die nächsten Tage besser einzuordnen und daraus eine verständliche Wochensteuerung abzuleiten.',
      ),
    ).toBeInTheDocument();
    const hero = screen.getByRole('region', { name: 'Produktkern Einstieg' });
    expect(within(hero).getByRole('heading', { name: 'Erkennen, welche Regionen jetzt zuerst geprüft werden sollten' })).toBeInTheDocument();
    expect(within(hero).getAllByRole('button', { name: 'Produktkern ansehen' })).toHaveLength(1);
    expect(within(hero).getByRole('link', { name: 'Aktuellen Produktumfang lesen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Nutzen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Produktkern' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Einsatzgrenzen' })).toBeInTheDocument();
    expect(screen.getByText('Was der Produktkern heute schon leistet')).toBeInTheDocument();
    expect(screen.getByText('Regionen schneller priorisieren')).toBeInTheDocument();
    expect(screen.getByText('Forecast, Lage und Empfehlung getrennt sehen')).toBeInTheDocument();
    expect(screen.getByText('Bewusst klar begrenzt statt zu viel versprochen')).toBeInTheDocument();
    expect(screen.queryByText('Was diese Woche entschieden werden sollte')).not.toBeInTheDocument();
    expect(screen.queryByText('Wochenfokus für Bundesländer')).not.toBeInTheDocument();
    expect(screen.queryByText('Evidenz bleibt sichtbar')).not.toBeInTheDocument();
  });

  it('shows footer status, version and product-scope link', async () => {
    mockAuthenticated = false;
    renderLandingPage();

    await resolveLandingFetch();

    await waitFor(() => {
      expect(screen.getByText(/Datenstatus:/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Version 1.0.0')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Produktumfang' })).toHaveAttribute(
      'href',
      'https://github.com/Fliegenbart/ViralFlux-Media-Intelligence/blob/main/docs/current_product_scope.md',
    );
  });

  it('sends logged-out visitors from the hero CTA to /login', async () => {
    mockAuthenticated = false;
    renderLandingPage();

    await resolveLandingFetch();

    await waitFor(() => {
      expect(screen.getByText(/Datenstatus:/i)).toBeInTheDocument();
    });

    const hero = screen.getByRole('region', { name: 'Produktkern Einstieg' });

    await act(async () => {
      within(hero).getByRole('button', { name: 'Produktkern ansehen' }).click();
    });

    expect(screen.getByTestId('location-probe')).toHaveTextContent('/login');
  });

  it('sends logged-in visitors from the hero CTA to /virus-radar', async () => {
    mockAuthenticated = true;
    renderLandingPage();

    await resolveLandingFetch();

    await waitFor(() => {
      expect(screen.getByText(/Datenstatus:/i)).toBeInTheDocument();
    });

    const hero = screen.getByRole('region', { name: 'Produktkern Einstieg' });

    await act(async () => {
      within(hero).getByRole('button', { name: 'Produktkern ansehen' }).click();
    });

    expect(screen.getByTestId('location-probe')).toHaveTextContent('/virus-radar');
  });
});
