import React from 'react';

import type { TriLayerSourceStatus as TriLayerSourceStatusShape, TriLayerSourceStatusItem } from './types';

const SOURCE_LABELS: Array<[keyof TriLayerSourceStatusShape, string]> = [
  ['wastewater', 'Abwasser'],
  ['clinical', 'Clinical / SurvStat / ARE'],
  ['sales', 'Sales'],
];

function formatPercent(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${Math.round(value * 100)}%`;
}

function formatFreshness(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toFixed(1)} d`;
}

function statusLabel(source: keyof TriLayerSourceStatusShape, item: TriLayerSourceStatusItem): string {
  if (source === 'sales' && item.status === 'not_connected') return 'Sales layer not connected';
  return item.status.replace(/_/g, ' ');
}

export const TriLayerSourceStatus: React.FC<{ sourceStatus: TriLayerSourceStatusShape }> = ({ sourceStatus }) => (
  <section className="tri-layer-source-strip" aria-label="Tri-Layer source status">
    {SOURCE_LABELS.map(([key, label]) => {
      const item = sourceStatus[key];
      return (
        <article key={key} className={`tri-layer-source tri-layer-source--${item.status}`}>
          <div className="tri-layer-source__label">{label}</div>
          <strong>{statusLabel(key, item)}</strong>
          <div className="tri-layer-source__meta">
            <span>Coverage {formatPercent(item.coverage)}</span>
            <span>Freshness {formatFreshness(item.freshness_days)}</span>
          </div>
        </article>
      );
    })}
  </section>
);

export default TriLayerSourceStatus;
