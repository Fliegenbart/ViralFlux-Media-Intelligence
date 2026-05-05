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

jest.mock('./pages/cockpit/triLayer/TriLayerPage', () => ({
  __esModule: true,
  default: () => <div>Tri-Layer Mock</div>,
}));

jest.mock('./pages/cockpit/phaseLead/PhaseLeadResearchPage', () => ({
  __esModule: true,
  default: () => <div>Phase-Lead Mock</div>,
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

  it('keeps the Tri-Layer research route reachable under /cockpit/tri-layer', async () => {
    window.history.pushState({}, '', '/cockpit/tri-layer');

    render(<App />);

    expect(await screen.findByText('Tri-Layer Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/cockpit/tri-layer');
  });

  it('keeps the Phase-Lead product route reachable under /cockpit/phase-lead', async () => {
    window.history.pushState({}, '', '/cockpit/phase-lead');

    render(<App />);

    expect(await screen.findByText('Phase-Lead Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/cockpit/phase-lead');
  });

  it('redirects cockpit design variants to the current cockpit', async () => {
    window.history.pushState({}, '', '/cockpit/variante-1');

    const view = render(<App />);

    expect(await screen.findByText('Cockpit Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/cockpit');

    view.unmount();
    window.history.pushState({}, '', '/cockpit/variante-2');

    render(<App />);

    expect(await screen.findByText('Cockpit Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/cockpit');
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
