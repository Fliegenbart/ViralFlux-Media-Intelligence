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

jest.mock('./cockpitUtils', () => ({
  __esModule: true,
  formatDateTime: (value?: string | null) => (value ? '24.03.2026 10:00' : '-'),
  truthFreshnessLabel: (value?: string | null) => value || 'fresh',
  truthLayerLabel: () => 'GELO-Datenbasis',
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

function buildReadyWorkspaceStatus(): WorkspaceStatusSummary {
  return {
    ...buildWorkspaceStatus(),
    open_blockers: 'Keine',
    blocker_count: 0,
    blockers: [],
    summary: 'Die Datenlage ist für die Wochenplanung belastbar genug.',
    items: buildWorkspaceStatus().items.map((item) => {
      if (item.key === 'customer_data_status') {
        return {
          ...item,
          value: 'Verbunden',
          detail: '24 Wochen verbunden · Produkte und Regionen abgedeckt',
          tone: 'success' as const,
        };
      }

      if (item.key === 'open_blockers') {
        return {
          ...item,
          value: 'Keine',
          detail: 'Aktuell gibt es keine offenen Blocker.',
          tone: 'success' as const,
        };
      }

      return item;
    }),
  };
}

describe('EvidencePanel', () => {
  it('puts readiness and the next step before trust details and technical sections', () => {
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

    const nextStep = screen.getByText('Nächster Schritt');
    const trust = screen.getByText('Was diese Aussage gerade trägt');
    const technical = screen.getByText('Für Technik und Details');

    expect(screen.getByText('Ist die Empfehlung diese Woche gut genug belegt?')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Fehlende Daten klären' })).toBeInTheDocument();
    expect(nextStep.compareDocumentPosition(trust) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(trust.compareDocumentPosition(technical) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows the trust and onboarding briefing before the technical sections', () => {
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

    expect(screen.getByText('Ist die Empfehlung diese Woche gut genug belegt?')).toBeInTheDocument();
    expect(screen.getByText('Aktueller Datenstatus')).toBeInTheDocument();
    expect(screen.getByText('Belastbarkeit')).toBeInTheDocument();
    expect(screen.getByText('Was diese Aussage gerade trägt')).toBeInTheDocument();
    expect(screen.getByText('Arbeitskontext')).toBeInTheDocument();
    expect(screen.getByText('Was bereits verbunden ist und was noch fehlt')).toBeInTheDocument();
    expect(screen.getByText('Bereits verbunden')).toBeInTheDocument();
    expect(screen.getByText('Fehlend oder offen')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Fehlende Daten klären' })).toHaveAttribute('href', '#evidence-import');
    expect(screen.getByRole('link', { name: 'CSV-Vorlage laden' })).toHaveAttribute('href', 'https://example.com/template.csv');
    expect(screen.getByText('Datenvollständigkeit')).toBeInTheDocument();
    expect(screen.getByText('Modell-Belastbarkeit')).toBeInTheDocument();
    expect(screen.getByText('Operative Einsatzreife')).toBeInTheDocument();
    expect(screen.getByText('Noch vorsichtig einordnen')).toBeInTheDocument();
    expect(screen.getAllByText('Ein Importfeld ist noch nicht sauber zugeordnet.').length).toBeGreaterThan(0);
    expect(screen.getByText('Kundendaten und Wirkung')).toBeInTheDocument();
    expect(screen.getByText('Import und Validierung')).toBeInTheDocument();
    expect(screen.getByText('Vorhersage und Monitoring (Details)')).toBeInTheDocument();
    expect(screen.getByText('Quellen & Grenzen')).toBeInTheDocument();
    expect(screen.getByText('Für Technik und Details')).toBeInTheDocument();
    expect(screen.getByText(/Gilt auf Bundesland-Ebene, nicht für einzelne Städte/i)).toBeInTheDocument();
    expect(screen.getAllByText(/nicht für einzelne Städte/i).length).toBeGreaterThan(0);
  });

  it('links the ready-state evidence CTA to a visible follow-up section', () => {
    render(
      <EvidencePanel
        evidence={{
          source_status: { items: [], live_count: 6, total: 6, live_ratio: 1 },
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
          },
          outcome_learning_summary: {
            outcome_signal_score: 0.74,
          },
        } as any}
        workspaceStatus={buildReadyWorkspaceStatus()}
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

    expect(screen.getByRole('link', { name: 'Datenlage prüfen' })).toHaveAttribute('href', '#evidence-onboarding');
  });

  it('announces the loading state for customer evidence data', () => {
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

    expect(screen.getByRole('status', { name: 'Kundendaten werden geladen' })).toBeInTheDocument();
    expect(screen.getByText('Daten werden geladen')).toBeInTheDocument();
  });

  it('does not show a customer import date when no customer data is actually connected', () => {
    render(
      <EvidencePanel
        evidence={{
          source_status: { items: [], live_count: 0, total: 0, live_ratio: 0 },
          truth_coverage: {
            coverage_weeks: 0,
            regions_covered: 0,
            products_covered: 0,
            truth_freshness_state: 'missing',
            last_imported_at: '2026-03-08T07:24:00Z',
            required_fields_present: [],
            conversion_fields_present: [],
          },
          truth_snapshot: {
            latest_batch: {
              uploaded_at: '2026-03-08T07:24:00Z',
            },
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

    expect(screen.queryByText(/Kundendaten-Import/i)).not.toBeInTheDocument();
  });
});
