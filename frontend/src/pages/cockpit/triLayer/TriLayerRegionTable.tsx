import React from 'react';

import type { TriLayerRegion } from './types';

function formatScore(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toFixed(1);
}

function formatWeight(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toFixed(2);
}

function formatLabel(value: string): string {
  return value.replace(/_/g, ' ');
}

export const TriLayerRegionTable: React.FC<{ regions: TriLayerRegion[] }> = ({ regions }) => (
  <section className="tri-layer-panel">
    <div className="tri-layer-section-head">
      <div>
        <div className="tri-layer-kicker">Regional Table</div>
        <h2>Regional evidence rows</h2>
      </div>
      <p>{regions.length} regions in this research snapshot.</p>
    </div>
    {regions.length === 0 ? (
      <div className="tri-layer-empty">No regional rows available for this research snapshot.</div>
    ) : (
      <div className="tri-layer-table-wrap">
        <table className="tri-layer-table">
          <thead>
            <tr>
              <th scope="col">Region</th>
              <th scope="col">Code</th>
              <th scope="col">EWS</th>
              <th scope="col">CRS</th>
              <th scope="col">Budget State</th>
              <th scope="col">Wave Phase</th>
              <th scope="col">Wastewater weight</th>
              <th scope="col">Clinical weight</th>
              <th scope="col">Sales weight</th>
              <th scope="col">Explanation</th>
            </tr>
          </thead>
          <tbody>
            {regions.map((region) => (
              <tr key={region.region_code}>
                <td>{region.region}</td>
                <td>{region.region_code}</td>
                <td>{formatScore(region.early_warning_score)}</td>
                <td>{formatScore(region.commercial_relevance_score)}</td>
                <td>{formatLabel(region.budget_permission_state)}</td>
                <td>{formatLabel(region.wave_phase)}</td>
                <td>{formatWeight(region.evidence_weights.wastewater)}</td>
                <td>{formatWeight(region.evidence_weights.clinical)}</td>
                <td>{formatWeight(region.evidence_weights.sales)}</td>
                <td>{region.explanation || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </section>
);

export default TriLayerRegionTable;
