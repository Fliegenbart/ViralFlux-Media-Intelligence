import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';

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
  default: () => <div>Login Mock</div>,
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

jest.mock('./pages/media/TimegraphPage', () => ({
  __esModule: true,
  default: () => <div>Zeitgraph Mock</div>,
}));

jest.mock('./features/media/usePilotSurfaceData', () => ({
  usePilotSurfaceData: () => ({
    pilotReadout: null,
    loading: false,
    loadSurface: jest.fn(),
  }),
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

    expect(await screen.findByText('Jetzt Mock')).toBeInTheDocument();
  });

  it('renders the real operator shell chrome for authenticated routes', async () => {
    render(<App />);

    expect(await screen.findByText('Jetzt Mock')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Schnellmenü öffnen/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Navigation öffnen/i })).toBeInTheDocument();
  });

  it('redirects legacy dashboard routes to /jetzt and shows the five PEIX work areas', async () => {
    window.history.pushState({}, '', '/dashboard');

    render(<App />);

    expect(await screen.findByText('Jetzt Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/jetzt');

    const operatorNav = screen.getByRole('navigation', { name: 'Arbeitsbereiche' });
    const navButtons = within(operatorNav).getAllByRole('button');

    expect(navButtons).toHaveLength(6);
    expect(within(operatorNav).getByRole('button', { name: /Virus-Radar/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Wochenplan/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Zeitgraph/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Regionen/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Kampagnen/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Evidenz/i })).toBeInTheDocument();
    expect(within(operatorNav).queryByRole('button', { name: /Dashboard/i })).not.toBeInTheDocument();
  });

  it('renders the dedicated Zeitgraph route as its own work area', async () => {
    window.history.pushState({}, '', '/zeitgraph');

    render(<App />);

    expect(await screen.findByText('Zeitgraph Mock')).toBeInTheDocument();

    const operatorNav = screen.getByRole('navigation', { name: 'Arbeitsbereiche' });
    expect(within(operatorNav).getByRole('button', { name: /Zeitgraph/i })).toHaveAttribute('aria-current', 'page');
  });
});
