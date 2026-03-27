import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, within } from '@testing-library/react';

jest.mock('./lib/api', () => ({
  ...jest.requireActual('./lib/api'),
  apiFetch: jest.fn(),
}));

jest.mock('./pages/media/NowPage', () => ({
  __esModule: true,
  default: () => <div>Jetzt Mock</div>,
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

  it('rehydrates auth state on app startup from browser storage', async () => {
    persistAuth(window.localStorage);

    render(<App />);

    expect(await screen.findByText('Jetzt Mock')).toBeInTheDocument();
  });

  it('redirects legacy dashboard routes to /jetzt and shows the four PEIX work areas', async () => {
    persistAuth(window.localStorage);
    window.history.pushState({}, '', '/dashboard');

    render(<App />);

    expect(await screen.findByText('Jetzt Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/jetzt');

    const operatorNav = screen.getByRole('navigation', { name: 'Arbeitsbereiche' });
    const navButtons = within(operatorNav).getAllByRole('button');

    expect(navButtons).toHaveLength(4);
    expect(within(operatorNav).getByRole('button', { name: /Wochenplan/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Regionen/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Kampagnen/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Evidenz/i })).toBeInTheDocument();
    expect(within(operatorNav).queryByRole('button', { name: /Dashboard/i })).not.toBeInTheDocument();
  });
});
