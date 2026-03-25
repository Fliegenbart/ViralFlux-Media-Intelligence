import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import NowWorkspace from './NowWorkspace';
import { NowPageTrustCheck, NowPageViewModel } from '../../features/media/useMediaData';
import {
  RegionalBacktestResponse,
  RegionalForecastResponse,
  WaveRadarResponse,
  WorkspaceStatusSummary,
} from '../../types/media';

jest.mock('recharts', () => {
  const ReactLib = require('react');

  const passthrough = ({ children }: { children?: React.ReactNode }) => ReactLib.createElement(ReactLib.Fragment, null, children);
  const empty = () => null;

  return {
    ResponsiveContainer: passthrough,
    ComposedChart: passthrough,
    CartesianGrid: empty,
    Legend: empty,
    Line: empty,
    ReferenceArea: empty,
    ReferenceLine: empty,
    Tooltip: empty,
    XAxis: empty,
    YAxis: empty,
    Area: empty,
  };
});

jest.mock('./HistoricalWaveMap', () => ({
  __esModule: true,
  default: ({ onSelectBundesland }: { onSelectBundesland: (bundesland: string) => void }) => (
    <div>
      <button type="button" data-testid="historical-wave-map-BE" onClick={() => onSelectBundesland('Berlin')}>
        HistoricalWaveMap Berlin
      </button>
      <button type="button" data-testid="historical-wave-map-BB" onClick={() => onSelectBundesland('Brandenburg')}>
        HistoricalWaveMap Brandenburg
      </button>
    </div>
  ),
}));

const noop = () => {};

function buildTrustChecks(): NowPageTrustCheck[] {
  return [
    {
      key: 'forecast',
      question: 'Kann ich der Vorhersage trauen?',
      value: 'Freigabe bereit',
      detail: 'Monitoring Stabil · Forecast aktuell',
      tone: 'success',
    },
    {
      key: 'data',
      question: 'Sind die Daten frisch genug?',
      value: 'Aktuell',
      detail: '6/7 Quellen aktuell',
      tone: 'success',
    },
    {
      key: 'business',
      question: 'Ist eine Business-Freigabe schon drin?',
      value: 'Im Aufbau',
      detail: 'Vergleichsgruppe bereit · beobachtend',
      tone: 'warning',
    },
  ];
}

function buildView(): NowPageViewModel {
  return {
    hasData: true,
    generatedAt: '2026-03-18T08:00:00Z',
    title: 'Aktivieren: Berlin',
    summary: 'Berlin ist diese Woche der klarste nächste Schritt.',
    note: 'Die nächste sinnvolle Aktion steht oben. Qualität und Risiken folgen darunter.',
    proof: {
      headline: 'Unsere Prognose zeigt im 7-Tage-Fenster die größte Dynamik aktuell in Berlin.',
      supportingText: 'Damit wird früh sichtbar, wo du als Nächstes priorisieren und Budget gezielter einsetzen solltest.',
      proofPoints: ['7 Tage Vorhersage', 'Berlin zeigt aktuell die größte Dynamik.'],
      cautionText: 'Die Lage bleibt nachvollziehbar, aber keine Vorhersage ist eine Garantie.',
      assertive: true,
    },
    primaryActionLabel: 'Nächste Kampagne öffnen',
    primaryRecommendationId: 'rec-1',
    primaryCampaignTitle: 'Respiratory Core Demand',
    primaryCampaignContext: 'Berlin · Zu prüfen',
    primaryCampaignCopy: 'Die Kampagne ist der direkteste prüfbare nächste Schritt.',
    focusRegion: {
      code: 'BE',
      name: 'Berlin',
      stage: 'Aktivieren',
      reason: 'Berlin bündelt aktuell die stärkste Dynamik aus Vorhersage und Kontext.',
      product: 'GeloMyrtol forte',
      probabilityLabel: '81.0%',
      budgetLabel: '55.200 €',
      recommendationId: 'rec-1',
    },
    metrics: [
      { label: 'Freigabe', value: 'Freigeben', tone: 'success' },
      { label: 'Event-Wahrscheinlichkeit', value: '81.0%', tone: 'success' },
      { label: 'Empfohlenes Budget', value: '55.200 €', tone: 'neutral' },
      { label: 'Vertrauen', value: 'im Aufbau', tone: 'warning' },
    ],
    trustChecks: buildTrustChecks(),
    reasons: [
      'Die Entwicklung liegt klar über der Aktivierungsschwelle.',
      'Die Fokusregion zeigt die stärkste Dynamik.',
    ],
    risks: [
      'Die Revision der Quelldaten bleibt sichtbar.',
    ],
    quality: [
      { label: 'Quellen aktuell', value: '6/7' },
      { label: 'Kundendaten', value: 'im Aufbau' },
      { label: 'Freigabestatus', value: 'Holdout bereit' },
      { label: 'Belegstufe', value: 'beobachtend' },
    ],
    relatedRegions: [
      {
        code: 'BY',
        name: 'Bayern',
        stage: 'Vorbereiten',
        probabilityLabel: '54.0%',
        reason: 'Bayern ist der nächste sinnvolle Prüfpfad.',
      },
    ],
    emptyState: null,
  };
}

function buildWorkspaceStatus(): WorkspaceStatusSummary {
  return {
    forecast_status: 'Freigabe bereit',
    data_freshness: 'Aktuell',
    customer_data_status: 'im Aufbau',
    open_blockers: '1 offen',
    last_import_at: '2026-03-17T08:00:00Z',
    blocker_count: 1,
    blockers: ['Die Revision der Quelldaten bleibt sichtbar.'],
    summary: 'Vor dem nächsten Schritt sollten wir zuerst die offenen Punkte prüfen.',
    items: [
      {
        key: 'forecast_status',
        question: 'Ist der Forecast stabil?',
        value: 'Freigabe bereit',
        detail: 'Monitoring Stabil · Forecast aktuell',
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
        detail: 'Die Revision der Quelldaten bleibt sichtbar.',
        tone: 'warning',
      },
    ],
  };
}

function buildForecast(): RegionalForecastResponse {
  return {
    virus_typ: 'Influenza A',
    horizon_days: 7,
    target_window_days: [7],
    decision_summary: {
      watch_regions: 10,
      prepare_regions: 4,
      activate_regions: 2,
      avg_priority_score: 61,
      top_region: 'BE',
      top_region_decision: 'Prepare',
    },
    total_regions: 16,
    predictions: [
      {
        bundesland: 'BE',
        bundesland_name: 'Berlin',
        virus_typ: 'Influenza A',
        as_of_date: '2026-03-18 00:00:00',
        target_date: '2026-03-25',
        target_week_start: '2026-03-23',
        target_window_days: [7],
        horizon_days: 7,
        event_probability_calibrated: 0.81,
        expected_target_incidence: 165,
        current_known_incidence: 110,
        change_pct: 18,
        trend: 'up',
        decision_label: 'Prepare',
        decision_rank: 1,
        prediction_interval: {
          lower: 150,
          upper: 185,
        },
        last_data_date: '2026-03-17 00:00:00',
      },
    ],
    top_5: [],
    top_decisions: [],
    generated_at: '2026-03-18T08:00:00Z',
    as_of_date: '2026-03-18',
  };
}

function buildFocusRegionBacktest(): RegionalBacktestResponse {
  return {
    bundesland: 'BE',
    bundesland_name: 'Berlin',
    timeline: [
      {
        bundesland: 'BE',
        bundesland_name: 'Berlin',
        as_of_date: '2026-02-24T00:00:00',
        target_date: '2026-03-03T00:00:00',
        horizon_days: 7,
        current_known_incidence: 92,
        expected_target_incidence: 96,
        prediction_interval_lower: 88,
        prediction_interval_upper: 102,
      },
      {
        bundesland: 'BE',
        bundesland_name: 'Berlin',
        as_of_date: '2026-03-03T00:00:00',
        target_date: '2026-03-10T00:00:00',
        horizon_days: 7,
        current_known_incidence: 101,
        expected_target_incidence: 108,
        prediction_interval_lower: 96,
        prediction_interval_upper: 116,
      },
      {
        bundesland: 'BE',
        bundesland_name: 'Berlin',
        as_of_date: '2026-03-10T00:00:00',
        target_date: '2026-03-17T00:00:00',
        horizon_days: 7,
        current_known_incidence: 110,
        expected_target_incidence: 121,
        prediction_interval_lower: 104,
        prediction_interval_upper: 132,
      },
    ],
  };
}

function buildWaveRadar(): WaveRadarResponse {
  return {
    disease: 'Influenza, saisonal',
    season: '2025/2026',
    summary: {
      first_onset: {
        bundesland: 'Berlin',
        date: '2025-11-10',
      },
      last_onset: {
        bundesland: 'Bayern',
        date: '2025-12-15',
      },
      spread_days: 35,
      regions_affected: 12,
      regions_total: 16,
    },
    regions: [
      {
        bundesland: 'Berlin',
        wave_start: '2025-11-10',
        wave_rank: 1,
      },
      {
        bundesland: 'Brandenburg',
        wave_start: '2025-11-17',
        wave_rank: 2,
      },
    ],
  };
}

describe('NowWorkspace', () => {
  it('shows one main decision and keeps secondary content in details', () => {
    render(
      <NowWorkspace
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        onHorizonChange={noop}
        view={buildView()}
        workspaceStatus={buildWorkspaceStatus()}
        loading={false}
        forecast={buildForecast()}
        focusRegionBacktest={buildFocusRegionBacktest()}
        focusRegionBacktestLoading={false}
        waveOutlook={null}
        waveOutlookLoading={false}
        waveRadar={buildWaveRadar()}
        waveRadarLoading={false}
        onOpenRecommendation={noop}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    expect(screen.getByText('Was passiert gerade?')).toBeInTheDocument();
    expect(screen.getByText('Fokusregion in 7 Tagen')).toBeInTheDocument();
    expect(screen.getByText(/In 7 Tagen erwarten wir für Berlin einen Viruslage-Wert von ca. 165,0/)).toBeInTheDocument();
    expect(screen.getByText(/Letzter bestätigter Ist-Wert vom 17.03.2026/)).toBeInTheDocument();
    expect(screen.getByText('Unsere Prognose zeigt im 7-Tage-Fenster die größte Dynamik aktuell in Berlin.')).toBeInTheDocument();
    expect(screen.getByText('Kann ich der Entscheidung trauen?')).toBeInTheDocument();
    expect(screen.getByText('Der schnelle Sicherheitscheck')).toBeInTheDocument();
    expect(screen.getByText('Ist eine Business-Freigabe schon drin?')).toBeInTheDocument();
    expect(screen.getByText('Weitere Details')).toBeInTheDocument();
  });

  it('opens the primary recommendation from the hero action', () => {
    const onOpenRecommendation = jest.fn();

    render(
      <NowWorkspace
        virus="Influenza A"
        onVirusChange={noop}
        horizonDays={7}
        onHorizonChange={noop}
        view={buildView()}
        workspaceStatus={buildWorkspaceStatus()}
        loading={false}
        forecast={buildForecast()}
        focusRegionBacktest={buildFocusRegionBacktest()}
        focusRegionBacktestLoading={false}
        waveOutlook={null}
        waveOutlookLoading={false}
        waveRadar={buildWaveRadar()}
        waveRadarLoading={false}
        onOpenRecommendation={onOpenRecommendation}
        onOpenRegions={noop}
        onOpenCampaigns={noop}
        onOpenEvidence={noop}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Nächste Kampagne öffnen' }));

    expect(onOpenRecommendation).toHaveBeenCalledWith('rec-1');
  });
});
