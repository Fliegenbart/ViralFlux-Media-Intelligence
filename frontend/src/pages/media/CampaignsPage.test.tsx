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

jest.mock('../../App', () => ({
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
  useCampaignsPageData: () => ({
    campaignsView: null,
    campaignsLoading: false,
    loadCampaigns: mockLoadCampaigns,
    workspaceStatus: null,
  }),
  useRegionsPageData: () => ({
    regionsView: { map: { top_regions: [{ code: 'BE' }] } },
    regionsLoading: false,
    loadRegions: mockLoadRegions,
    workspaceStatus: null,
  }),
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

  it('uses a neutral all-products default when opening a region campaign', async () => {
    render(<RegionsPage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Kampagnen öffnen');
    expect(latestHeader?.secondaryAction?.label).toBe('Zum Virus-Radar');

    fireEvent.click(screen.getByRole('button', { name: 'Region öffnen' }));

    await waitFor(() => {
      expect(mediaApi.openRegionCampaign).toHaveBeenCalledWith(
        expect.objectContaining({
          product: 'Alle Produkte',
        }),
      );
    });
  });
});
