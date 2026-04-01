import '@testing-library/jest-dom';
import { existsSync, readFileSync } from 'fs';
import { join } from 'path';
import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';

jest.mock('./lib/api', () => ({
  ...jest.requireActual('./lib/api'),
  apiFetch: jest.fn(),
}));

jest.mock('./pages/LoginPage', () => ({
  __esModule: true,
  default: () => <div>Login Mock</div>,
}));

jest.mock('./pages/media/MediaShell', () => {
  const React = require('react');
  const { Outlet, useLocation } = require('react-router-dom');

  const navItems = [
    { label: 'Wochenplan', path: '/jetzt' },
    { label: 'Zeitgraph', path: '/zeitgraph' },
    { label: 'Regionen', path: '/regionen' },
    { label: 'Kampagnen', path: '/kampagnen' },
    { label: 'Evidenz', path: '/evidenz' },
  ];

  return {
    __esModule: true,
    default: () => {
      const location = useLocation();

      return (
        <div>
          <nav aria-label="Arbeitsbereiche">
            {navItems.map((item) => (
              <button
                key={item.path}
                aria-current={location.pathname.startsWith(item.path) ? 'page' : undefined}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </nav>
          <Outlet />
        </div>
      );
    },
  };
});

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
import { AUTH_STORAGE_KEY, logout } from './lib/api';

function persistAuth(storage: Storage = window.localStorage) {
  storage.setItem(AUTH_STORAGE_KEY, JSON.stringify({
    token: 'stored-token',
    tokenExpiry: Date.now() + 60_000,
  }));
}

describe('App routing', () => {
  beforeEach(() => {
    logout();
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

  it('keeps the light foundation outside dark theme overrides', () => {
    const indexCss = readFileSync(join(__dirname, 'index.css'), 'utf8');
    const darkCss = readFileSync(join(__dirname, 'styles', 'dark.css'), 'utf8');
    const lightCssPath = join(__dirname, 'styles', 'light.css');

    expect(existsSync(lightCssPath)).toBe(true);
    expect(indexCss).toContain("@import './styles/light.css';");
    expect(darkCss).not.toMatch(/\[data-theme=["']light["']\]/);
    expect(readFileSync(lightCssPath, 'utf8')).toContain('.app-shell--operator');
  });

  it('rehydrates auth state on app startup from browser storage', async () => {
    persistAuth(window.localStorage);

    render(<App />);

    expect(await screen.findByText('Jetzt Mock')).toBeInTheDocument();
  });

  it('redirects legacy dashboard routes to /jetzt and shows the five PEIX work areas', async () => {
    persistAuth(window.localStorage);
    window.history.pushState({}, '', '/dashboard');

    render(<App />);

    expect(await screen.findByText('Jetzt Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/jetzt');

    const operatorNav = screen.getByRole('navigation', { name: 'Arbeitsbereiche' });
    const navButtons = within(operatorNav).getAllByRole('button');

    expect(navButtons).toHaveLength(5);
    expect(within(operatorNav).getByRole('button', { name: /Wochenplan/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Zeitgraph/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Regionen/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Kampagnen/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Evidenz/i })).toBeInTheDocument();
    expect(within(operatorNav).queryByRole('button', { name: /Dashboard/i })).not.toBeInTheDocument();
  });

  it('renders the dedicated Zeitgraph route as its own work area', async () => {
    persistAuth(window.localStorage);
    window.history.pushState({}, '', '/zeitgraph');

    render(<App />);

    expect(await screen.findByText('Zeitgraph Mock')).toBeInTheDocument();

    const operatorNav = screen.getByRole('navigation', { name: 'Arbeitsbereiche' });
    expect(within(operatorNav).getByRole('button', { name: /Zeitgraph/i })).toHaveAttribute('aria-current', 'page');
  });
});
