import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

jest.mock('./pages/cockpit/CockpitShell', () => ({
  __esModule: true,
  default: () => <div>Cockpit Mock</div>,
}));

jest.mock('./pages/cockpit/data/DataOfficePage', () => ({
  __esModule: true,
  default: () => <div>Data Office Mock</div>,
}));

jest.mock('./pages/cockpit/variants/VarianteExecutivePage', () => ({
  __esModule: true,
  default: () => <div>Variante Executive Mock</div>,
}));

jest.mock('./pages/cockpit/variants/VarianteTerminalPage', () => ({
  __esModule: true,
  default: () => <div>Variante Terminal Mock</div>,
}));

import App from './App';

describe('App routing', () => {
  beforeEach(() => {
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

  it('redirects root to the cockpit as the single live surface', async () => {
    render(<App />);

    expect(await screen.findByText('Cockpit Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/cockpit');
  });

  it('keeps the Data Office reachable under /cockpit/data', async () => {
    window.history.pushState({}, '', '/cockpit/data');

    render(<App />);

    expect(await screen.findByText('Data Office Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/cockpit/data');
  });

  it('keeps cockpit variants reachable', async () => {
    window.history.pushState({}, '', '/cockpit/variante-1');

    const view = render(<App />);

    expect(await screen.findByText('Variante Executive Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/cockpit/variante-1');

    view.unmount();
    window.history.pushState({}, '', '/cockpit/variante-2');

    render(<App />);

    expect(await screen.findByText('Variante Terminal Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/cockpit/variante-2');
  });

  it('soft-redirects retired routes to the cockpit', async () => {
    const retiredPaths = [
      '/login',
      '/welcome',
      '/virus-radar',
      '/zeitgraph',
      '/kampagnen/123',
      '/dashboard/recommendations/123',
      '/entscheidung',
      '/pilot',
      '/bericht',
    ];

    for (const path of retiredPaths) {
      window.history.pushState({}, '', path);

      const view = render(<App />);

      expect(await screen.findByText('Cockpit Mock')).toBeInTheDocument();
      expect(window.location.pathname).toBe('/cockpit');

      view.unmount();
    }
  });
});
