import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

jest.mock('./GermanyMap', () => ({
  __esModule: true,
  default: () => <div>GermanyMap Mock</div>,
}));

import RegionWorkbench from './RegionWorkbench';
import { MediaRegionsResponse, WorkspaceStatusSummary } from '../../types/media';

function buildRegionsView(): MediaRegionsResponse {
  return {
    virus_typ: 'Influenza A',
    target_source: 'regional',
    generated_at: '2026-03-18T08:00:00Z',
    map: {
      has_data: true,
      date: '2026-03-18',
      max_viruslast: 100,
      regions: {
        BE: {
          name: 'Berlin',
          avg_viruslast: 84,
          intensity: 0.8,
          trend: 'steigend',
          change_pct: 18,
          n_standorte: 2,
          signal_score: 0.82,
          actionability_score: 0.76,
          forecast_direction: 'aufwaerts',
          priority_explanation: 'Berlin ist aktuell die klarste Region fuer den naechsten Schritt.',
          decision_mode_label: 'Regionalsignal',
          signal_drivers: [{ label: 'Abwasser', strength_pct: 74 }],
          source_trace: ['AMELAG', 'SurvStat'],
          recommendation_ref: {
            card_id: 'rec-1',
            detail_url: '/kampagnen/rec-1',
          },
          tooltip: {
            region_name: 'Berlin',
            recommendation_text: 'Berlin zeigt das staerkste Signal.',
            epi_outlook: 'hoch',
            recommended_product: 'GeloMyrtol forte',
            peix_score: 0.8,
            peix_band: 'hoch',
            impact_probability: 0.81,
            urgency_label: 'hoch',
            trend: 'steigend',
            change_pct: 18,
            virus_typ: 'Influenza A',
          },
          priority_rank: 1,
        },
        BY: {
          name: 'Bayern',
          avg_viruslast: 64,
          intensity: 0.62,
          trend: 'steigend',
          change_pct: 11,
          n_standorte: 2,
          signal_score: 0.61,
          actionability_score: 0.52,
          forecast_direction: 'aufwaerts',
          priority_explanation: 'Bayern bleibt als naechster pruefbarer Bundeslandpfad sichtbar.',
          decision_mode_label: 'Vorbereiten',
          signal_drivers: [{ label: 'Suchvolumen', strength_pct: 56 }],
          source_trace: ['AMELAG', 'SurvStat'],
          priority_rank: 2,
        },
        NW: {
          name: 'Nordrhein-Westfalen',
          avg_viruslast: 52,
          intensity: 0.46,
          trend: 'seitwaerts',
          change_pct: 4,
          n_standorte: 2,
          signal_score: 0.44,
          actionability_score: 0.38,
          forecast_direction: 'seitwaerts',
          priority_explanation: 'Nordrhein-Westfalen sollte sichtbar bleiben, aber noch nicht vor Berlin gezogen werden.',
          decision_mode_label: 'Beobachten',
          signal_drivers: [{ label: 'Apothekenabverkauf', strength_pct: 44 }],
          source_trace: ['AMELAG', 'SurvStat'],
          priority_rank: 3,
        },
        SN: {
          name: 'Sachsen',
          avg_viruslast: 44,
          intensity: 0.4,
          trend: 'seitwaerts',
          change_pct: 3,
          n_standorte: 1,
          signal_score: 0.18,
          actionability_score: 0.12,
          forecast_direction: 'seitwaerts',
          priority_explanation: 'Fuer Sachsen reicht die Evidenz aktuell noch nicht fuer eine belastbare Einordnung.',
          decision_mode_label: 'Beobachten',
          signal_drivers: [],
          source_trace: [],
          tooltip: {
            region_name: 'Sachsen',
            recommendation_text: 'Sachsen bleibt aktuell beobachtend.',
            epi_outlook: 'mittel',
            recommended_product: 'GeloBronchial',
            peix_score: 0.18,
            peix_band: 'niedrig',
            impact_probability: 0.2,
            urgency_label: 'niedrig',
            trend: 'seitwaerts',
            change_pct: 3,
            virus_typ: 'Influenza A',
          },
          priority_rank: 4,
        },
      },
      top_regions: [
        { code: 'BE', name: 'Berlin', trend: 'steigend', signal_score: 0.82, actionability_score: 0.76, priority_rank: 1 },
        { code: 'BY', name: 'Bayern', trend: 'steigend', signal_score: 0.61, actionability_score: 0.52, priority_rank: 2 },
        { code: 'NW', name: 'Nordrhein-Westfalen', trend: 'seitwaerts', signal_score: 0.44, actionability_score: 0.38, priority_rank: 3 },
        { code: 'SN', name: 'Sachsen', trend: 'seitwaerts', signal_score: 0.18, actionability_score: 0.12, priority_rank: 4 },
      ],
      activation_suggestions: [
        {
          region: 'BE',
          region_name: 'Berlin',
          priority: 'hoch',
          signal_score: 0.82,
          priority_score: 0.76,
          impact_probability: 0.81,
          budget_shift_pct: 24,
          channel_mix: { search: 0.5 },
          reason: 'Berlin sollte zuerst geprueft werden.',
        },
        {
          region: 'BY',
          region_name: 'Bayern',
          priority: 'mittel',
          signal_score: 0.61,
          priority_score: 0.52,
          impact_probability: 0.63,
          budget_shift_pct: 8,
          channel_mix: { search: 0.35 },
          reason: 'Bayern kann als naechster regionaler Vorschlag vorbereitet werden.',
        },
        {
          region: 'NW',
          region_name: 'Nordrhein-Westfalen',
          priority: 'niedrig',
          signal_score: 0.44,
          priority_score: 0.38,
          impact_probability: 0.46,
          budget_shift_pct: 0,
          channel_mix: { search: 0.22 },
          reason: 'Nordrhein-Westfalen sollte vorerst beobachtet werden.',
        },
        {
          region: 'SN',
          region_name: 'Sachsen',
          priority: 'niedrig',
          signal_score: 0.18,
          priority_score: 0.12,
          impact_probability: 0.2,
          budget_shift_pct: 4,
          channel_mix: { search: 0.2 },
          reason: 'Fuer Sachsen gibt es aktuell zu wenig Evidenz.',
        },
      ],
    },
    top_regions: [
      { code: 'BE', name: 'Berlin', trend: 'steigend', signal_score: 0.82 },
      { code: 'BY', name: 'Bayern', trend: 'steigend', signal_score: 0.61 },
      { code: 'NW', name: 'Nordrhein-Westfalen', trend: 'seitwaerts', signal_score: 0.44 },
      { code: 'SN', name: 'Sachsen', trend: 'seitwaerts', signal_score: 0.18 },
    ],
    decision_state: 'GO',
  };
}

function buildWorkspaceStatus(): WorkspaceStatusSummary {
  return {
    forecast_status: 'Freigabe bereit',
    data_freshness: 'Aktuell',
    customer_data_status: 'im Aufbau',
    open_blockers: 'Keine',
    last_import_at: '2026-03-17T08:00:00Z',
    blocker_count: 0,
    blockers: [],
    summary: 'Die regionale Empfehlung ist klar genug fuer den naechsten pruelfaehigen Schritt.',
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
        value: 'Keine',
        detail: 'Aktuell gibt es keine offenen Blocker.',
        tone: 'success',
      },
    ],
  };
}

const noop = () => {};

describe('RegionWorkbench', () => {
  it('shows an action-first regional workspace with trust and secondary regions above the map', () => {
    const onOpenRecommendation = jest.fn();

    render(
      <RegionWorkbench
        virus="Influenza A"
        onVirusChange={noop}
        regionsView={buildRegionsView()}
        workspaceStatus={buildWorkspaceStatus()}
        loading={false}
        selectedRegion="BE"
        onSelectRegion={noop}
        onOpenRecommendation={onOpenRecommendation}
        onGenerateRegionCampaign={noop}
        regionActionLoading={false}
      />,
    );

    expect(screen.getByText('Wo GELO diese Woche regional Fokus setzen sollte')).toBeInTheDocument();
    expect(screen.getByText('Empfohlene Regionen-Aktion diese Woche')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Fokus erhöhen in Berlin' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Regionalen Vorschlag öffnen' })).toBeInTheDocument();
    expect(screen.getByText('Was die regionale Empfehlung trägt')).toBeInTheDocument();
    expect(screen.getByText('Belastbarkeit')).toBeInTheDocument();
    expect(screen.getByText('Datenlage')).toBeInTheDocument();
    expect(screen.getByText('Einsatzreife')).toBeInTheDocument();
    expect(screen.getByText('Weitere Bundesländer mit nächstem Schritt')).toBeInTheDocument();
    expect(screen.getAllByText('Bayern').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Nordrhein-Westfalen').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Bundesländer im Vergleich').length).toBeGreaterThan(0);
    expect(screen.getByText('Orientierungskarte auf Bundesland-Level')).toBeInTheDocument();
    expect(screen.getByText('GermanyMap Mock')).toBeInTheDocument();
    expect(screen.getAllByText(/City-Forecast/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: 'Regionalen Vorschlag öffnen' }));

    expect(onOpenRecommendation).toHaveBeenCalledWith('rec-1');
  });

  it('disables a new regional action when the selected Bundesland has too little evidence', () => {
    render(
      <RegionWorkbench
        virus="Influenza A"
        onVirusChange={noop}
        regionsView={buildRegionsView()}
        workspaceStatus={buildWorkspaceStatus()}
        loading={false}
        selectedRegion="SN"
        onSelectRegion={noop}
        onOpenRecommendation={noop}
        onGenerateRegionCampaign={noop}
        regionActionLoading={false}
      />,
    );

    expect(screen.getByRole('heading', { name: 'In Sachsen vorerst zurückhaltend bleiben' })).toBeInTheDocument();
    expect(screen.getAllByText('Zu wenig Evidenz').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Regionale Maßnahme prüfen' })).toBeDisabled();
    expect(
      screen.getAllByText('Für dieses Bundesland reicht die aktuelle Evidenz noch nicht für einen neuen regionalen Vorschlag.').length,
    ).toBeGreaterThan(0);
  });

  it('can filter the comparison list to low-evidence regions', () => {
    render(
      <RegionWorkbench
        virus="Influenza A"
        onVirusChange={noop}
        regionsView={buildRegionsView()}
        workspaceStatus={buildWorkspaceStatus()}
        loading={false}
        selectedRegion="BE"
        onSelectRegion={noop}
        onOpenRecommendation={noop}
        onGenerateRegionCampaign={noop}
        regionActionLoading={false}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Zu wenig Evidenz' }));

    expect(screen.getByRole('heading', { name: 'Bundesländer mit zu wenig Evidenz' })).toBeInTheDocument();
    expect(screen.getAllByText('Sachsen').length).toBeGreaterThan(0);
  });

  it('shows a regional workspace skeleton while loading', () => {
    render(
      <RegionWorkbench
        virus="Influenza A"
        onVirusChange={noop}
        regionsView={null}
        workspaceStatus={null}
        loading
        selectedRegion={null}
        onSelectRegion={noop}
        onOpenRecommendation={noop}
        onGenerateRegionCampaign={noop}
        regionActionLoading={false}
      />,
    );

    expect(screen.getByLabelText('Regionale Arbeitsfläche wird geladen')).toBeInTheDocument();
  });

  it('shows an honest empty state when no regional prioritization exists', () => {
    const emptyView = buildRegionsView();
    emptyView.map.regions = {};
    emptyView.map.top_regions = [];
    emptyView.map.activation_suggestions = [];

    render(
      <RegionWorkbench
        virus="Influenza A"
        onVirusChange={noop}
        regionsView={emptyView}
        workspaceStatus={buildWorkspaceStatus()}
        loading={false}
        selectedRegion={null}
        onSelectRegion={noop}
        onOpenRecommendation={noop}
        onGenerateRegionCampaign={noop}
        regionActionLoading={false}
      />,
    );

    expect(screen.getByText('Noch keine belastbare regionale Priorisierung')).toBeInTheDocument();
    expect(screen.getByText('Für diese Auswahl liegen aktuell keine belastbaren regionalen Prioritäten vor.')).toBeInTheDocument();
  });
});
