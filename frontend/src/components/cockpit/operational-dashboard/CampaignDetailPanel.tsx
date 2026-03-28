import React from 'react';

import { OPERATOR_LABELS } from '../../../constants/operatorLabels';
import { formatCurrency, formatPercent } from '../cockpitUtils';
import { OperatorChipRail, OperatorPanel, OperatorStat } from '../operator/OperatorPrimitives';
import { OperationalRegionRow } from './types';

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const pct = value <= 1 ? value * 100 : value;
  return formatPercent(pct, digits);
}

interface Props {
  row: OperationalRegionRow;
  onOpenCampaigns: () => void;
}

const CampaignDetailPanel: React.FC<Props> = ({ row, onOpenCampaigns }) => (
  <OperatorPanel
    eyebrow="Kampagnen-Detail"
    title="Produktcluster, Budget und Freigabe-Status"
    description="Hier bleibt sichtbar, wie aus der regionalen Priorisierung ein konkreter Maßnahmenfall wird."
    actions={(
      <button type="button" className="media-button secondary" onClick={onOpenCampaigns}>
        Kampagnen öffnen
      </button>
    )}
  >
    <div className="operator-stat-grid metric-strip">
      <OperatorStat label="Produktcluster" value={row.productCluster} tone="accent" />
      <OperatorStat label="Budget" value={row.budgetAmount != null ? formatCurrency(row.budgetAmount) : '-'} />
      <OperatorStat label={OPERATOR_LABELS.allocation_share} value={row.budgetShare != null ? formatFractionPercent(row.budgetShare, 1) : '-'} />
      <OperatorStat label={OPERATOR_LABELS.business_validation_gate} value={row.businessGateLabel} meta={row.businessGateHelper} />
    </div>

    <div className="ops-command-panel-grid ops-command-panel-grid--two-up">
      <div className="workspace-note-card">
        <strong>Keyword-Cluster:</strong> {row.keywordCluster}
      </div>
      <div className="workspace-note-card">
        <strong>Kanäle:</strong> {row.channels.length > 0 ? row.channels.join(', ') : 'Noch keine Kanäle sichtbar.'}
      </div>
    </div>

    <OperatorChipRail className="ops-command-chip-wrap">
      {row.keywords.length > 0 ? row.keywords.slice(0, 6).map((keyword) => (
        <span key={keyword} className="step-chip">{keyword}</span>
      )) : <span className="step-chip">Noch keine Keywords sichtbar</span>}
    </OperatorChipRail>
  </OperatorPanel>
);

export default CampaignDetailPanel;
