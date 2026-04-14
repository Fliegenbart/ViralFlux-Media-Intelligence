import '@testing-library/jest-dom';
import React from 'react';
import { act, render } from '@testing-library/react';

import VirusRadarPage from './VirusRadarPage';

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

jest.mock('../../components/cockpit/VirusRadarWorkspace', () => ({
  __esModule: true,
  default: () => <div>Virus-Radar-Ansicht</div>,
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
  useRegionsPageData: () => ({
    regionsView: {
      map: {
        activation_suggestions: [{ region: 'BE' }],
        top_regions: [{ code: 'BE' }],
      },
    },
  }),
  useVirusRadarHeroForecast: () => ({
    loading: false,
    heroForecast: {
      availableViruses: ['Influenza A'],
      chartData: [],
      summaries: [],
    },
  }),
  useNowPageData: () => mockNowPageData,
  useCampaignsPageData: () => ({ campaignsView: null }),
  useEvidencePageData: () => ({ evidence: null }),
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

describe('VirusRadarPage page header', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockNowPageData = {
      view: {
        heroRecommendation: {
          direction: 'Aktivieren',
          region: 'Berlin',
          whyNow: 'Berlin ist diese Woche der stärkste Fall.',
        },
        focusRegion: {
          code: 'BE',
          name: 'Berlin',
          recommendationId: 'rec-1',
        },
      },
    };
  });

  it('opens the focus recommendation from the header when one is already linked', async () => {
    render(<VirusRadarPage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Empfehlung prüfen');
    expect(latestHeader?.secondaryAction?.label).toBe('Regionen öffnen');
    expect(latestHeader?.secondaryAction?.to).toBe('/regionen');

    await act(async () => {
      await latestHeader.primaryAction.onClick();
    });

    expect(mockOpenRecommendation).toHaveBeenCalledWith('rec-1', 'overlay');
  });

  it('sends the user into the regions flow when no recommendation is linked yet', async () => {
    mockNowPageData = {
      view: {
        heroRecommendation: null,
        focusRegion: {
          code: 'BE',
          name: 'Berlin',
          recommendationId: null,
        },
      },
    };

    render(<VirusRadarPage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Regionen öffnen');

    await act(async () => {
      await latestHeader.primaryAction.onClick();
    });

    expect(mockNavigate).toHaveBeenCalledWith('/regionen', { state: { regionCode: 'BE' } });
  });
});
