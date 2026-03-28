import React from 'react';

import { OperatorPanel } from '../operator/OperatorPrimitives';
import { OperationalRegionRow } from './types';

function renderList(items: string[], emptyText: string) {
  return (
    <ul className="ops-command-trace-list">
      {items.length > 0 ? items.map((item) => <li key={item}>{item}</li>) : <li>{emptyText}</li>}
    </ul>
  );
}

interface Props {
  row: OperationalRegionRow;
}

const TracePanel: React.FC<Props> = ({ row }) => (
  <OperatorPanel
    eyebrow="Nachvollziehbarkeit"
    title="Decision, Allocation und Recommendation Trace"
    description="Die Entscheidungswege bleiben sichtbar, aber klar in der zweiten Ebene."
  >
    <div className="ops-command-trace-grid">
      <div className="soft-panel">
        <h4 className="ops-command-trace-title">Decision Trace</h4>
        {renderList(row.decisionTrace, 'Noch keine Decision-Spur sichtbar.')}
      </div>
      <div className="soft-panel">
        <h4 className="ops-command-trace-title">Allocation Trace</h4>
        {renderList(row.allocationTrace, 'Noch keine Allocation-Spur sichtbar.')}
      </div>
      <div className="soft-panel">
        <h4 className="ops-command-trace-title">Recommendation Trace</h4>
        {renderList(row.recommendationTrace, 'Noch keine Recommendation-Spur sichtbar.')}
      </div>
    </div>
  </OperatorPanel>
);

export default TracePanel;
