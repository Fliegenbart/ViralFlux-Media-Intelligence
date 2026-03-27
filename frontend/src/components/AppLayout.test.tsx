import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import AppLayout from './AppLayout';
import { useAuth, useTheme } from '../App';
import { usePilotSurfaceData } from '../features/media/usePilotSurfaceData';
import { useMediaWorkflow } from '../features/media/workflowContext';

jest.mock('../App', () => ({
  useTheme: jest.fn(),
  useAuth: jest.fn(),
}));

jest.mock('../features/media/usePilotSurfaceData', () => ({
  usePilotSurfaceData: jest.fn(),
}));

jest.mock('../features/media/workflowContext', () => ({
  useMediaWorkflow: jest.fn(),
}));

jest.mock('../lib/api', () => ({
  apiFetch: jest.fn(),
}));

const mockedUseTheme = useTheme as jest.MockedFunction<typeof useTheme>;
const mockedUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockedUsePilotSurfaceData = usePilotSurfaceData as jest.MockedFunction<typeof usePilotSurfaceData>;
const mockedUseMediaWorkflow = useMediaWorkflow as jest.MockedFunction<typeof useMediaWorkflow>;

describe('AppLayout theme rendering', () => {
  beforeEach(() => {
    mockedUseAuth.mockReturnValue({
      authenticated: true,
      handleLogin: jest.fn(),
      handleLogout: jest.fn(),
    });
    mockedUseMediaWorkflow.mockReturnValue({
      virus: 'RSV A',
      setVirus: jest.fn(),
      brand: 'gelo',
      setBrand: jest.fn(),
      weeklyBudget: 120000,
      setWeeklyBudget: jest.fn(),
      campaignGoal: 'Sichtbarkeit aufbauen',
      setCampaignGoal: jest.fn(),
      dataVersion: 0,
      invalidateData: jest.fn(),
      selectedRecommendationId: null,
      recommendationOverlayMode: null,
      openRecommendation: jest.fn(),
      closeRecommendation: jest.fn(),
    });
    mockedUsePilotSurfaceData.mockReturnValue({
      loading: false,
      loadSurface: jest.fn(),
      pilotReadout: {
        generated_at: '2026-03-27T10:00:00Z',
        run_context: {
          generated_at: '2026-03-27T10:00:00Z',
          scope_readiness: 'WATCH',
          forecast_readiness: 'GO',
          commercial_validation_status: 'WATCH',
          gate_snapshot: {
            coverage_weeks: 24,
            missing_requirements: ['GELO-Outcome-Daten für eine Region fehlen noch.'],
          },
        },
        executive_summary: {
          what_should_we_do_now: 'GELO sollte diese Woche zuerst Bayern prüfen.',
          headline: 'Bayern und Nordrhein-Westfalen bleiben im Fokus, während die Evidenz noch nachgezogen wird.',
          top_regions: [
            {
              region_name: 'Bayern',
              recommended_product: 'Nasenspray',
              campaign_recommendation: 'Apotheken-Review vorbereiten',
            },
            {
              region_name: 'Nordrhein-Westfalen',
            },
          ],
        },
        operational_recommendations: {
          summary: {
            headline: 'Zwei Bundesländer sind sofort reviewwürdig.',
          },
          regions: [
            {
              region_name: 'Bayern',
              recommended_product: 'Nasenspray',
              campaign_recommendation: 'Apotheken-Review vorbereiten',
            },
          ],
        },
      } as any,
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

    expect(screen.getByLabelText('Dunkles Design aktivieren')).toBeInTheDocument();
    expect(screen.getByRole('banner')).toHaveClass('surface-header');
    expect(screen.getByRole('link', { name: 'Direkt zum Inhalt springen' })).toHaveAttribute('href', '#main-content');
    expect(screen.getByText('Wochenbericht exportieren')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Wochenüberblick' })).toBeInTheDocument();
    expect(screen.getAllByText('Mit Vorsicht').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Bayern, Nordrhein-Westfalen').length).toBeGreaterThan(0);
    expect(screen.getByText('Bayern · Nasenspray')).toBeInTheDocument();
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

    expect(screen.getByLabelText('Helles Design aktivieren')).toBeInTheDocument();
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
