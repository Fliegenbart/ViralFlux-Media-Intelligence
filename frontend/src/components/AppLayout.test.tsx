import '@testing-library/jest-dom';
import React, { useEffect } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import AppLayout, { usePageHeader } from './AppLayout';
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

const SimplePage: React.FC = () => {
  const { clearPageHeader } = usePageHeader();

  useEffect(() => {
    return clearPageHeader;
  }, [clearPageHeader]);

  return <div>Kampagneninhalt</div>;
};

const HeaderActionPage: React.FC = () => {
  const { setPageHeader, clearPageHeader } = usePageHeader();

  useEffect(() => {
    setPageHeader({
      primaryAction: {
        label: 'Wochenbericht exportieren',
        onClick: jest.fn(),
      },
      secondaryAction: {
        label: 'Evidenz öffnen',
        onClick: jest.fn(),
      },
    });

    return clearPageHeader;
  }, [clearPageHeader, setPageHeader]);

  return <div>Wochenplaninhalt</div>;
};

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
    expect(screen.getByRole('banner')).toHaveClass('operator-header');
    expect(screen.getByRole('link', { name: 'Direkt zum Inhalt springen' })).toHaveAttribute('href', '#main-content');
    expect(screen.queryByText('Wochenbericht exportieren')).not.toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('aria-labelledby', 'operator-page-title');
    expect(screen.getByRole('heading', { name: 'Was PEIX diese Woche tun sollte' })).toBeInTheDocument();
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

  it('renders slim header and section context on the campaigns route', () => {
    mockedUseTheme.mockReturnValue({
      theme: 'light',
      toggle: jest.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/kampagnen']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppLayout>
          <SimplePage />
        </AppLayout>
      </MemoryRouter>,
    );

    expect(screen.getByRole('banner')).toHaveClass('operator-header');
    expect(screen.getByRole('main')).toHaveAttribute('aria-labelledby', 'operator-page-title');
    expect(screen.getByText('Kampagneninhalt')).toBeInTheDocument();
  });

  it('shows simplified section framing and the primary page action on the now route', () => {
    mockedUseTheme.mockReturnValue({
      theme: 'light',
      toggle: jest.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/jetzt']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppLayout>
          <HeaderActionPage />
        </AppLayout>
      </MemoryRouter>,
    );

    const banner = screen.getByRole('banner');
    const sectionFrame = screen.getByLabelText('Aktueller Bereich');
    const pageActions = screen.getByLabelText('Seitenaktionen');
    const primaryAction = screen.getByRole('button', { name: 'Wochenbericht exportieren' });
    const secondaryAction = screen.getByRole('button', { name: 'Evidenz öffnen' });

    expect(banner).not.toHaveTextContent('Arbeitsbereich');
    expect(sectionFrame).toHaveTextContent('ViralFlux');
    expect(sectionFrame).toHaveTextContent('Wochenplan');
    expect(screen.getByRole('heading', { name: 'Was PEIX diese Woche tun sollte' })).toBeVisible();
    expect(primaryAction).toBeVisible();
    expect(primaryAction).toHaveClass('operator-page-action--primary');
    expect(secondaryAction).toHaveClass('operator-page-action--secondary');
    expect(pageActions).toContainElement(primaryAction);
    expect(pageActions.lastElementChild).toBe(primaryAction);
  });
});
