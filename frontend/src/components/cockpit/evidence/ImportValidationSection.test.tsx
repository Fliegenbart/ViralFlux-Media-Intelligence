import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import ImportValidationSection from './ImportValidationSection';

describe('ImportValidationSection', () => {
  it('hides validation-only batches from the visible GELO import history', () => {
    render(
      <ImportValidationSection
        truthSnapshot={{
          brand: 'GELO',
          coverage: {
            coverage_weeks: 0,
            regions_covered: 0,
            products_covered: 0,
            outcome_fields_present: [],
            trust_readiness: 'pending_truth_connection',
          },
          recent_batches: [
            {
              batch_id: 'validated-only',
              brand: 'GELO',
              source_label: 'manual_csv',
              file_name: 'gelo_truth_sample_30_weeks.csv',
              status: 'validated',
              rows_total: 30,
              rows_valid: 30,
              rows_imported: 0,
              rows_rejected: 0,
              rows_duplicate: 0,
              uploaded_at: '2026-03-08T07:24:00Z',
            },
          ],
          latest_batch: {
            batch_id: 'validated-only',
            brand: 'GELO',
            source_label: 'manual_csv',
            file_name: 'gelo_truth_sample_30_weeks.csv',
            status: 'validated',
            rows_total: 30,
            rows_valid: 30,
            rows_imported: 0,
            rows_rejected: 0,
            rows_duplicate: 0,
            uploaded_at: '2026-03-08T07:24:00Z',
          },
        }}
        truthPreview={null}
        truthBatchDetail={null}
        truthActionLoading={false}
        truthBatchDetailLoading={false}
        onSubmitTruthCsv={async () => {}}
        onLoadTruthBatchDetail={async () => {}}
      />,
    );

    expect(screen.getByText('Noch keine echten GELO-Importe vorhanden.')).toBeInTheDocument();
    expect(screen.queryByText('gelo_truth_sample_30_weeks.csv')).not.toBeInTheDocument();
    expect(screen.getByText('Wähle einen echten Import aus der Historie oder prüfe eine neue Datei.')).toBeInTheDocument();
    expect(screen.queryByText('1dac0298ec3d')).not.toBeInTheDocument();
  });

  it('shows real imported batches and lets the operator load their details', () => {
    const onLoadTruthBatchDetail = jest.fn();

    render(
      <ImportValidationSection
        truthSnapshot={{
          brand: 'GELO',
          coverage: {
            coverage_weeks: 12,
            regions_covered: 6,
            products_covered: 2,
            outcome_fields_present: ['sales_units'],
            trust_readiness: 'connected',
          },
          recent_batches: [
            {
              batch_id: 'imported-1',
              brand: 'GELO',
              source_label: 'crm_upload',
              file_name: 'gelo_truth_real.csv',
              status: 'imported',
              rows_total: 24,
              rows_valid: 24,
              rows_imported: 24,
              rows_rejected: 0,
              rows_duplicate: 0,
              uploaded_at: '2026-03-12T08:00:00Z',
              week_min: '2026-01-05',
              week_max: '2026-03-23',
              coverage_after_import: {
                coverage_weeks: 12,
                regions_covered: 6,
                products_covered: 2,
                outcome_fields_present: ['sales_units'],
                trust_readiness: 'connected',
              },
            },
          ],
          latest_batch: null,
        }}
        truthPreview={null}
        truthBatchDetail={null}
        truthActionLoading={false}
        truthBatchDetailLoading={false}
        onSubmitTruthCsv={async () => {}}
        onLoadTruthBatchDetail={onLoadTruthBatchDetail}
      />,
    );

    expect(screen.getByText('gelo_truth_real.csv')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /gelo_truth_real\.csv/i }));
    expect(onLoadTruthBatchDetail).toHaveBeenCalledWith('imported-1');
  });
});
