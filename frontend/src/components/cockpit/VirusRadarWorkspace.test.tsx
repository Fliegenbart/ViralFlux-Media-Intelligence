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

jest.mock('./MultiVirusForecastChart', () => ({
  __esModule: true,
  MultiVirusForecastChart: ({ loading, selectedVirus }: { loading?: boolean; selectedVirus?: string }) => (
    <div>{loading ? 'Hero virus forecast loading' : `Hero virus forecast chart ${selectedVirus}`}</div>
  ),
}));

jest.mock('./cockpitUtils', () => ({
  formatCurrency: (value: number | null | undefined) => (value == null ? '-' : `${value} EUR`),
  formatDateTime: () => '04.04.2026 · 08:00',
  formatDateShort: (value?: string | null) => {
    if (!value) return '-';
    const iso = String(value).slice(0, 10);
    const [year, month, day] = iso.split('-');
    return `${day}.${month}.${year}`;
  },
  formatPercent: (value: number) => `${Math.round(value)}%`,
  formatSignalScore: (value: number | null | undefined, digits = 0) => {
    if (value == null || Number.isNaN(value)) return '-';
    const normalized = value <= 1 ? value * 100 : value;
    return `${normalized.toFixed(digits)}/100`;
  },
  primarySignalScore: (item: { signal_score?: number | null; ranking_signal_score?: number | null; peix_score?: number | null; impact_probability?: number | null } | null | undefined) => {
    if (!item) return 0;
    const raw = item.signal_score ?? item.ranking_signal_score ?? item.peix_score ?? item.impact_probability ?? 0;
    return raw <= 1 ? raw * 100 : raw;
  },
  statusTone: () => ({
    background: 'rgba(31, 122, 102, 0.12)',
    color: '#1f7a66',
    border: '1px solid rgba(31, 122, 102, 0.18)',
  }),
}));

const noop = () => {};

describe('VirusRadarWorkspace', () => {
  it('renders one selected virus history plus forecast in the hero', () => {
    render(
      <VirusRadarWorkspace
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        heroForecastLoading={false}
        heroForecast={{
          availableViruses: ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A'],
          chartData: [
            {
              date: '2026-03-18',
              dateLabel: '18.03',
              actualSeries: {
                'Influenza A': 84,
                'Influenza B': 104,
                'SARS-CoV-2': 91,
                'RSV A': 70,
              },
              forecastSeries: {
                'Influenza A': null,
                'Influenza B': null,
                'SARS-CoV-2': null,
                'RSV A': null,
              },
            },
            {
              date: '2026-03-30',
              dateLabel: '30.03',
              actualSeries: {
                'Influenza A': 100,
                'Influenza B': 100,
                'SARS-CoV-2': 100,
                'RSV A': 100,
              },
              forecastSeries: {
                'Influenza A': 100,
                'Influenza B': 100,
                'SARS-CoV-2': 100,
                'RSV A': 100,
              },
            },
            {
              date: '2026-04-01',
              dateLabel: '01.04',
              actualSeries: {
                'Influenza A': null,
                'Influenza B': null,
                'SARS-CoV-2': null,
                'RSV A': null,
              },
              forecastSeries: {
                'Influenza A': 108,
                'Influenza B': 94,
                'SARS-CoV-2': 121,
                'RSV A': 145,
              },
            },
          ],
          summaries: [
            { virus: 'RSV A', currentIndex: 100, projectedIndex: 145, deltaPct: 45, direction: 'steigend' },
            { virus: 'SARS-CoV-2', currentIndex: 100, projectedIndex: 121, deltaPct: 21, direction: 'steigend' },
            { virus: 'Influenza A', currentIndex: 100, projectedIndex: 108, deltaPct: 8, direction: 'steigend' },
            { virus: 'Influenza B', currentIndex: 100, projectedIndex: 94, deltaPct: -6, direction: 'fallend' },
          ],
          headlinePrimary: 'Die letzten Wochen und die nächsten 7 Tage.',
          headlineSecondary: 'RSV A und SARS-CoV-2 ziehen aktuell am stärksten an.',
          summary: 'RSV A liegt in der 7-Tage-Prognose bei +45 %. Dahinter folgt SARS-CoV-2 mit +21 %. Alle Linien sind auf Heute = 100 normiert, damit die Dynamik direkt vergleichbar bleibt.',
        }}
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
                  event_probability: 0.81,
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
                bundesland: 'MV',
                bundesland_name: 'Mecklenburg-Vorpommern',
                as_of_date: '2026-04-03',
                target_date: '2026-04-03',
                horizon_days: 7,
                current_known_incidence: 24,
                expected_target_incidence: 24,
              },
              {
                bundesland: 'MV',
                bundesland_name: 'Mecklenburg-Vorpommern',
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
                MV: {
                  name: 'Mecklenburg-Vorpommern',
                  trend: 'steigend',
                  change_pct: 199,
                  impact_probability: 0.88,
                },
              },
              top_regions: [
                {
                  code: 'MV',
                  name: 'Mecklenburg-Vorpommern',
                  trend: 'steigend',
                  impact_probability: 0.88,
                  recommendation_ref: { card_id: 'rec-2' },
                },
              ],
              activation_suggestions: [
                {
                  region: 'MV',
                  region_name: 'Mecklenburg-Vorpommern',
                  priority: 'Aktivieren',
                  impact_probability: 0.88,
                  reason: 'Mecklenburg-Vorpommern zeigt aktuell die höchste Aktivierungsreife.',
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

    expect(screen.getByText('VIRALFLUX / VIRUS-RADAR')).toBeInTheDocument();
    expect(screen.getByText('Empfohlener nächster Schritt')).toBeInTheDocument();
    expect(screen.getByText('Berlin zeigt die stärkste Dynamik für GELO in dieser Woche.')).toBeInTheDocument();
    expect(screen.getByText('Virus-Verlauf · Influenza A')).toBeInTheDocument();
    expect(screen.getByText('Influenza A · letzte Wochen und nächste 7 Tage.')).toBeInTheDocument();
    expect(screen.getByText('Durchgezogen siehst du den gemessenen Verlauf, gestrichelt die Prognose.')).toBeInTheDocument();
    expect(screen.getByText('Hero virus forecast chart Influenza A')).toBeInTheDocument();
    expect(screen.getByText('Aktualisiert 04.04.2026 · 08:00')).toBeInTheDocument();
    expect(screen.getAllByText('Mecklenburg-Vorpommern').length).toBeGreaterThan(0);
    expect(screen.getByText('Letzte Wochen')).toBeInTheDocument();
    expect(screen.getByText('Nächste 7 Tage')).toBeInTheDocument();
    expect(screen.getByText('Letzter Stand = 100')).toBeInTheDocument();
    expect(screen.queryByText('Heute = 100')).not.toBeInTheDocument();
    expect(screen.getByText('Datenstand 30.03.2026')).toBeInTheDocument();
    expect(screen.getByText('Prognose bis 01.04.2026')).toBeInTheDocument();
    expect(screen.getByText('Links siehst du den gemessenen Verlauf bis zum letzten verfügbaren Stand, rechts die nächsten 7 Tage Prognose. Alle Werte sind auf Letzter Stand = 100 normiert, damit die Richtung sauber vergleichbar bleibt.')).toBeInTheDocument();
    expect(screen.queryByText('Eine zentrale Entscheidungsseite für Media. Was jetzt wichtig ist, wo gehandelt werden sollte und welche Risiken oder Blocker noch sichtbar bleiben.')).not.toBeInTheDocument();
    expect(screen.queryByText('Entscheidung diese Woche')).not.toBeInTheDocument();
    expect(screen.getByText('Radar-Tape')).toBeInTheDocument();
    expect(screen.getByText('Signal baut sich deutlich auf.')).toBeInTheDocument();
    expect(screen.getByText('+199.0%')).toBeInTheDocument();
    expect(screen.getByText('Zur Vorwoche')).toBeInTheDocument();
    expect(screen.getByText('Wichtigste Regionen diese Woche')).toBeInTheDocument();
    expect(screen.getByText('Fokusregion')).toBeInTheDocument();
    expect(screen.getAllByText('Aktivieren').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/88\/100 Signalwert/i).length).toBeGreaterThan(0);

    const decisionBlock = screen.getByText('Empfohlener nächster Schritt');
    const chartLegend = screen.getByText('Letzte Wochen');
    expect(
      decisionBlock.compareDocumentPosition(chartLegend) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('prefers ranking signal scores from the regions payload over the legacy alias in the focus ladder', () => {
    render(
      <VirusRadarWorkspace
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        heroForecastLoading={false}
        heroForecast={{
          availableViruses: ['Influenza A'],
          chartData: [],
          summaries: [{ virus: 'Influenza A', currentIndex: 100, projectedIndex: 108, deltaPct: 8, direction: 'steigend' }],
          headlinePrimary: 'Kurzfristiger Blick',
          headlineSecondary: 'Eine Region steht vorne.',
          summary: 'Die Fokusregion wird aus dem Regionsmodell gezogen.',
        }}
        nowData={{
          view: {
            generatedAt: '2026-04-04T08:00:00Z',
            heroRecommendation: {
              direction: 'Aktivieren',
              region: 'Hamburg',
              whyNow: 'Hamburg ist die Fokusregion.',
            },
            focusRegion: {
              code: 'HH',
              name: 'Hamburg',
              recommendationId: 'rec-1',
            },
            reasons: ['Hamburg steht im Ranking vorn.'],
            risks: [],
            summary: 'Hamburg ist diese Woche im Fokus.',
          },
          forecast: { predictions: [] },
          workspaceStatus: {
            data_freshness: 'Aktuell',
            summary: 'Die wichtigsten Daten sind aktuell genug für die Wochenentscheidung.',
            blocker_count: 0,
            blockers: [],
            open_blockers: 'Keine',
          },
          focusRegionBacktest: { timeline: [] },
        } as any}
        regionsData={{
          regionsView: {
            map: {
              regions: {
                HH: {
                  name: 'Hamburg',
                  trend: 'steigend',
                  change_pct: 14.2,
                  ranking_signal_score: 0.79,
                },
              },
              top_regions: [
                {
                  code: 'HH',
                  name: 'Hamburg',
                  trend: 'steigend',
                  ranking_signal_score: 0.79,
                  impact_probability: 0.64,
                  recommendation_ref: { card_id: 'rec-1' },
                },
              ],
              activation_suggestions: [
                {
                  region: 'HH',
                  region_name: 'Hamburg',
                  priority: 'Aktivieren',
                  signal_score: 0.79,
                  reason: 'Hamburg steht vorne.',
                  budget_shift_pct: 20,
                  channel_mix: { search: 0.5 },
                },
              ],
            },
          },
        } as any}
        campaignsData={{
          campaignsView: {
            summary: {
              publishable_cards: 1,
              active_cards: 1,
            },
            cards: [],
          },
        } as any}
        evidenceData={{
          evidence: {
            truth_gate: {
              state: 'Aktiv',
              passed: true,
              message: 'Evidenz ist ausreichend sichtbar.',
            },
            business_validation: {},
            signal_stack: {
              summary: {
                top_drivers: [],
              },
            },
            known_limits: [],
          },
        } as any}
        onOpenRecommendation={noop}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    expect(screen.getAllByText(/79\/100 Signalwert/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/64\/100 Signalwert/i)).not.toBeInTheDocument();
  });

  it('shows an honest loading state while the shared hero outlook is still loading', () => {
    render(
      <VirusRadarWorkspace
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        heroForecastLoading
        heroForecast={{
          availableViruses: [],
          chartData: [],
          summaries: [],
          headlinePrimary: 'Das Lagebild der nächsten 7 Tage.',
          headlineSecondary: 'Noch keine belastbare 7-Tage-Prognose.',
          summary: 'Sobald frische Prognosekurven vorliegen, wird hier das gemeinsame Lagebild der nächsten sieben Tage sichtbar.',
        }}
        nowData={{
          view: {
            generatedAt: '2026-04-04T08:00:00Z',
            heroRecommendation: null,
            focusRegion: null,
            reasons: [],
            risks: [],
            summary: '',
          },
          forecast: { predictions: [] },
          workspaceStatus: {
            data_freshness: 'Lädt',
            summary: 'Die wichtigsten Daten werden noch geladen.',
            blocker_count: 0,
            blockers: [],
            open_blockers: '0 offen',
          },
          focusRegionBacktest: {
            timeline: [],
          },
        } as any}
        regionsData={{
          regionsView: {
            map: {
              regions: {},
              top_regions: [],
              activation_suggestions: [],
            },
          },
        } as any}
        campaignsData={{
          campaignsView: {
            summary: {
              publishable_cards: 0,
              active_cards: 0,
            },
            cards: [],
          },
        } as any}
        evidenceData={{
          evidence: {
            truth_gate: {
              state: 'Lädt',
              passed: false,
              message: 'Evidenz wird geladen.',
            },
          },
        } as any}
        onOpenRecommendation={noop}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    expect(screen.getByText('Virus-Verlauf wird geladen')).toBeInTheDocument();
    expect(screen.getByText('Der Verlauf wird geladen.')).toBeInTheDocument();
    expect(screen.getByText('Die Prognose wird gerade aufgebaut.')).toBeInTheDocument();
    expect(screen.getByText('Hero virus forecast loading')).toBeInTheDocument();
    expect(screen.queryByText('Virus-Verlauf · 0 Viren')).not.toBeInTheDocument();
  });
});
