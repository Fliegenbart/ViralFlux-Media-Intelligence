import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import { EvidenceStatusBar } from './EvidenceStatusBar';

describe('EvidenceStatusBar', () => {
  it('shows customer-data status without exposing the raw budget flag', () => {
    render(
      <EvidenceStatusBar
        snapshot={{
          client: 'GELO',
          virusTyp: 'Influenza A',
          virusLabel: 'Influenza A',
          isoWeek: 'KW 18 / 2026',
          generatedAt: '2026-04-30T10:00:00Z',
          systemStatus: {
            diagnostic_only: true,
            can_change_budget: false,
            global_status: 'diagnostic_only',
            operational_status: 'healthy',
            science_status: 'review',
            budget_status: 'diagnostic_only',
            latest_amelag_date: '2026-04-22',
            latest_survstat_date: '2026-04-20',
          },
          mediaSpendingTruth: {
            global_status: 'blocked',
            release_mode: 'shadow_only',
            budget_permission: 'manual_approval_required',
            max_approved_delta_pct: 0,
          },
          evidenceScore: {
            overallScore: 62.5,
            releaseStatus: 'blocked',
            label: 'Signal prüfen, Budget blockiert',
            components: [],
            blockers: ['missing_media_spend'],
            businessValidation: {
              validated_for_budget_activation: false,
              missing_requirements: ['missing_media_spend'],
            },
            plainLanguage: 'Budget bleibt blockiert, bis Business-Daten reichen.',
          },
          mediaPlan: {
            connected: false,
          },
          siteEarlyWarning: {
            active_alert_count: 6,
            active_yellow_alerts: 3,
            active_red_alerts: 3,
            latest_measurement_date: '2026-04-22',
            active_alerts: [],
          },
        } as any}
      />,
    );

    expect(screen.getByText('System')).toBeInTheDocument();
    expect(screen.getByText('läuft')).toBeInTheDocument();
    expect(screen.getByText('System').closest('.evidence-status-cell')).toHaveAttribute(
      'title',
      expect.stringContaining('wartet auf GELO-Daten'),
    );
    expect(screen.queryByText('Systembetrieb')).not.toBeInTheDocument();
    expect(screen.queryByText('diagnostic_only')).not.toBeInTheDocument();
    expect(screen.getByText('Wissenschaft')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
    expect(screen.getByText('Daten')).toBeInTheDocument();
    expect(screen.getByText('2 von 3 Quellen')).toBeInTheDocument();
    expect(screen.getByText('Budget-Gate')).toBeInTheDocument();
    expect(screen.getByText('geschlossen — Kalibrierungsfenster')).toBeInTheDocument();
    expect(screen.queryByText('can_change_budget=false')).not.toBeInTheDocument();

    expect(screen.getByText('Daten').closest('.evidence-status-cell')).toHaveAttribute(
      'title',
      expect.stringContaining('AMELAG: 2026-04-22'),
    );
    expect(screen.getByText('Daten').closest('.evidence-status-cell')).toHaveAttribute(
      'title',
      expect.stringContaining('SurvStat: 2026-04-20'),
    );
  });
});
