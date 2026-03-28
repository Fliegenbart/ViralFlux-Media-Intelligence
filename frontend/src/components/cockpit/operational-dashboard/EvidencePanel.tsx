import React from 'react';

import { OperatorPanel, OperatorStat } from '../operator/OperatorPrimitives';
import { formatPercent } from '../cockpitUtils';
import { OperationalRegionRow } from './types';

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const pct = value <= 1 ? value * 100 : value;
  return formatPercent(pct, digits);
}

interface Props {
  row: OperationalRegionRow;
  onOpenEvidence: () => void;
}

const EvidencePanel: React.FC<Props> = ({ row, onOpenEvidence }) => (
  <OperatorPanel
    eyebrow="Evidenz"
    title="Forecast-Qualität, Unsicherheit und Backtest"
    description="Die erste Ebene bleibt kompakt: Belastbarkeit, Frische und Risiko. Tiefergehende Prüfung bleibt erst nach dem Aufklappen sichtbar."
    actions={(
      <button type="button" className="media-button secondary" onClick={onOpenEvidence}>
        Evidenz öffnen
      </button>
    )}
  >
    <div className="operator-stat-grid metric-strip">
      <OperatorStat label="Forecast-Qualität" value={formatFractionPercent(row.forecastConfidence, 0)} />
      <OperatorStat label="Datenfrische" value={formatFractionPercent(row.sourceFreshness, 0)} />
      <OperatorStat label="Revisionsrisiko" value={formatFractionPercent(row.revisionRisk, 0)} />
      <OperatorStat label="Quellenabgleich" value={formatFractionPercent(row.crossSourceAgreement, 0)} />
    </div>

    <div className="ops-command-note-grid">
      <div className="workspace-note-card">
        <strong>Bereits belastbar:</strong> {row.summary}
      </div>
      <div className="workspace-note-card">
        <strong>Mit Vorsicht lesen:</strong> {row.uncertainty}
      </div>
      <div className="workspace-note-card">
        <strong>Evidenzstatus:</strong> {row.evidenceLabel}. {row.evidenceHelper}
      </div>
    </div>
  </OperatorPanel>
);

export default EvidencePanel;
