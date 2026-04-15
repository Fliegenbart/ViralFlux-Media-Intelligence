import '@testing-library/jest-dom';
import React from 'react';
import { act, render, screen } from '@testing-library/react';

import VirusRadarPage from './VirusRadarPage';

const mockSetPageHeader = jest.fn();
const mockClearPageHeader = jest.fn();
const mockToast = jest.fn();
const mockOpenRecommendation = jest.fn();

type MockNowPageView = {
  primaryActionLabel: string;
  primaryRecommendationId: string | null;
  heroRecommendation: {
    actionLabel?: string;
    ctaDisabled: boolean;
    direction?: string;
    region?: string;
    whyNow?: string;
  } | null;
  focusRegion: {
    code: string;
    name: string;
    recommendationId?: string | null;
  } | null;
};

type MockNowPageData = {
  loading?: boolean;
  workspaceStatus?: null;
  forecast: null;
  focusRegionBacktest: null;
  focusRegionBacktestLoading: boolean;
  waveOutlook?: null;
  waveOutlookLoading?: boolean;
  waveRadar?: null;
  waveRadarLoading?: boolean;
  view: MockNowPageView;
};

type MockWorkspaceProps = {
  view: MockNowPageView;
  forecast: null;
  focusRegionBacktest: null;
  focusRegionBacktestLoading: boolean;
  horizonDays: number;
  primaryActionLabel: string;
  onPrimaryAction: () => Promise<void> | void;
};

const mockWorkspaceProps = jest.fn<void, [MockWorkspaceProps]>();
let mockNowPageData: MockNowPageData;

jest.mock('../../components/AnimatedPage', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock('../../components/cockpit/SimplifiedDecisionWorkspace', () => ({
  __esModule: true,
  default: (props: MockWorkspaceProps) => {
    mockWorkspaceProps(props);
    return <div>Entscheidungsansicht</div>;
  },
}));

jest.mock('../../lib/appContext', () => ({
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

describe('VirusRadarPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockNowPageData = {
      view: {
        heroRecommendation: {
          direction: 'Aktivieren',
          region: 'Berlin',
          whyNow: 'Berlin ist diese Woche der stärkste Fall.',
          ctaDisabled: false,
        },
        focusRegion: {
          code: 'BE',
          name: 'Berlin',
          recommendationId: 'rec-1',
        },
        primaryActionLabel: 'Empfehlung pruefen',
        primaryRecommendationId: 'rec-1',
      },
      forecast: null,
      focusRegionBacktest: null,
      focusRegionBacktestLoading: false,
      workspaceStatus: null,
    };
  });

  it('renders the simplified decision workspace and opens the linked recommendation', async () => {
    render(<VirusRadarPage />);

    expect(screen.getByText('Entscheidungsansicht')).toBeInTheDocument();
    expect(mockSetPageHeader).not.toHaveBeenCalled();
    expect(mockClearPageHeader).toHaveBeenCalledTimes(1);

    const latestProps = mockWorkspaceProps.mock.calls.at(-1)?.[0];

    expect(latestProps?.primaryActionLabel).toBe('Empfehlung pruefen');

    await act(async () => {
      await latestProps?.onPrimaryAction();
    });

    expect(mockOpenRecommendation).toHaveBeenCalledWith('rec-1', 'overlay');
  });

  it('falls back to a details action when no live recommendation can be opened', async () => {
    mockNowPageData = {
      view: {
        heroRecommendation: {
          direction: 'Beobachten',
          region: 'Berlin',
          whyNow: 'Es gibt erste Signale, aber noch keine klare Freigabe.',
          ctaDisabled: true,
        },
        focusRegion: {
          code: 'BE',
          name: 'Berlin',
          recommendationId: null,
        },
        primaryActionLabel: 'Empfehlung pruefen',
        primaryRecommendationId: null,
      },
      forecast: null,
      focusRegionBacktest: null,
      focusRegionBacktestLoading: false,
      workspaceStatus: null,
    };

    render(<VirusRadarPage />);

    const latestProps = mockWorkspaceProps.mock.calls.at(-1)?.[0];

    expect(latestProps?.primaryActionLabel).toBe('Details ansehen');

    await act(async () => {
      await latestProps?.onPrimaryAction();
    });

    expect(mockOpenRecommendation).not.toHaveBeenCalled();
  });
});
