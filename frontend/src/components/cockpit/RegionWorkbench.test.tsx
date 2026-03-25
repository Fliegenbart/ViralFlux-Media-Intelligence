import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

jest.mock('./GermanyMap', () => ({
  __esModule: true,
  default: () => <div>GermanyMap Mock</div>,
}));

import RegionWorkbench from './RegionWorkbench';
import { MediaRegionsResponse } from '../../types/media';

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
          forecast_direction: 'aufwärts',
          priority_explanation: 'Berlin ist aktuell die klarste Region für den nächsten Schritt.',
          decision_mode_label: 'Regionalsignal',
          signal_drivers: [{ label: 'Abwasser', strength_pct: 74 }],
          source_trace: ['AMELAG', 'SurvStat'],
          recommendation_ref: {
            card_id: 'rec-1',
            detail_url: '/kampagnen/rec-1',
          },
          tooltip: {
            region_name: 'Berlin',
            recommendation_text: 'Berlin zeigt das stärkste Signal.',
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
        },
        SN: {
          name: 'Sachsen',
          avg_viruslast: 44,
          intensity: 0.4,
          trend: 'seitwärts',
          change_pct: 3,
          n_standorte: 1,
          signal_score: 0.18,
          actionability_score: 0.12,
          forecast_direction: 'seitwärts',
          priority_explanation: 'Für Sachsen reicht die Evidenz aktuell noch nicht für eine belastbare Einordnung.',
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
            trend: 'seitwärts',
            change_pct: 3,
            virus_typ: 'Influenza A',
          },
        },
      },
      top_regions: [
        {
          code: 'BE',
          name: 'Berlin',
          trend: 'steigend',
          signal_score: 0.82,
          actionability_score: 0.76,
          decision_mode_label: 'Regionalsignal',
          priority_rank: 1,
          recommendation_ref: {
            card_id: 'rec-1',
            detail_url: '/kampagnen/rec-1',
          },
          tooltip: {
            region_name: 'Berlin',
            recommendation_text: 'Berlin zeigt das stärkste Signal.',
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
        },
        {
          code: 'SN',
          name: 'Sachsen',
          trend: 'seitwärts',
          signal_score: 0.18,
          actionability_score: 0.12,
          decision_mode_label: 'Beobachten',
          priority_rank: 2,
          tooltip: {
            region_name: 'Sachsen',
            recommendation_text: 'Sachsen bleibt aktuell beobachtend.',
            epi_outlook: 'mittel',
            recommended_product: 'GeloBronchial',
            peix_score: 0.18,
            peix_band: 'niedrig',
            impact_probability: 0.2,
            urgency_label: 'niedrig',
            trend: 'seitwärts',
            change_pct: 3,
            virus_typ: 'Influenza A',
          },
        },
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
          reason: 'Berlin sollte zuerst geprüft werden.',
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
          reason: 'Für Sachsen gibt es aktuell zu wenig Evidenz.',
        },
      ],
    },
    top_regions: [
      {
        code: 'BE',
        name: 'Berlin',
        trend: 'steigend',
        signal_score: 0.82,
      },
      {
        code: 'SN',
        name: 'Sachsen',
        trend: 'seitwärts',
        signal_score: 0.18,
      },
    ],
    decision_state: 'GO',
  };
}

const noop = () => {};

describe('RegionWorkbench', () => {
  it('shows state-level guidance, a primary action and the comparison list', () => {
    const onOpenRecommendation = jest.fn();

    const { container } = render(
      <RegionWorkbench
        virus="Influenza A"
        onVirusChange={noop}
        regionsView={buildRegionsView()}
        workspaceStatus={null}
        loading={false}
        selectedRegion="BE"
        onSelectRegion={noop}
        onOpenRecommendation={onOpenRecommendation}
        onGenerateRegionCampaign={noop}
        regionActionLoading={false}
      />,
    );

    expect(screen.getByText('Bundesländer vergleichen')).toBeInTheDocument();
    expect(screen.getAllByText('Bundesland-Level').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Kein City-Forecast').length).toBeGreaterThan(0);
    expect(screen.getByText('Vergleichsliste')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Regionenvergleich auf Bundesland-Level' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zu wenig Evidenz' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Kampagnenvorschlag öffnen' })).toBeInTheDocument();
    expect(screen.getByText(/Warum: Berlin ist aktuell die klarste Region/)).toBeInTheDocument();
    expect(screen.queryByText('Empfehlung neu berechnen')).not.toBeInTheDocument();
    expect(container.querySelector('.regions-command-grid')).toBeTruthy();
    expect(container.querySelector('.regions-list-panel')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Kampagnenvorschlag öffnen' }));

    expect(onOpenRecommendation).toHaveBeenCalledWith('rec-1');
  });

  it('can filter the comparison list to low-evidence regions', () => {
    render(
      <RegionWorkbench
        virus="Influenza A"
        onVirusChange={noop}
        regionsView={buildRegionsView()}
        workspaceStatus={null}
        loading={false}
        selectedRegion="BE"
        onSelectRegion={noop}
        onOpenRecommendation={noop}
        onGenerateRegionCampaign={noop}
        regionActionLoading={false}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Zu wenig Evidenz' }));

    expect(screen.getByRole('heading', { name: 'Regionen mit zu wenig Evidenz' })).toBeInTheDocument();
    expect(screen.getByText('Sachsen')).toBeInTheDocument();
  });
});
