import React from 'react';

import { OPERATOR_LABELS } from '../../../constants/operatorLabels';
import { evidenceStatusLabel } from '../../../lib/copy';
import { formatCurrency, formatPercent } from '../cockpitUtils';
import { OperatorChipRail, OperatorPanel, OperatorStat } from '../operator/OperatorPrimitives';
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
  if (normalized === 'activate') return 'Freigabe';
  if (normalized === 'prepare') return 'Prüfen';
  return 'Beobachten';
}

function primaryCtaLabel(stage?: string | null): string {
  const normalized = normalizeStage(stage);
  if (normalized === 'activate') return 'Freigabe öffnen';
  if (normalized === 'prepare') return 'Prüfung öffnen';
  return 'Lage beobachten';
}

function stageClass(stage?: string | null): string {
  const normalized = normalizeStage(stage);
  if (normalized === 'activate') return 'ops-stage-pill ops-stage-pill--activate';
  if (normalized === 'prepare') return 'ops-stage-pill ops-stage-pill--prepare';
  return 'ops-stage-pill ops-stage-pill--watch';
}

interface Props {
  row: OperationalRegionRow;
  virus: string;
  horizonDays: number;
  onOpenDetails: (regionCode?: string) => void;
  onOpenApproval: () => void;
}

const ActionPanel: React.FC<Props> = ({
  row,
  virus,
  horizonDays,
  onOpenDetails,
  onOpenApproval,
}) => {
  const progressValue = Math.max(8, Math.round((row.signalStrength ?? row.eventProbability ?? 0) * 100));

  return (
    <OperatorPanel
      eyebrow="Fokusfall"
      title={`${row.name}: ${actionLabel(row.stage)}`}
      description="Der wichtigste Fall im aktuellen Scope bleibt hier kompakt sichtbar: Relevanz, Budget, Status und die passende nächste Aktion."
      className="ops-action-panel"
      tone="accent"
      actions={<span className={stageClass(row.stage)}>{row.stage}</span>}
    >
      <OperatorChipRail className="ops-action-panel__chips">
        <span className="step-chip">{virus}</span>
        <span className="step-chip">{horizonDays}-Tage-Sicht</span>
        <span className="step-chip">Bundesland-Ebene</span>
      </OperatorChipRail>

      <div className="ops-action-panel__hero">
        <div>
          <p className="ops-action-panel__region">{row.name}</p>
          <p className="ops-action-panel__meta">
            <span>{row.productCluster}</span>
            <span>{row.keywordCluster}</span>
          </p>
        </div>
        <div className="ops-action-panel__probability">
          <span className="ops-action-panel__probability-label">{OPERATOR_LABELS.forecast_event_probability}</span>
          <strong>{formatFractionPercent(row.eventProbability, 0)}</strong>
        </div>
      </div>

      <div className="operator-stat-grid metric-strip">
        <OperatorStat label="Budget" value={row.budgetAmount != null ? formatCurrency(row.budgetAmount) : '-'} tone="accent" />
        <OperatorStat label={OPERATOR_LABELS.allocation_share} value={row.budgetShare != null ? formatFractionPercent(row.budgetShare, 1) : '-'} />
        <OperatorStat label="Produktcluster" value={row.productCluster} />
        <OperatorStat label={OPERATOR_LABELS.business_validation_gate} value={row.businessGateLabel || evidenceStatusLabel('observe_only')} meta={row.businessGateHelper} />
      </div>

      <div className="ops-action-panel__status-row" aria-label="Statusübersicht Fokusfall">
        <div className="ops-action-panel__status-item">
          <span className="ops-action-panel__status-label">Evidenz</span>
          <strong>{row.evidenceLabel}</strong>
        </div>
        <div className="ops-action-panel__status-item">
          <span className="ops-action-panel__status-label">{OPERATOR_LABELS.business_validation_gate}</span>
          <strong>{row.businessGateLabel || evidenceStatusLabel('observe_only')}</strong>
        </div>
        <div className="ops-action-panel__status-item">
          <span className="ops-action-panel__status-label">Aktion</span>
          <strong>{row.actionLabel}</strong>
        </div>
      </div>

      <div className="ops-action-panel__signal">
        <div className="ops-action-panel__signal-head">
          <span>{OPERATOR_LABELS.signal_confidence}</span>
          <strong>{formatFractionPercent(row.signalStrength, 0)}</strong>
        </div>
        <div className="ops-action-panel__signal-track" aria-label={OPERATOR_LABELS.signal_confidence}>
          <div className={`ops-action-panel__signal-fill ops-action-panel__signal-fill--${normalizeStage(row.stage) || 'watch'}`} style={{ width: `${progressValue}%` }} />
        </div>
      </div>

      <div className="ops-command-note-grid">
        <div className="workspace-note-card">
          <strong>Warum jetzt:</strong> {row.summary}
        </div>
        <div className="workspace-note-card">
          <strong>Worauf achten:</strong> {row.uncertainty}
        </div>
      </div>

      <div className="action-row">
        <button type="button" className="media-button secondary" onClick={() => onOpenDetails(row.code)}>
          Details öffnen
        </button>
        <button type="button" className="media-button" onClick={onOpenApproval}>
          {primaryCtaLabel(row.stage)}
        </button>
      </div>
    </OperatorPanel>
  );
};

export default ActionPanel;
