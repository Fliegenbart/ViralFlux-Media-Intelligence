import React from 'react';

import type { TriLayerSummary } from './types';

function formatScore(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toFixed(1);
}

function formatState(value: string): string {
  return value.replace(/_/g, ' ');
}

export const TriLayerScoreCards: React.FC<{ summary: TriLayerSummary }> = ({ summary }) => (
  <section className="tri-layer-score-grid" aria-label="Tri-Layer score summary">
    <article className="tri-layer-score-card">
      <div className="tri-layer-kicker">Phase-Lead Frühwarn-Score</div>
      <strong className="tri-layer-score-value">{formatScore(summary.early_warning_score)}</strong>
      <p>Regionaler Atemwegsdruck aus Phase-Lead. Er priorisiert Regionen, gibt aber noch kein Budget frei.</p>
    </article>
    <article className="tri-layer-score-card">
      <div className="tri-layer-kicker">Commercial Relevance Score</div>
      <strong className="tri-layer-score-value">{formatScore(summary.commercial_relevance_score)}</strong>
      <p>{summary.commercial_relevance_score === null ? 'Sales layer not connected; kommerzielle Tragfähigkeit noch offen.' : 'Sales-calibrated commercial signal.'}</p>
    </article>
    <article className="tri-layer-score-card tri-layer-score-card--safety">
      <div className="tri-layer-kicker">Budget Permission State</div>
      <strong className="tri-layer-state-value">{formatState(summary.budget_permission_state)}</strong>
      <p>Budget can change: {String(summary.budget_can_change)}</p>
    </article>
  </section>
);

export default TriLayerScoreCards;
