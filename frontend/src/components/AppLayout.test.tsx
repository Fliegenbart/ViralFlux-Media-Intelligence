import '@testing-library/jest-dom';
import React, { useEffect } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import AppLayout, { usePageHeader } from './AppLayout';
import NowPage from '../pages/media/NowPage';
import { apiFetch } from '../lib/api';
import { useAuth, useTheme, useToast } from '../App';
import { useNowPageData } from '../features/media/useMediaData';
import { useMediaWorkflow } from '../features/media/workflowContext';

jest.mock('../App', () => ({
  useTheme: jest.fn(),
  useAuth: jest.fn(),
  useToast: jest.fn(),
}));

jest.mock('../lib/api', () => ({
  apiFetch: jest.fn(),
}));

jest.mock('./AnimatedPage', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock('./cockpit/NowWorkspace', () => ({
  __esModule: true,
  default: () => <div>Now workspace</div>,
}));

jest.mock('../features/media/useMediaData', () => ({
  useNowPageData: jest.fn(),
}));

jest.mock('../features/media/workflowContext', () => ({
  useMediaWorkflow: jest.fn(),
}));

const mockedUseTheme = useTheme as jest.MockedFunction<typeof useTheme>;
const mockedUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockedUseToast = useToast as jest.MockedFunction<typeof useToast>;
const mockedApiFetch = apiFetch as jest.MockedFunction<typeof apiFetch>;
const mockedUseNowPageData = useNowPageData as jest.MockedFunction<typeof useNowPageData>;
const mockedUseMediaWorkflow = useMediaWorkflow as jest.MockedFunction<typeof useMediaWorkflow>;

const SimplePage: React.FC = () => {
  const { clearPageHeader } = usePageHeader();

  useEffect(() => {
    return clearPageHeader;
  }, [clearPageHeader]);

  return <div>Kampagneninhalt</div>;
};

describe('AppLayout theme rendering', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  beforeEach(() => {
    window.localStorage.clear();
    mockedApiFetch.mockReset();
    mockedUseAuth.mockReturnValue({
      authenticated: true,
      handleLogin: jest.fn(),
      handleLogout: jest.fn(),
    });
    mockedUseToast.mockReturnValue({
      toast: jest.fn(),
    });
    mockedUseMediaWorkflow.mockReturnValue({
      virus: 'Influenza',
      setVirus: jest.fn(),
      brand: 'PEIX',
      weeklyBudget: 12000,
      dataVersion: 'v1',
      setBrand: jest.fn(),
      setWeeklyBudget: jest.fn(),
      campaignGoal: 'Awareness',
      setCampaignGoal: jest.fn(),
      invalidateData: jest.fn(),
      openRecommendation: jest.fn(),
      closeRecommendation: jest.fn(),
      recommendationOverlayMode: 'overlay',
      openDrawer: jest.fn(),
      closeDrawer: jest.fn(),
      activeDrawer: null,
    } as unknown as ReturnType<typeof useMediaWorkflow>);
    mockedUseNowPageData.mockReturnValue({
      loading: false,
      workspaceStatus: null,
      view: null,
      decision: null,
      evidence: null,
      forecast: null,
      allocation: null,
      campaignRecommendations: [],
      loadNowPage: jest.fn(),
      focusRegionBacktest: null,
      focusRegionBacktestLoading: false,
      waveOutlook: null,
      waveOutlookLoading: false,
      waveRadar: null,
      waveRadarLoading: false,
    } as unknown as ReturnType<typeof useNowPageData>);
    Object.defineProperty(URL, 'createObjectURL', {
      writable: true,
      value: jest.fn(() => 'blob:weekly-brief'),
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      writable: true,
      value: jest.fn(),
    });
    jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
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

  it('wires the real now page header actions into a simplified shell frame', async () => {
    mockedUseTheme.mockReturnValue({
      theme: 'light',
      toggle: jest.fn(),
    });
    let resolveGenerate: (() => void) | undefined;
    const generateRequest = new Promise<Response>((resolve) => {
      resolveGenerate = () => resolve({ ok: true } as Response);
    });
    mockedApiFetch
      .mockImplementationOnce(() => generateRequest)
      .mockResolvedValueOnce({
        blob: jest.fn().mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' })),
      } as unknown as Response);

    render(
      <MemoryRouter initialEntries={['/jetzt']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppLayout>
          <NowPage />
        </AppLayout>
      </MemoryRouter>,
    );

    const sectionFrame = screen.getByLabelText('Aktueller Bereich');
    const pageActions = screen.getByLabelText('Seitenaktionen');
    const primaryAction = screen.getByRole('button', { name: 'Wochenbericht exportieren' });
    const secondaryAction = screen.getByRole('button', { name: 'Evidenz öffnen' });

    expect(sectionFrame).toHaveTextContent('ViralFlux');
    expect(sectionFrame).toHaveTextContent('Wochenplan');
    expect(sectionFrame).not.toHaveTextContent('Arbeitsbereich');
    expect(screen.getByRole('heading', { name: 'Was PEIX diese Woche tun sollte' })).toBeVisible();
    expect(primaryAction).toBeVisible();
    expect(primaryAction).toHaveClass('operator-page-action--primary');
    expect(secondaryAction).toHaveClass('operator-page-action--secondary');
    expect(pageActions).toContainElement(primaryAction);
    expect(pageActions.lastElementChild).toBe(primaryAction);

    fireEvent.click(primaryAction);

    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith('/api/v1/media/weekly-brief/generate', { method: 'POST' });
    });
    expect(screen.getByRole('button', { name: 'Bericht wird erstellt...' })).toBeDisabled();

    resolveGenerate?.();

    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith('/api/v1/media/weekly-brief/latest');
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Wochenbericht exportieren' })).toBeEnabled();
    });
  });
});
