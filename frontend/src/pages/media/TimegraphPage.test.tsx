import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import TimegraphPage from './TimegraphPage';

const mockSetVirus = jest.fn();
const mockSetSelectedRegion = jest.fn();
const mockSetPageHeader = jest.fn();
const mockClearPageHeader = jest.fn();

jest.mock('../../App', () => ({
  useToast: () => ({
    toast: jest.fn(),
  }),
}));

jest.mock('../../components/AppLayout', () => ({
  usePageHeader: () => ({
    setPageHeader: mockSetPageHeader,
    clearPageHeader: mockClearPageHeader,
  }),
}));

jest.mock('../../features/media/workflowContext', () => ({
  useMediaWorkflow: () => ({
    virus: 'Influenza A',
    setVirus: mockSetVirus,
    dataVersion: 0,
  }),
}));

jest.mock('../../features/media/useMediaData', () => ({
  useTimegraphPageData: () => ({
    selectedRegion: 'BE',
    setSelectedRegion: mockSetSelectedRegion,
    selectedPrediction: {
      bundesland: 'BE',
      bundesland_name: 'Berlin',
    },
    regionOptions: [
      { code: 'BE', name: 'Berlin' },
      { code: 'BY', name: 'Bayern' },
    ],
    regionalBacktest: {
      bundesland: 'BE',
      bundesland_name: 'Berlin',
      timeline: [],
    },
    loading: false,
    backtestLoading: false,
    horizonDays: 7,
  }),
}));

jest.mock('../../components/cockpit/BacktestVisuals', () => ({
  FocusRegionOutlookPanel: ({ minimal, horizonDays }: { minimal?: boolean; horizonDays: number }) => (
    <div data-testid="focus-region-graph">
      {minimal ? 'minimal' : 'default'}-{horizonDays}
    </div>
  ),
}));

describe('TimegraphPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders a reduced graph page with virus chips, region select and a minimal graph', () => {
    render(<TimegraphPage />);

    expect(screen.getByText(/Influenza A lädt — Berlin/)).toBeInTheDocument();
    expect(screen.getByText(/Horizont 7 Tage/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Influenza A' })).toBeInTheDocument();
    expect(screen.getByLabelText('Bundesland wählen')).toBeInTheDocument();
    expect(screen.getByTestId('focus-region-graph')).toHaveTextContent('minimal-7');

    fireEvent.click(screen.getByRole('button', { name: 'Influenza B' }));
    expect(mockSetVirus).toHaveBeenCalledWith('Influenza B');

    fireEvent.change(screen.getByLabelText('Bundesland wählen'), { target: { value: 'BY' } });
    expect(mockSetSelectedRegion).toHaveBeenCalledWith('BY');
  });
});
