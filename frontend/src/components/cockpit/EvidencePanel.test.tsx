import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import EvidencePanel from './EvidencePanel';
import { WorkspaceStatusSummary } from '../../types/media';

jest.mock('./evidence/ForecastMonitoringSection', () => ({
  __esModule: true,
  default: () => <div>ForecastMonitoringSection Mock</div>,
}));

jest.mock('./evidence/WaveValidationSection', () => ({
  __esModule: true,
  default: () => <div>WaveValidationSection Mock</div>,
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
  it('shows the GELO trust and onboarding briefing before the technical sections', () => {
    render(
      <EvidencePanel
        evidence={{
          source_status: { items: [], live_count: 0, total: 0, live_ratio: 0 },
          recent_runs: [{ mode: 'forecast_monitoring', status: 'ok' }],
          truth_coverage: {
            coverage_weeks: 24,
            regions_covered: 9,
            products_covered: 3,
            truth_freshness_state: 'fresh',
            last_imported_at: '2026-03-24T10:00:00Z',
            required_fields_present: ['Produkt vorhanden'],
            conversion_fields_present: ['Outcome vorhanden'],
          },
          truth_snapshot: {
            latest_batch: {
              uploaded_at: '2026-03-24T10:00:00Z',
            },
            template_url: 'https://example.com/template.csv',
          },
          business_validation: {
            guidance: 'Die Datenlage reicht für vorsichtige Wochenplanung.',
          },
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

    expect(screen.getAllByText('Evidenz').length).toBeGreaterThan(0);
    expect(screen.getByText('Aktuelle Evidenzlage')).toBeInTheDocument();
    expect(screen.getByText('Worauf es sich stützt')).toBeInTheDocument();
    expect(screen.getByText('Was schon trägt')).toBeInTheDocument();
    expect(screen.getByText('Arbeitskontext')).toBeInTheDocument();
    expect(screen.getByText('Schon verbunden')).toBeInTheDocument();
    expect(screen.getByText('Fehlend oder blockiert')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Fehlende Daten klären' })).toHaveAttribute('href', '#evidence-import');
    expect(screen.getByRole('link', { name: 'CSV-Vorlage laden' })).toHaveAttribute('href', 'https://example.com/template.csv');
    expect(screen.getByText('Datenvollständigkeit')).toBeInTheDocument();
    expect(screen.getByText('Modell-Belastbarkeit')).toBeInTheDocument();
    expect(screen.getByText('Operative Einsatzreife')).toBeInTheDocument();
    expect(screen.getAllByText('Ein Importfeld ist noch nicht sauber zugeordnet.').length).toBeGreaterThan(0);
    expect(screen.getByText('Kundendaten (optional)')).toBeInTheDocument();
    expect(screen.getByText('Import prüfen')).toBeInTheDocument();
    expect(screen.getByText('Vorhersage (Details)')).toBeInTheDocument();
    expect(screen.getByText('Quellen & Grenzen')).toBeInTheDocument();
    expect(screen.getByText('Technische Tiefe')).toBeInTheDocument();
    expect(screen.getByText(/Bundesland-Ansicht, ohne Stadt-Prognose/i)).toBeInTheDocument();
    expect(screen.getAllByText(/nicht für einzelne Städte/i).length).toBeGreaterThan(0);
  });

  it('announces the loading state for GELO trust data', () => {
    render(
      <EvidencePanel
        evidence={null}
        workspaceStatus={null}
        loading
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

    expect(screen.getByRole('status', { name: 'GELO-Datenlage wird geladen' })).toBeInTheDocument();
    expect(screen.getByText('Evidenz wird geladen')).toBeInTheDocument();
  });
});
