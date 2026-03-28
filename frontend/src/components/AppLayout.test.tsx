import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import AppLayout from './AppLayout';
import { useAuth, useTheme } from '../App';

jest.mock('../App', () => ({
  useTheme: jest.fn(),
  useAuth: jest.fn(),
}));

jest.mock('../lib/api', () => ({
  apiFetch: jest.fn(),
}));

const mockedUseTheme = useTheme as jest.MockedFunction<typeof useTheme>;
const mockedUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

describe('AppLayout theme rendering', () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockedUseAuth.mockReturnValue({
      authenticated: true,
      handleLogin: jest.fn(),
      handleLogout: jest.fn(),
    });
  });

  it('shows the dark-mode activation label in light theme', () => {
    mockedUseTheme.mockReturnValue({
      theme: 'light',
      toggle: jest.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/jetzt']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppLayout>
          <div>Inhalt</div>
        </AppLayout>
      </MemoryRouter>,
    );

    expect(screen.getByLabelText('Schnellmenü öffnen')).toBeInTheDocument();
    expect(screen.getByRole('banner')).toHaveClass('surface-header');
    expect(screen.getByRole('link', { name: 'Direkt zum Inhalt springen' })).toHaveAttribute('href', '#main-content');
    expect(screen.queryByText('Wochenbericht exportieren')).not.toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('aria-labelledby', 'operator-page-title');
    expect(screen.getByRole('heading', { name: 'Was PEIX diese Woche tun sollte' })).toBeInTheDocument();
    expect(screen.getByText('Eine klare Wochensteuerung: zuerst die wichtigste Richtung, dann Vertrauen und nächste sinnvolle Schritte.')).toBeInTheDocument();
    expect(screen.getByText('Eine Hauptentscheidung zuerst. Details erst im zweiten Blick.')).toBeInTheDocument();
    expect(screen.getByText('Was PEIX diese Woche zuerst tun sollte')).toBeInTheDocument();
    expect(screen.getByText('Bundesland-Ebene, nicht Stadt-Ebene.')).toBeInTheDocument();
  });

  it('shows the light-mode activation label in dark theme', () => {
    mockedUseTheme.mockReturnValue({
      theme: 'dark',
      toggle: jest.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/jetzt']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppLayout>
          <div>Inhalt</div>
        </AppLayout>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByLabelText('Schnellmenü öffnen'));
    expect(screen.getByRole('menuitem', { name: 'Helles Design aktivieren' })).toBeInTheDocument();
  });

  it('stores and restores the dense mode preference', () => {
    mockedUseTheme.mockReturnValue({
      theme: 'light',
      toggle: jest.fn(),
    });

    const { unmount } = render(
      <MemoryRouter initialEntries={['/jetzt']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppLayout>
          <div>Inhalt</div>
        </AppLayout>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByLabelText('Schnellmenü öffnen'));
    fireEvent.click(screen.getByRole('button', { name: 'Dense' }));

    expect(window.localStorage.getItem('viralflux-density-mode')).toBe('dense');
    expect(document.querySelector('.app-shell--operator')).toHaveAttribute('data-density', 'dense');

    unmount();

    render(
      <MemoryRouter initialEntries={['/jetzt']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppLayout>
          <div>Inhalt</div>
        </AppLayout>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByLabelText('Schnellmenü öffnen'));
    expect(screen.getByRole('button', { name: 'Dense' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('opens and closes the mobile navigation with keyboard-friendly controls', () => {
    mockedUseTheme.mockReturnValue({
      theme: 'light',
      toggle: jest.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/jetzt']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppLayout>
          <div>Inhalt</div>
        </AppLayout>
      </MemoryRouter>,
    );

    const openButton = screen.getByRole('button', { name: 'Navigation öffnen' });
    fireEvent.click(openButton);

    const closeButton = screen.getByRole('button', { name: 'Navigation schließen' });
    expect(closeButton).toHaveAttribute('aria-expanded', 'true');

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.getByRole('button', { name: 'Navigation öffnen' })).toBeInTheDocument();
  });
});
