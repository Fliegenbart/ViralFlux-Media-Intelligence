import '@testing-library/jest-dom';
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import CampaignsPage from './CampaignsPage';
import RegionsPage from './RegionsPage';
import { mediaApi } from '../../features/media/api';

const mockSetPageHeader = jest.fn();
const mockClearPageHeader = jest.fn();
const mockToast = jest.fn();
const mockNavigate = jest.fn();
const mockInvalidateData = jest.fn();
const mockOpenRecommendation = jest.fn();
const mockCloseRecommendation = jest.fn();
const mockLoadCampaigns = jest.fn().mockResolvedValue(undefined);
const mockLoadRegions = jest.fn().mockResolvedValue(undefined);
let mockCampaignsPageData: {
  campaignsView: MockCampaignsView | null;
  campaignsLoading: boolean;
  loadCampaigns: typeof mockLoadCampaigns;
  workspaceStatus: MockWorkspaceStatus;
};
let mockRegionsPageData: {
  regionsView: MockRegionsView | null;
  regionsLoading: boolean;
  loadRegions: typeof mockLoadRegions;
  workspaceStatus: MockWorkspaceStatus;
};

type MockCampaignCard = {
  id: string;
  status?: string;
  lifecycle_state?: string;
  publish_blockers: string[];
};

type MockCampaignsView = {
  cards: MockCampaignCard[];
};

type MockRegionEntry = {
  name: string;
  signal_score?: number;
  source_trace?: string[];
  signal_drivers?: Array<{ label: string; strength_pct: number }>;
  recommendation_ref?: {
    card_id: string;
  };
};

type MockRegionsView = {
  map: {
    top_regions: Array<{ code: string }>;
    regions: Record<string, MockRegionEntry>;
    activation_suggestions: Array<{
      region: string;
      priority: string;
    }>;
  };
};

type MockWorkspaceStatus = {
  blocker_count: number;
  blockers: string[];
} | null;

jest.mock('../../components/AnimatedPage', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock('../../components/cockpit/CampaignStudio', () => ({
  __esModule: true,
  default: () => <div>Kampagnenansicht</div>,
}));

jest.mock('../../components/cockpit/RegionWorkbench', () => ({
  __esModule: true,
  default: ({ onGenerateRegionCampaign }: { onGenerateRegionCampaign: (code: string) => void }) => (
    <button onClick={() => onGenerateRegionCampaign('BE')}>Region öffnen</button>
  ),
}));

jest.mock('../../lib/appContext', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('../../components/AppLayout', () => ({
  usePageHeader: () => ({
    setPageHeader: mockSetPageHeader,
    clearPageHeader: mockClearPageHeader,
  }),
}));

jest.mock('../../features/media/api', () => ({
  mediaApi: {
    generateRecommendations: jest.fn(),
    openRegionCampaign: jest.fn(),
  },
}));

jest.mock('../../features/media/useMediaData', () => ({
  useCampaignsPageData: () => mockCampaignsPageData,
  useRegionsPageData: () => mockRegionsPageData,
}));

jest.mock('../../features/media/workflowContext', () => ({
  useMediaWorkflow: () => ({
    brand: 'platform',
    setBrand: jest.fn(),
    weeklyBudget: 120000,
    setWeeklyBudget: jest.fn(),
    campaignGoal: 'Sichtbarkeit steigern',
    setCampaignGoal: jest.fn(),
    virus: 'Influenza A',
    setVirus: jest.fn(),
    dataVersion: 1,
    invalidateData: mockInvalidateData,
    openRecommendation: mockOpenRecommendation,
    closeRecommendation: mockCloseRecommendation,
    recommendationOverlayMode: 'overlay',
  }),
}));

jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({}),
  useLocation: () => ({ state: null }),
}));

describe('media page defaults', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCampaignsPageData = {
      campaignsView: null,
      campaignsLoading: false,
      loadCampaigns: mockLoadCampaigns,
      workspaceStatus: null,
    };
    mockRegionsPageData = {
      regionsView: {
        map: {
          top_regions: [{ code: 'BE' }],
          regions: {
            BE: {
              name: 'Berlin',
              signal_score: 0.82,
              source_trace: ['AMELAG', 'SurvStat'],
              signal_drivers: [{ label: 'Abwasser', strength_pct: 74 }],
              recommendation_ref: {
                card_id: 'rec-region-1',
              },
            },
          },
          activation_suggestions: [
            {
              region: 'BE',
              priority: 'hoch',
            },
          ],
        },
      },
      regionsLoading: false,
      loadRegions: mockLoadRegions,
      workspaceStatus: null,
    };
    (mediaApi.generateRecommendations as jest.Mock).mockResolvedValue({ cards: [] });
    (mediaApi.openRegionCampaign as jest.Mock).mockResolvedValue({ action: 'created', card_id: 'rec-1' });
  });

  it('uses a neutral all-products default when generating recommendations', async () => {
    render(<CampaignsPage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Vorschläge erstellen');
    expect(latestHeader?.secondaryAction?.label).toBe('Zum Virus-Radar');

    await act(async () => {
      await latestHeader.primaryAction.onClick();
    });

    await waitFor(() => {
      expect(mediaApi.generateRecommendations).toHaveBeenCalledWith(
        expect.objectContaining({
          product: 'Alle Produkte',
        }),
      );
    });
  });

  it('opens the focus recommendation from the page header when a campaign is already in focus', async () => {
    mockCampaignsPageData = {
      campaignsView: {
        cards: [
          {
            id: 'rec-focus-1',
            status: 'NEW',
            lifecycle_state: 'REVIEW',
            publish_blockers: [],
          },
        ],
      },
      campaignsLoading: false,
      loadCampaigns: mockLoadCampaigns,
      workspaceStatus: null,
    };

    render(<CampaignsPage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Empfehlung prüfen');

    await act(async () => {
      await latestHeader.primaryAction.onClick();
    });

    expect(mockNavigate).toHaveBeenCalledWith('/kampagnen/rec-focus-1');
    expect(mediaApi.generateRecommendations).not.toHaveBeenCalled();
  });

  it('opens the selected region recommendation from the page header when one already exists', async () => {
    render(<RegionsPage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Regionalen Vorschlag öffnen');
    expect(latestHeader?.secondaryAction?.label).toBe('Zum Virus-Radar');

    await act(async () => {
      await latestHeader.primaryAction.onClick();
    });

    expect(mockOpenRecommendation).toHaveBeenCalledWith('rec-region-1', 'overlay');
    expect(mediaApi.openRegionCampaign).not.toHaveBeenCalled();
  });

  it('uses a neutral all-products default when a regional action must be created from the header', async () => {
    mockRegionsPageData = {
      regionsView: {
        map: {
          top_regions: [{ code: 'BE' }],
          regions: {
            BE: {
              name: 'Berlin',
              signal_score: 0.82,
              source_trace: ['AMELAG', 'SurvStat'],
              signal_drivers: [{ label: 'Abwasser', strength_pct: 74 }],
            },
          },
          activation_suggestions: [
            {
              region: 'BE',
              priority: 'hoch',
            },
          ],
        },
      },
      regionsLoading: false,
      loadRegions: mockLoadRegions,
      workspaceStatus: null,
    };

    render(<RegionsPage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Regionalen Vorschlag vorbereiten');

    await act(async () => {
      await latestHeader.primaryAction.onClick();
    });

    await waitFor(() => {
      expect(mediaApi.openRegionCampaign).toHaveBeenCalledWith(
        expect.objectContaining({
          product: 'Alle Produkte',
        }),
      );
    });
  });
});
