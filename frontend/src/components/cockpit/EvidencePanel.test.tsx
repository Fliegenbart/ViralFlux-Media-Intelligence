import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import EvidencePanel from './EvidencePanel';
import { WorkspaceStatusSummary } from '../../types/media';

jest.mock('./evidence/ForecastMonitoringSection', () => ({
  __esModule: true,
  default: () => <div>ForecastMonitoringSection Mock</div>,
}));

jest.mock('./evidence/TruthOutcomeSection', () => ({
  __esModule: true,
  default: () => <div>TruthOutcomeSection Mock</div>,
}));

jest.mock('./evidence/SourceFreshnessSection', () => ({
  __esModule: true,
  default: () => <div>SourceFreshnessSection Mock</div>,
}));

jest.mock('./evidence/ImportValidationSection', () => ({
  __esModule: true,
  default: () => <div>ImportValidationSection Mock</div>,
}));

function buildWorkspaceStatus(): WorkspaceStatusSummary {
  return {
    forecast_status: 'Freigabe bereit',
    data_freshness: 'Aktuell',
    customer_data_status: 'im Aufbau',
    open_blockers: '1 offen',
    last_import_at: '2026-03-24T10:00:00Z',
    blocker_count: 1,
    blockers: ['Ein Importfeld ist noch nicht sauber zugeordnet.'],
    summary: 'Vor der Freigabe sollte der letzte offene Qualitätsblock noch geklärt werden.',
    items: [
      {
        key: 'forecast_status',
        question: 'Ist der Forecast stabil?',
        value: 'Freigabe bereit',
        detail: 'Monitoring stabil',
        tone: 'success',
      },
      {
        key: 'data_freshness',
        question: 'Sind die Daten frisch?',
        value: 'Aktuell',
        detail: '6/7 Quellen aktuell',
        tone: 'success',
      },
      {
        key: 'customer_data_status',
        question: 'Sind Kundendaten verbunden?',
        value: 'im Aufbau',
        detail: '24 Wochen verbunden',
        tone: 'warning',
      },
      {
        key: 'open_blockers',
        question: 'Gibt es offene Blocker?',
        value: '1 offen',
        detail: 'Ein Importfeld ist noch nicht sauber zugeordnet.',
        tone: 'warning',
      },
    ],
  };
}

describe('EvidencePanel', () => {
  it('shows the go-no-go summary first and keeps the technical blocks below', () => {
    render(
      <EvidencePanel
        evidence={{
          source_status: { items: [], live_count: 0, total: 0, live_ratio: 0 },
          recent_runs: [{ mode: 'forecast_monitoring', status: 'ok' }],
        } as any}
        workspaceStatus={buildWorkspaceStatus()}
        loading={false}
        marketValidation={null}
        marketValidationLoading={false}
        customerValidation={null}
        customerValidationLoading={false}
        truthPreview={null}
        truthBatchDetail={null}
        truthActionLoading={false}
        truthBatchDetailLoading={false}
        onSubmitTruthCsv={async () => {}}
        onLoadTruthBatchDetail={async () => {}}
      />,
    );

    expect(screen.getByText('Kannst du weitermachen?')).toBeInTheDocument();
    expect(screen.getByText('Die vier wichtigsten Prüfpunkte')).toBeInTheDocument();
    expect(screen.getByText('Das bremst die Freigabe gerade')).toBeInTheDocument();
    expect(screen.getAllByText('Ein Importfeld ist noch nicht sauber zugeordnet.').length).toBeGreaterThan(0);
    expect(screen.getByText('1. Vorhersage prüfen')).toBeInTheDocument();
    expect(screen.getByText('2. Kundendaten prüfen')).toBeInTheDocument();
    expect(screen.getByText('3. Quellen prüfen')).toBeInTheDocument();
    expect(screen.getByText('4. Import prüfen')).toBeInTheDocument();
    expect(screen.getByText('Technische Hinweise')).toBeInTheDocument();
  });
});
