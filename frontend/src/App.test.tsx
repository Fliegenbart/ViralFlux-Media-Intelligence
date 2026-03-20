import '@testing-library/jest-dom';
import React from 'react';
import { render, screen, within } from '@testing-library/react';

jest.mock('./lib/api', () => ({
  isAuthenticated: () => true,
  logout: jest.fn(),
  apiFetch: jest.fn(),
}));

jest.mock('./pages/media/NowPage', () => ({
  __esModule: true,
  default: () => <div>Jetzt Mock</div>,
}));

import App from './App';

describe('App routing', () => {
  it('redirects legacy dashboard routes to /jetzt and shows the four PEIX work areas', async () => {
    window.history.pushState({}, '', '/dashboard');

    render(<App />);

    expect(await screen.findByText('Jetzt Mock')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/jetzt');

    const operatorNav = screen.getByRole('navigation', { name: 'Arbeitsbereiche' });
    const navButtons = within(operatorNav).getAllByRole('button');

    expect(navButtons).toHaveLength(4);
    expect(within(operatorNav).getByRole('button', { name: /Jetzt/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Regionen/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Kampagnen/i })).toBeInTheDocument();
    expect(within(operatorNav).getByRole('button', { name: /Qualität/i })).toBeInTheDocument();
    expect(within(operatorNav).queryByRole('button', { name: /Dashboard/i })).not.toBeInTheDocument();
  });
});
