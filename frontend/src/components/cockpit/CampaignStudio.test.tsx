import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import CampaignStudio from './CampaignStudio';
import { MediaCampaignsResponse } from '../../types/media';

function buildCampaignsView(): MediaCampaignsResponse {
  return {
    generated_at: '2026-03-18T08:00:00Z',
    archived_cards: [],
    summary: {
      total_cards: 2,
      active_cards: 2,
      deduped_cards: 2,
      publishable_cards: 1,
      expired_cards: 0,
      visible_cards: 2,
      hidden_backlog_cards: 1,
      states: {
        review: 1,
        approve: 1,
        sync: 0,
        live: 0,
        prepare: 0,
      },
      learning_state: 'im_aufbau',
    },
    cards: [
      {
        id: 'rec-review',
        status: 'NEW',
        lifecycle_state: 'REVIEW',
        type: 'campaign',
        urgency_score: 0.8,
        brand: 'gelo',
        product: 'GeloMyrtol forte',
        region: 'Berlin',
        region_codes_display: ['Berlin'],
        display_title: 'Berlin Search',
        budget_shift_pct: 22,
        channel_mix: {},
        reason: 'Berlin sollte jetzt zuerst geprüft werden.',
        confidence: 0.81,
        signal_score: 0.84,
        priority_score: 0.9,
        campaign_preview: {
          budget: { weekly_budget_eur: 55200 },
        },
      },
      {
        id: 'rec-approve',
        status: 'READY',
        lifecycle_state: 'APPROVE',
        type: 'campaign',
        urgency_score: 0.6,
        brand: 'gelo',
        product: 'GeloBronchial',
        region: 'Bayern',
        region_codes_display: ['Bayern'],
        display_title: 'Bayern Social',
        budget_shift_pct: 12,
        channel_mix: {},
        reason: 'Bayern ist der nächste Freigabefall.',
        confidence: 0.72,
        signal_score: 0.67,
        priority_score: 0.7,
        campaign_preview: {
          budget: { weekly_budget_eur: 18000 },
        },
      },
    ],
  };
}

const noop = () => {};

describe('CampaignStudio', () => {
  it('keeps review focus above generation and opens the focus card first', () => {
    const onOpenRecommendation = jest.fn();

    render(
      <CampaignStudio
        campaignsView={buildCampaignsView()}
        virus="Influenza A"
        brand="gelo"
        budget={120000}
        goal="Sichtbarkeit steigern"
        workspaceStatus={null}
        loading={false}
        generationLoading={false}
        onBrandChange={noop}
        onBudgetChange={noop}
        onGoalChange={noop}
        onGenerate={noop}
        onOpenRecommendation={onOpenRecommendation}
      />,
    );

    expect(screen.getByText('Jetzt zuerst prüfen')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Diesen Fall öffnen' })).toBeInTheDocument();
    expect(screen.getByText('Vorbereitung')).toBeInTheDocument();
    expect(screen.getByText('Freigabe')).toBeInTheDocument();
    expect(screen.getByText('Weitere Vorschläge erstellen')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Diesen Fall öffnen' }));

    expect(onOpenRecommendation).toHaveBeenCalledWith('rec-review');
  });
});
