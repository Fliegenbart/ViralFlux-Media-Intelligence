import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

jest.mock('./cockpitUtils', () => ({
  __esModule: true,
  formatDateShort: () => '18.03.2026',
  learningStateLabel: () => 'im Aufbau',
  recommendationLane: (card: { lifecycle_state?: string | null; status?: string | null }) => {
    const normalized = String(card.lifecycle_state || card.status || '').toLowerCase();
    if (normalized === 'review') return 'review';
    if (normalized === 'approve' || normalized === 'approved') return 'approve';
    if (normalized === 'sync' || normalized === 'sync_ready') return 'sync';
    if (normalized === 'live' || normalized === 'activated') return 'live';
    return 'prepare';
  },
  signalConfidencePercent: () => 81,
  statusTone: () => ({
    background: 'rgba(31, 122, 102, 0.12)',
    color: '#1f7a66',
    border: '1px solid rgba(31, 122, 102, 0.18)',
  }),
  workflowLabel: (status?: string | null) => {
    const normalized = String(status || '').toUpperCase();
    if (normalized === 'APPROVE' || normalized === 'APPROVED') return 'Zur Entscheidung';
    if (normalized === 'SYNC' || normalized === 'SYNC_READY') return 'Bereit zur Übergabe';
    if (normalized === 'LIVE' || normalized === 'ACTIVATED') return 'Aktiv';
    if (normalized === 'REVIEW') return 'Zur Prüfung';
    return 'In Vorbereitung';
  },
}));

import CampaignStudio from './CampaignStudio';
import { MediaCampaignsResponse, WorkspaceStatusSummary } from '../../types/media';

function buildCampaignsView(): MediaCampaignsResponse {
  return {
    generated_at: '2026-03-18T08:00:00Z',
    archived_cards: [],
    summary: {
      total_cards: 3,
      active_cards: 1,
      deduped_cards: 3,
      publishable_cards: 2,
      expired_cards: 0,
      visible_cards: 3,
      hidden_backlog_cards: 1,
      states: {
        review: 1,
        approve: 1,
        sync: 0,
        live: 1,
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
        brand: 'GELO',
        product: 'GeloMyrtol forte',
        recommended_product: 'GeloMyrtol forte',
        region: 'Berlin',
        region_codes_display: ['Berlin'],
        display_title: 'Berlin Search',
        budget_shift_pct: 22,
        channel_mix: { search: 0.58, social: 0.22 },
        reason: 'Berlin sollte jetzt zuerst geprüft werden.',
        confidence: 0.81,
        signal_score: 0.84,
        priority_score: 0.9,
        evidence_class: 'truth_backed',
        publish_blockers: [],
        campaign_preview: {
          budget: { weekly_budget_eur: 55200 },
        },
      },
      {
        id: 'rec-blocked',
        status: 'READY',
        lifecycle_state: 'APPROVE',
        type: 'campaign',
        urgency_score: 0.6,
        brand: 'GELO',
        product: 'GeloBronchial',
        recommended_product: 'GeloBronchial',
        region: 'Bayern',
        region_codes_display: ['Bayern'],
        display_title: 'Bayern Social',
        budget_shift_pct: 12,
        channel_mix: { social: 0.7 },
        reason: 'Bayern ist der nächste Freigabefall.',
        confidence: 0.72,
        signal_score: 0.67,
        priority_score: 0.7,
        evidence_class: 'guarded',
        publish_blockers: ['Freigabetext für GELO noch nicht final abgestimmt.'],
        campaign_preview: {
          budget: { weekly_budget_eur: 18000 },
        },
      },
      {
        id: 'rec-live',
        status: 'ACTIVATED',
        lifecycle_state: 'LIVE',
        type: 'campaign',
        urgency_score: 0.4,
        brand: 'GELO',
        product: 'GeloProsed',
        recommended_product: 'GeloProsed',
        region: 'Nordrhein-Westfalen',
        region_codes_display: ['Nordrhein-Westfalen'],
        display_title: 'NRW Programmatic',
        budget_shift_pct: 0,
        channel_mix: { programmatic: 0.6, ctv: 0.2 },
        reason: 'NRW läuft bereits aktiv weiter.',
        confidence: 0.68,
        signal_score: 0.61,
        priority_score: 0.45,
        evidence_class: 'ready',
        publish_blockers: [],
        campaign_preview: {
          budget: { weekly_budget_eur: 22000 },
        },
      },
    ],
  };
}

function buildWorkspaceStatus(): WorkspaceStatusSummary {
  return {
    forecast_status: 'Belastbar',
    data_freshness: 'Aktuell',
    customer_data_status: 'Teilweise',
    open_blockers: '1 offen',
    last_import_at: '2026-03-18T07:40:00Z',
    blocker_count: 1,
    blockers: ['Freigabetext für GELO noch nicht final abgestimmt.'],
    summary: 'Ein blockernder Punkt verhindert gerade einen Teil der Übergabe.',
    items: [
      {
        key: 'forecast_status',
        question: 'Wie belastbar ist das Signal?',
        value: 'Mit Kundendaten gestützt',
        detail: 'Forecast- und Kundendaten zeigen dieselbe Richtung.',
        tone: 'success',
      },
      {
        key: 'data_freshness',
        question: 'Wie frisch sind die Daten?',
        value: 'Aktuell',
        detail: 'Die zugrunde liegenden Daten wurden heute aktualisiert.',
        tone: 'success',
      },
      {
        key: 'open_blockers',
        question: 'Was blockiert noch?',
        value: '1 offen',
        detail: 'Freigabetext für GELO noch nicht final abgestimmt.',
        tone: 'warning',
      },
    ],
  };
}

const noop = () => {};

describe('CampaignStudio', () => {
  it('puts the GELO approval case first and opens the focus recommendation', () => {
    const onOpenRecommendation = jest.fn();

    render(
      <CampaignStudio
        campaignsView={buildCampaignsView()}
        virus="Influenza A"
        brand="GELO"
        budget={120000}
        goal="Sichtbarkeit steigern"
        workspaceStatus={buildWorkspaceStatus()}
        loading={false}
        generationLoading={false}
        onBrandChange={noop}
        onBudgetChange={noop}
        onGoalChange={noop}
        onGenerate={noop}
        onOpenRecommendation={onOpenRecommendation}
      />,
    );

    expect(screen.getAllByRole('heading', { name: 'Welcher Fall als Nächstes geprüft werden sollte' })).toHaveLength(1);
    expect(screen.getAllByText('Empfohlene Aktion').length).toBeGreaterThan(0);
    expect(screen.getByText('Nächster Schritt')).toBeInTheDocument();
    expect(screen.getByText('Warum dieser Fall jetzt vorne liegt')).toBeInTheDocument();
    expect(screen.getByText('Hier wird sichtbar, ob der Fall jetzt geprüft werden sollte, ob noch etwas fehlt oder ob er schon weitergegeben werden kann.')).toBeInTheDocument();
    expect(screen.getAllByText('Belastbarkeit').length).toBeGreaterThan(0);
    expect(screen.getByText('Was diesen Fokusfall trägt')).toBeInTheDocument();
    expect(screen.getAllByText('Danach').length).toBeGreaterThan(0);
    expect(screen.getByText('Arbeitsphasen')).toBeInTheDocument();
    expect(screen.getAllByText('Weitere Vorschläge erstellen').length).toBeGreaterThan(0);
    expect(screen.getByText(/Offene Punkte klären/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Empfehlung prüfen' }));

    expect(onOpenRecommendation).toHaveBeenCalledWith('rec-review');
  });

  it('shows approval-oriented loading and empty states', () => {
    const { rerender } = render(
      <CampaignStudio
        campaignsView={null}
        virus="Influenza A"
        brand="GELO"
        budget={120000}
        goal="Sichtbarkeit steigern"
        workspaceStatus={null}
        loading
        generationLoading={false}
        onBrandChange={noop}
        onBudgetChange={noop}
        onGoalChange={noop}
        onGenerate={noop}
        onOpenRecommendation={noop}
      />,
    );

    expect(screen.getByLabelText('Kampagnenansicht wird geladen')).toBeInTheDocument();

    rerender(
      <CampaignStudio
        campaignsView={{
          generated_at: '2026-03-18T08:00:00Z',
          archived_cards: [],
          cards: [],
          summary: {
            total_cards: 0,
            active_cards: 0,
            deduped_cards: 0,
            publishable_cards: 0,
            expired_cards: 0,
            visible_cards: 0,
            hidden_backlog_cards: 0,
            states: {},
            learning_state: 'missing',
          },
        }}
        virus="Influenza A"
        brand="GELO"
        budget={120000}
        goal="Sichtbarkeit steigern"
        workspaceStatus={null}
        loading={false}
        generationLoading={false}
        onBrandChange={noop}
        onBudgetChange={noop}
        onGoalChange={noop}
        onGenerate={noop}
        onOpenRecommendation={noop}
      />,
    );

    expect(screen.getByText('Noch kein prüfbarer Fall sichtbar')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Erste Vorschläge erstellen' })).toBeInTheDocument();
  });
});
