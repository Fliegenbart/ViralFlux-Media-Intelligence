import React from 'react';

import type { TriLayerGates, TriLayerRegion, TriLayerGateState } from './types';

const GATE_ROWS: Array<[keyof TriLayerGates, string]> = [
  ['epidemiological_signal', 'Epi Signal'],
  ['clinical_confirmation', 'Clinical Confirmation'],
  ['sales_calibration', 'Sales Calibration'],
  ['coverage', 'Coverage'],
  ['drift', 'Drift'],
  ['budget_isolation', 'Budget Isolation'],
];

function gateLabel(value: TriLayerGateState): string {
  return value.replace(/_/g, ' ');
}

function summarizeGate(regions: TriLayerRegion[], key: keyof TriLayerGates): TriLayerGateState {
  const states = regions.map((region) => region.gates[key]);
  if (!states.length) return 'not_available';
  if (states.includes('fail')) return 'fail';
  if (states.includes('watch')) return 'watch';
  if (states.includes('not_available')) return 'not_available';
  return 'pass';
}

export const TriLayerGateMatrix: React.FC<{ regions: TriLayerRegion[] }> = ({ regions }) => (
  <section className="tri-layer-panel">
    <div className="tri-layer-section-head">
      <div>
        <div className="tri-layer-kicker">Gate Matrix</div>
        <h2>Evidence gates</h2>
      </div>
      <p>Budget permission stays conservative when any required layer is incomplete.</p>
    </div>
    <div className="tri-layer-gate-grid" role="table" aria-label="Tri-Layer evidence gate matrix">
      {GATE_ROWS.map(([key, label]) => {
        const state = summarizeGate(regions, key);
        return (
          <div key={key} className="tri-layer-gate-row" role="row">
            <span role="cell">{label}</span>
            <strong className={`tri-layer-pill tri-layer-pill--${state}`} role="cell">
              {gateLabel(state)}
            </strong>
          </div>
        );
      })}
    </div>
  </section>
);

export default TriLayerGateMatrix;
