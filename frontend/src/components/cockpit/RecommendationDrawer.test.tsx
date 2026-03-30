import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import RecommendationDrawer from './RecommendationDrawer';

function buildDetail() {
  return {
    id: 'rec-1',
    status: 'READY',
    lifecycle_state: 'APPROVE',
    status_label: 'Zur Freigabe',
    region: 'BE',
    region_name: 'Berlin',
    region_codes_display: ['Berlin'],
    updated_at: '2026-03-25T10:00:00Z',
    display_title: 'Berlin jetzt priorisieren',
    recommended_product: 'GeloMyrtol forte',
    budget_shift_pct: 0.22,
    priority_score: 0.81,
    confidence: 0.74,
    evidence_class: 'truth_backed',
    field_contracts: {},
    campaign_pack: {
      budget_plan: { weekly_budget_eur: 55200 },
      channel_plan: [
        { channel: 'search', role: 'Push', share_pct: 58 },
        { channel: 'social', role: 'Support', share_pct: 22 },
      ],
      message_framework: {
        hero_message: 'Berlin zuerst bearbeiten.',
        support_points: ['Hohe Nachfrage', 'Gutes Timing für GELO'],
      },
      ai_plan: {
        creative_angles: ['Schnelle Hilfe bei Schleim'],
        keyword_clusters: ['husten schleim loesen'],
        next_steps: [{ task: 'Freigabe prüfen', owner: 'PEIX Ops', eta: 'heute' }],
        compliance_hinweis: 'Claims vor Freigabe noch einmal gegenlesen.',
      },
      targeting: {
        audience_segments: ['Akute Atemwegsbeschwerden'],
      },
      measurement_plan: {
        primary_kpi: 'sales',
      },
    },
    activation_window: { start: '2026-03-26', end: '2026-04-02' },
    learning_state: 'active',
    primary_kpi: 'sales',
    connector_key: 'meta_ads',
    decision_brief: {
      summary_sentence: 'Berlin sollte jetzt zuerst geprüft werden.',
    },
    recommendation_rationale: {
      why: ['Berlin führt aktuell den Arbeitsfall an.'],
    },
    publish_blockers: [],
    is_publishable: true,
  } as any;
}

function buildSyncPreview() {
  return {
    connector_key: 'meta_ads',
    connector_label: 'Meta Ads',
    generated_at: '2026-03-25T10:15:00Z',
    connector_payload: { campaign: 'Berlin jetzt priorisieren' },
    readiness: {
      state: 'approval_required',
      can_sync_now: false,
      blockers: ['Freigabe steht noch aus.'],
      warnings: ['Channel-Mapping vor Versand kurz prüfen.'],
    },
  } as any;
}

describe('RecommendationDrawer', () => {
  it('renders an approval memo, keeps technical detail behind disclosure, and closes on Escape', () => {
    const onClose = jest.fn();

    render(
      <RecommendationDrawer
        detail={buildDetail()}
        loading={false}
        connectorCatalog={[{ key: 'meta_ads', label: 'Meta Ads' } as any]}
        syncPreview={buildSyncPreview()}
        syncLoading={false}
        statusUpdating={false}
        regenerating={false}
        onClose={onClose}
        onAdvanceStatus={jest.fn()}
        onRegenerateAI={jest.fn()}
        onPrepareSync={jest.fn()}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Berlin jetzt priorisieren' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Kampagnen-Detail schließen' })).toHaveFocus();
    expect(screen.getByText('GELO-Freigabe-Memo')).toBeInTheDocument();
    expect(screen.getAllByText('Freigabe auf einen Blick').length).toBeGreaterThan(0);
    expect(screen.getByText('Was diese Empfehlung trägt')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Freigeben' })).toBeInTheDocument();
    expect(screen.getAllByText('Übergabe vorbereiten').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Zweiter Blick: Kennzahlen und Lernsignale/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Bundesland-Level/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Signal-Score/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Zweiter Blick: Kennzahlen und Lernsignale/i }));

    expect(screen.getAllByText(/Signal-Score/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Aktivierungs-Priorität/).length).toBeGreaterThan(0);

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalled();
  });
});
