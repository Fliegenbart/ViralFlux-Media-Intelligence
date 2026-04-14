import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const mockRehydrateAuth = jest.fn<Promise<boolean>, []>();
const mockLogout = jest.fn();
const mockAddAuthChangeListener = jest.fn<() => void, [(authenticated: boolean) => void]>(() => () => {});

jest.mock('./lib/api', () => ({
  apiFetch: jest.fn(),
  rehydrateAuth: (...args: unknown[]) => mockRehydrateAuth(...args as []),
  logout: (...args: unknown[]) => mockLogout(...args),
  addAuthChangeListener: (...args: [(authenticated: boolean) => void]) => mockAddAuthChangeListener(...args),
}));

jest.mock('./pages/LoginPage', () => ({
  __esModule: true,
  default: ({ onLogin }: { onLogin: () => void }) => (
    <button type="button" onClick={onLogin}>
      Login Mock
    </button>
  ),
}));

jest.mock('./pages/LandingPage', () => ({
  __esModule: true,
  default: () => <div>Landing Mock</div>,
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

jest.mock('./pages/media/CampaignsPage', () => ({
  __esModule: true,
  default: () => <div>Kampagnen Mock</div>,
}));

import App from './App';

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

  it('renders the real operator shell chrome for authenticated routes', async () => {
    render(<App />);

    expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Schnellmenü öffnen/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Navigation öffnen/i })).toBeInTheDocument();
  });

  it('redirects root and legacy dashboard routes to /virus-radar and shows the five PEIX work areas', async () => {
    const firstRender = render(<App />);

    expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/virus-radar');

    firstRender.unmount();
    window.history.pushState({}, '', '/dashboard');

    render(<App />);

    expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/virus-radar');

    const operatorNav = screen.getByRole('navigation', { name: 'Arbeitsbereiche' });
    const navLinks = within(operatorNav).getAllByRole('link');

    expect(navLinks).toHaveLength(6);
    expect(within(operatorNav).getByRole('link', { name: /Virus-Radar/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('link', { name: /Diese Woche/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('link', { name: /Zeitgraph/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('link', { name: /Regionen/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('link', { name: /Kampagnen/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('link', { name: /Evidenz/i })).toBeInTheDocument();
    expect(within(operatorNav).queryByRole('link', { name: /Dashboard/i })).not.toBeInTheDocument();
  });

  describe('when logged out', () => {
    beforeEach(() => {
      mockRehydrateAuth.mockResolvedValue(false);
    });

    it('renders the landing page at /', async () => {
      render(<App />);

      expect(await screen.findByText('Landing Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/');
    });

    it('redirects /welcome to / and renders the landing page there', async () => {
      window.history.pushState({}, '', '/welcome');

      render(<App />);

      expect(await screen.findByText('Landing Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/');
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

  it('renders the dedicated Zeitgraph route as its own work area', async () => {
    window.history.pushState({}, '', '/zeitgraph');

    render(<App />);

    expect(await screen.findByText('Zeitgraph Mock')).toBeInTheDocument();

    const operatorNav = screen.getByRole('navigation', { name: 'Arbeitsbereiche' });
    expect(within(operatorNav).getByRole('link', { name: /Zeitgraph/i })).toHaveAttribute('aria-current', 'page');
  });

  it('keeps an explicit virus-radar URL after auth instead of redirecting elsewhere', async () => {
    window.history.pushState({}, '', '/virus-radar');

    render(<App />);

    expect(await screen.findByText('Virus-Radar Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/virus-radar');
  });
});
