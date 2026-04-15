import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

jest.mock('./lib/api', () => ({
  apiFetch: jest.fn(),
  rehydrateAuth: jest.fn(),
  logout: jest.fn(),
  addAuthChangeListener: jest.fn(),
}));

jest.mock('./pages/LoginPage', () => ({
  __esModule: true,
  default: ({ onLogin }: { onLogin: () => void }) => (
    <button type="button" onClick={onLogin}>
      Login Mock
    </button>
  ),
}));

jest.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock('./features/media/RecommendationOverlay', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('./pages/media/NowPage', () => ({
  __esModule: true,
  default: () => <div>Jetzt Mock</div>,
}));

jest.mock('./pages/media/VirusRadarPage', () => ({
  __esModule: true,
  default: () => <div>Virus-Radar Mock</div>,
}));

jest.mock('./pages/media/TimegraphPage', () => ({
  __esModule: true,
  default: () => <div>Zeitgraph Mock</div>,
}));

jest.mock('./pages/media/RegionsPage', () => ({
  __esModule: true,
  default: () => <div>Regionen Mock</div>,
}));

jest.mock('./pages/media/CampaignsPage', () => ({
  __esModule: true,
  default: () => <div>Kampagnen Mock</div>,
}));

jest.mock('./pages/media/EvidencePage', () => ({
  __esModule: true,
  default: () => <div>Evidenz Mock</div>,
}));

import App from './App';
import { addAuthChangeListener, logout, rehydrateAuth } from './lib/api';

const mockRehydrateAuth = jest.mocked(rehydrateAuth);
const mockLogout = jest.mocked(logout);
const mockAddAuthChangeListener = jest.mocked(addAuthChangeListener);

describe('App routing', () => {
  beforeEach(() => {
    mockRehydrateAuth.mockReset();
    mockRehydrateAuth.mockResolvedValue(true);
    mockLogout.mockReset();
    mockAddAuthChangeListener.mockReset();
    mockAddAuthChangeListener.mockReturnValue(() => {});
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.history.pushState({}, '', '/');
  });

  it('applies the light theme by default when no theme is stored', async () => {
    window.localStorage.removeItem('viralflux-theme');

    render(<App />);

    await waitFor(() => {
      expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    });
  });

  it('rehydrates auth state on app startup from the backend session check', async () => {
    render(<App />);

    expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
  });

  it('logs auth rehydration failures and still lands on the login page', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    mockRehydrateAuth.mockRejectedValueOnce(new Error('session busted'));

    try {
      render(<App />);

      expect(await screen.findByText('Login Mock')).toBeInTheDocument();
      expect(consoleErrorSpy).toHaveBeenCalledWith('Auth rehydration failed', expect.any(Error));
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it('renders the real operator shell chrome for authenticated routes', async () => {
    render(<App />);

    expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Schnellmenü öffnen/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Navigation öffnen/i })).toBeInTheDocument();
  });

  it('redirects root and legacy dashboard routes to /virus-radar and keeps detail routes visible in navigation', async () => {
    const firstRender = render(<App />);

    expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/virus-radar');

    firstRender.unmount();
    window.history.pushState({}, '', '/dashboard');

    render(<App />);

    expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/virus-radar');

    const primaryNavigation = screen.getByRole('navigation', { name: 'Hauptnavigation' });
    const detailNavigation = screen.getByRole('navigation', { name: 'Detailansichten' });

    expect(within(primaryNavigation).getByRole('link', { name: /Entscheidung/i })).toBeInTheDocument();
    expect(within(detailNavigation).getByRole('link', { name: /Zeitgraph/i })).toBeInTheDocument();
    expect(within(detailNavigation).getByRole('link', { name: /Regionen/i })).toBeInTheDocument();
    expect(within(detailNavigation).getByRole('link', { name: /^Kampagnen$/i })).toBeInTheDocument();
    expect(within(detailNavigation).getByRole('link', { name: /Evidenz/i })).toBeInTheDocument();
  });

  describe('when logged out', () => {
    beforeEach(() => {
      mockRehydrateAuth.mockResolvedValue(false);
    });

    it('redirects / to /login', async () => {
      render(<App />);

      expect(await screen.findByText('Login Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/login');
    });

    it('redirects /welcome to /login', async () => {
      window.history.pushState({}, '', '/welcome');

      render(<App />);

      expect(await screen.findByText('Login Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/login');
    });

    it('redirects /virus-radar to /login', async () => {
      window.history.pushState({}, '', '/virus-radar');

      render(<App />);

      expect(await screen.findByText('Login Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/login');
    });

    it('redirects /dashboard to /login', async () => {
      window.history.pushState({}, '', '/dashboard');

      render(<App />);

      expect(await screen.findByText('Login Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/login');
    });

    it('renders the login page at /login and keeps the URL on /login', async () => {
      window.history.pushState({}, '', '/login');

      render(<App />);

      expect(await screen.findByText('Login Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/login');
    });

    it('returns to the requested deep link after login', async () => {
      window.history.pushState({}, '', '/kampagnen/123');

      render(<App />);

      expect(await screen.findByText('Login Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/login');

      fireEvent.click(screen.getByRole('button', { name: 'Login Mock' }));

      expect(await screen.findByText('Kampagnen Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/kampagnen/123');
    });

    it('lands on /virus-radar after login when there is no stored from destination', async () => {
      window.history.pushState({}, '', '/login');

      render(<App />);

      expect(await screen.findByText('Login Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/login');

      fireEvent.click(screen.getByRole('button', { name: 'Login Mock' }));

      expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/virus-radar');
    });

    it('preserves search and hash when returning to the requested deep link after login', async () => {
      window.history.pushState({}, '', '/kampagnen/123?tab=history#details');

      render(<App />);

      expect(await screen.findByText('Login Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/login');

      fireEvent.click(screen.getByRole('button', { name: 'Login Mock' }));

      expect(await screen.findByText('Kampagnen Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/kampagnen/123');
      expect(window.location.search).toBe('?tab=history');
      expect(window.location.hash).toBe('#details');
    });

    it('returns to the canonical destination after logging in from a legacy alias', async () => {
      window.history.pushState({}, '', '/dashboard/recommendations/123');

      render(<App />);

      expect(await screen.findByText('Login Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/login');

      fireEvent.click(screen.getByRole('button', { name: 'Login Mock' }));

      expect(await screen.findByText('Kampagnen Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/kampagnen/123');
    });
  });

  it('redirects authenticated visitors away from /login to /virus-radar', async () => {
    window.history.pushState({}, '', '/login');

    render(<App />);

    expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/virus-radar');
  });

  it('keeps legacy buyer-facing aliases for decision, pilot, and report on supported pages', async () => {
    const legacyPaths = ['/entscheidung', '/pilot', '/bericht'];

    for (const path of legacyPaths) {
      window.history.pushState({}, '', path);

      const view = render(<App />);

      expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/virus-radar');

      view.unmount();
    }
  });

  it('keeps /zeitgraph as a reachable detail page', async () => {
    window.history.pushState({}, '', '/zeitgraph');

    render(<App />);

    expect(await screen.findByText('Zeitgraph Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/zeitgraph');
  });

  it('keeps the detail work-area routes reachable next to the decision page', async () => {
    const reachablePaths = [
      ['/zeitgraph', 'Zeitgraph Mock'],
      ['/regionen', 'Regionen Mock'],
      ['/kampagnen', 'Kampagnen Mock'],
      ['/evidenz', 'Evidenz Mock'],
    ] as const;

    for (const [path, text] of reachablePaths) {
      window.history.pushState({}, '', path);

      const view = render(<App />);

      expect(await screen.findByText(text)).toBeInTheDocument();
      expect(window.location.pathname).toBe(path);

      view.unmount();
    }
  });

  it('keeps an explicit virus-radar URL after auth instead of redirecting elsewhere', async () => {
    window.history.pushState({}, '', '/virus-radar');

    render(<App />);

    expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/virus-radar');
  });
});
