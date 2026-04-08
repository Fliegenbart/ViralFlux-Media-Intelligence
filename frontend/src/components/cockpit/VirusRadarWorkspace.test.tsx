import '@testing-library/jest-dom';
import React from 'react';
import { render, screen } from '@testing-library/react';

import VirusRadarWorkspace from './VirusRadarWorkspace';

jest.mock('./GermanyMap', () => ({
  __esModule: true,
  default: () => <div>Germany map</div>,
}));

jest.mock('./ForecastChart', () => ({
  __esModule: true,
  ForecastChart: () => <div>Forecast chart</div>,
}));

jest.mock('./cockpitUtils', () => ({
  formatCurrency: (value: number | null | undefined) => (value == null ? '-' : `${value} EUR`),
  formatDateTime: () => '04.04.2026 · 08:00',
  formatPercent: (value: number) => `${Math.round(value)}%`,
  statusTone: () => ({
    background: 'rgba(31, 122, 102, 0.12)',
    color: '#1f7a66',
    border: '1px solid rgba(31, 122, 102, 0.18)',
  }),
}));

const noop = () => {};

describe('VirusRadarWorkspace', () => {
  it('renders a hero-style weekly signal with peak framing', () => {
    render(
      <VirusRadarWorkspace
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        nowData={{
          view: {
            generatedAt: '2026-04-04T08:00:00Z',
            heroRecommendation: {
              direction: 'Aktivieren',
              region: 'Berlin',
              whyNow: 'Berlin zeigt die stärkste Dynamik für GELO in dieser Woche.',
            },
            focusRegion: {
              code: 'BE',
              name: 'Berlin',
              recommendationId: 'rec-1',
            },
            reasons: ['Berlin führt Forecast, Signal und Reife zusammen.'],
            risks: ['Kundendaten bleiben noch im Aufbau.'],
            summary: 'Berlin ist diese Woche der klarste Fokusfall.',
          },
          forecast: {
            predictions: [
              {
                bundesland: 'BE',
                bundesland_name: 'Berlin',
                event_probability_calibrated: 0.81,
                trend: 'steigend',
                change_pct: 12.4,
                decision_rank: 1,
              },
            ],
          },
          workspaceStatus: {
            data_freshness: 'Aktuell',
            summary: 'Die wichtigsten Daten sind aktuell genug für die Wochenentscheidung.',
            blocker_count: 1,
            blockers: ['Eine Freigabe ist noch offen.'],
            open_blockers: '1 offen',
          },
          focusRegionBacktest: {
            timeline: [
              {
                bundesland: 'BE',
                bundesland_name: 'Berlin',
                as_of_date: '2026-04-03',
                target_date: '2026-04-03',
                horizon_days: 7,
                current_known_incidence: 24,
                expected_target_incidence: 24,
              },
              {
                bundesland: 'BE',
                bundesland_name: 'Berlin',
                as_of_date: '2026-04-04',
                target_date: '2026-04-08',
                horizon_days: 7,
                current_known_incidence: 31,
                expected_target_incidence: 58,
                prediction_interval_lower: 49,
                prediction_interval_upper: 64,
              },
            ],
          },
        } as any}
        regionsData={{
          regionsView: {
            map: {
              regions: {
                BE: {
                  name: 'Berlin',
                  trend: 'steigend',
                  change_pct: 12.4,
                  impact_probability: 0.81,
                },
              },
              top_regions: [
                {
                  code: 'BE',
                  name: 'Berlin',
                  trend: 'steigend',
                  impact_probability: 0.81,
                  recommendation_ref: { card_id: 'rec-1' },
                },
              ],
              activation_suggestions: [
                {
                  region: 'BE',
                  region_name: 'Berlin',
                  priority: 'Aktivieren',
                  impact_probability: 0.81,
                  reason: 'Signal, Reife und Relevanz kommen zusammen.',
                },
              ],
            },
          },
        } as any}
        campaignsData={{
          campaignsView: {
            summary: {
              publishable_cards: 1,
              active_cards: 2,
            },
            cards: [
              {
                id: 'rec-1',
                display_title: 'Berlin jetzt priorisieren',
                status: 'READY',
                region: 'Berlin',
                reason: 'Respiratory Core Demand ist bereit für Review.',
                campaign_preview: { budget: { weekly_budget_eur: 55000 } },
              },
            ],
          },
        } as any}
        evidenceData={{
          evidence: {
            truth_gate: {
              state: 'Aktiv',
              passed: true,
              message: 'Evidenz ist für diese Woche ausreichend sichtbar.',
            },
            business_validation: {
              guidance: 'GELO kann die Wochenentscheidung mit Vorsicht treffen.',
            },
            signal_stack: {
              summary: {
                top_drivers: [{ label: 'Apothekennachfrage', strength_pct: 62 }],
              },
            },
            known_limits: ['Business-Lift bleibt beobachtend.'],
          },
        } as any}
        onOpenRecommendation={noop}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    expect(screen.getByText('PEIX / GELO / VIRUS-RADAR')).toBeInTheDocument();
    expect(screen.getByText('Live-Signal · Influenza A')).toBeInTheDocument();
    expect(screen.getByText('Berlin läuft heiß.')).toBeInTheDocument();
    expect(screen.getByText('Peak in 4 Tagen.')).toBeInTheDocument();
    expect(screen.getByText('Ist · 28 Tage')).toBeInTheDocument();
    expect(screen.getByText('Forecast · 7 Tage')).toBeInTheDocument();
    expect(screen.queryByText('Entscheidung diese Woche')).not.toBeInTheDocument();
    expect(screen.getByText('Radar-Tape')).toBeInTheDocument();
  });
});
