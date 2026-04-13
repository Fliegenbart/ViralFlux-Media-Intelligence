import '@testing-library/jest-dom';
import React from 'react';
import { render } from '@testing-library/react';

import EvidencePage from './EvidencePage';

const mockSetPageHeader = jest.fn();
const mockClearPageHeader = jest.fn();
const mockInvalidateData = jest.fn();
let mockEvidencePageData: Record<string, unknown>;

jest.mock('../../components/AnimatedPage', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock('../../components/cockpit/EvidencePanel', () => ({
  __esModule: true,
  default: () => <div>Evidenzansicht</div>,
}));

jest.mock('../../App', () => ({
  useToast: () => ({ toast: jest.fn() }),
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
    brand: 'PEIX',
    dataVersion: 1,
    invalidateData: mockInvalidateData,
  }),
}));

jest.mock('../../features/media/useMediaData', () => ({
  useEvidencePageData: () => mockEvidencePageData,
}));

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}));

describe('EvidencePage page header', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockEvidencePageData = {
      evidence: {
        source_status: {
          items: [{ status_color: 'amber' }],
        },
        truth_coverage: {
          coverage_weeks: 0,
        },
      },
      evidenceLoading: false,
      workspaceStatus: {
        blocker_count: 1,
        blockers: ['Kundendaten fehlen noch.'],
      },
      marketValidation: null,
      marketValidationLoading: false,
      customerValidation: null,
      customerValidationLoading: false,
      truthPreview: null,
      truthBatchDetail: null,
      truthActionLoading: false,
      truthBatchDetailLoading: false,
      submitTruthCsv: jest.fn(),
      loadTruthBatchDetail: jest.fn(),
    };
  });

  it('points the header to missing evidence when import or blockers still need attention', () => {
    render(<EvidencePage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Fehlende Evidenz klären');
    expect(latestHeader?.primaryAction?.href).toBe('#evidence-import');
    expect(latestHeader?.secondaryAction?.to).toBe('/virus-radar');
  });

  it('points the header to the evidence overview when the data base is already strong enough', () => {
    mockEvidencePageData = {
      ...mockEvidencePageData,
      evidence: {
        source_status: {
          items: [{ status_color: 'green' }],
        },
        truth_coverage: {
          coverage_weeks: 12,
        },
        truth_snapshot: {
          coverage: {
            coverage_weeks: 12,
          },
        },
      },
      workspaceStatus: {
        blocker_count: 0,
        blockers: [],
      },
    };

    render(<EvidencePage />);

    const latestHeader = mockSetPageHeader.mock.calls.at(-1)?.[0];
    expect(latestHeader?.primaryAction?.label).toBe('Evidenzlage prüfen');
    expect(latestHeader?.primaryAction?.href).toBe('#evidence-onboarding');
  });
});
