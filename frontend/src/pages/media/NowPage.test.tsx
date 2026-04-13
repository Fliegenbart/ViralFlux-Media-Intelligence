import '@testing-library/jest-dom';
import React from 'react';
import { act, render } from '@testing-library/react';

import NowPage from './NowPage';

const mockSetPageHeader = jest.fn();
const mockClearPageHeader = jest.fn();
const mockToast = jest.fn();
const mockNavigate = jest.fn();
const mockOpenRecommendation = jest.fn();
let mockNowPageData: Record<string, unknown>;

jest.mock('../../components/AnimatedPage', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock('../../components/cockpit/NowWorkspace', () => ({
  __esModule: true,
  default: () => <div>Diese-Woche-Ansicht</div>,
}));

jest.mock('../../App', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('../../components/AppLayout', () => ({
  usePageHeader: () => ({
    setPageHeader: mockSetPageHeader,
    clearPageHeader: mockClearPageHeader,
    exportBriefingPdf: jest.fn(),
    pdfLoading: false,
  }),
}));

jest.mock('../../features/media/useMediaData', () => ({
  useNowPageData: () => mockNowPageData,
}));

jest.mock('../../features/media/workflowContext', () => ({
  useMediaWorkflow: () => ({
    virus: 'Influenza A',
    setVirus: jest.fn(),
    brand: 'PEIX',
    weeklyBudget: 120000,
    dataVersion: 1,
    openRecommendation: mockOpenRecommendation,
  }),
}));

jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

describe('NowPage page header', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockNowPageData = {
      loading: false,
      workspaceStatus: null,
      forecast: null,
      focusRegionBacktest: null,
      focusRegionBacktestLoading: false,
      waveOutlook: null,
      waveOutlookLoading: false,
      waveRadar: null,
      waveRadarLoading: false,
      view: {
        generatedAt: '2026-04-13T08:00:00Z',
        primaryActionLabel: 'Top-Empfehlung prüfen',
        primaryRecommendationId: 'rec-1',
        heroRecommendation: {
          actionLabel: 'Top-Empfehlung prüfen',
          ctaDisabled: false,
        },
        focusRegion: {
          code: 'BE',
          name: 'Berlin',
        },
      },
    };
  });

  it('uses the next recommendation step as the main header action', async () => {
    render(<NowPage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Top-Empfehlung prüfen');
    expect(latestHeader?.secondaryAction?.label).toBe('Zum Virus-Radar');
    expect(latestHeader?.secondaryAction?.to).toBe('/virus-radar');

    await act(async () => {
      await latestHeader.primaryAction.onClick();
    });

    expect(mockOpenRecommendation).toHaveBeenCalledWith('rec-1', 'overlay');
  });

  it('falls back to the focus region when the recommendation CTA is blocked', async () => {
    mockNowPageData = {
      ...mockNowPageData,
      view: {
        generatedAt: '2026-04-13T08:00:00Z',
        primaryActionLabel: 'Top-Empfehlung prüfen',
        primaryRecommendationId: 'rec-1',
        heroRecommendation: {
          actionLabel: 'Top-Empfehlung prüfen',
          ctaDisabled: true,
        },
        focusRegion: {
          code: 'BE',
          name: 'Berlin',
        },
      },
    };

    render(<NowPage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Fokusregion öffnen');

    await act(async () => {
      await latestHeader.primaryAction.onClick();
    });

    expect(mockNavigate).toHaveBeenCalledWith('/regionen', { state: { regionCode: 'BE' } });
  });
});
