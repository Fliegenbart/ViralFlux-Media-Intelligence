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
      ],
    },
    top_regions: [
      {
        code: 'BE',
        name: 'Berlin',
        trend: 'steigend',
        signal_score: 0.82,
      },
    ],
    decision_state: 'GO',
  };
}

const noop = () => {};

describe('RegionWorkbench', () => {
  it('shows one primary action for the selected region', () => {
    const onOpenRecommendation = jest.fn();

    render(
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

    expect(screen.getByText('Hier sehen wir den wahrscheinlichen frühen Start')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Kampagnenvorschlag öffnen' })).toBeInTheDocument();
    expect(screen.getByText(/Warum: Berlin ist aktuell die klarste Region/)).toBeInTheDocument();
    expect(screen.queryByText('Empfehlung neu berechnen')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Kampagnenvorschlag öffnen' }));

    expect(onOpenRecommendation).toHaveBeenCalledWith('rec-1');
  });
});
