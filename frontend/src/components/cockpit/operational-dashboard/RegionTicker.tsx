import React from 'react';

import { formatCurrency, formatPercent } from '../cockpitUtils';
import { OperationalRegionRow } from './types';

function normalizeStage(value?: string | null): string {
  return String(value || '').trim().toLowerCase();
}

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const pct = value <= 1 ? value * 100 : value;
  return formatPercent(pct, digits);
}

function actionLabel(stage?: string | null): string {
  const normalized = normalizeStage(stage);
  if (normalized === 'activate') return 'Freigeben';
  if (normalized === 'prepare') return 'Prüfen';
  return 'Beobachten';
}

function trendArrow(percent?: number | null): string {
  if (percent == null || Number.isNaN(percent)) return '→';
  if (percent > 1) return '↑';
  if (percent < -1) return '↓';
  return '→';
}

interface Props {
  rows: OperationalRegionRow[];
  selectedRegion: string | null;
  onSelectRegion: (code: string) => void;
  onAction: (row: OperationalRegionRow) => void;
}

const RegionTicker: React.FC<Props> = ({
  rows,
  selectedRegion,
  onSelectRegion,
  onAction,
}) => (
  <div className="ops-region-ticker">
    <div className="ops-table-wrap">
      <table className="ops-table ops-region-ticker__table">
        <thead>
          <tr>
            <th>#</th>
            <th>Region</th>
            <th>Stage</th>
            <th>Trend</th>
            <th>Budget</th>
            <th>Aktion</th>
          </tr>
        </thead>
        <tbody>
          {rows.length > 0 ? rows.map((row) => (
            <tr
              key={row.code}
              className={selectedRegion === row.code ? 'ops-region-ticker__row ops-region-ticker__row--selected' : 'ops-region-ticker__row'}
              onClick={() => onSelectRegion(row.code)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelectRegion(row.code);
                }
              }}
              tabIndex={0}
              role="button"
              aria-label={`${row.name} auswählen`}
              aria-pressed={selectedRegion === row.code}
            >
              <td className="ops-region-ticker__rank">{row.rank ?? '-'}</td>
              <td>
                <strong>{row.name}</strong>
                <div className="ops-region-ticker__meta">{row.productCluster}</div>
              </td>
              <td>
                <span className={`ops-stage-dot ops-stage-dot--${normalizeStage(row.stage) || 'watch'}`} aria-hidden="true" />
                <span className="ops-region-ticker__stage-text">{row.stage}</span>
              </td>
              <td className="ops-region-ticker__trend">
                <span className="ops-region-ticker__trend-arrow">{trendArrow(row.trendPercent)}</span>
                <span>{row.trendPercent != null ? formatPercent(row.trendPercent, 0) : row.trendLabel}</span>
              </td>
              <td className="ops-region-ticker__budget">
                <strong>{row.budgetAmount != null ? formatCurrency(row.budgetAmount) : '-'}</strong>
                <div className="ops-region-ticker__meta">{row.budgetShare != null ? `${formatFractionPercent(row.budgetShare, 1)} Anteil` : 'Kein Anteil'}</div>
              </td>
              <td>
                <button
                  type="button"
                  className="media-button secondary ops-region-ticker__action"
                  onClick={(event) => {
                    event.stopPropagation();
                    onAction(row);
                  }}
                >
                  {actionLabel(row.stage)}
                </button>
              </td>
            </tr>
          )) : (
            <tr>
              <td colSpan={6} className="ops-table-empty">Noch keine regionalen Zeilen im aktuellen Scope.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  </div>
);

export default RegionTicker;
