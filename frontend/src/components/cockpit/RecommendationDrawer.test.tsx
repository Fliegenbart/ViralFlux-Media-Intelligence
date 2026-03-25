import '@testing-library/jest-dom';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

import RecommendationDrawer from './RecommendationDrawer';

function buildDetail() {
  return {
    id: 'rec-1',
    status: 'REVIEW',
    lifecycle_state: 'REVIEW',
    status_label: 'In Prüfung',
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
      message_framework: {
        hero_message: 'Berlin zuerst bearbeiten.',
        support_points: ['Hohe Nachfrage'],
      },
      ai_plan: {
        creative_angles: ['Schnelle Hilfe bei Schleim'],
        keyword_clusters: ['husten schleim loesen'],
        next_steps: [{ task: 'Review', owner: 'Ops', eta: 'heute' }],
      },
    },
    activation_window: { start: '2026-03-26' },
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

describe('RecommendationDrawer', () => {
  it('renders a labeled dialog and closes on Escape', () => {
    const onClose = jest.fn();

    const { container } = render(
      <RecommendationDrawer
        detail={buildDetail()}
        loading={false}
        connectorCatalog={[{ key: 'meta_ads', label: 'Meta Ads' } as any]}
        syncPreview={null}
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
    expect(container.querySelector('.review-sheet-grid--primary')).toBeTruthy();
    expect(container.querySelector('.review-sheet-grid--secondary')).toBeTruthy();
    expect(screen.getAllByText(/Ranking-Signal/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Entscheidungs-Priorität/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Bundesland-Level/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Mit Kundendaten gestützt/).length).toBeGreaterThan(0);

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalled();
  });
});
