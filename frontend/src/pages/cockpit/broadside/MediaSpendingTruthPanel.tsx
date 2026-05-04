import React from 'react';
import type { MediaSpendingTruthPayload, MediaSpendingTruthRegion } from '../types';

const STATUS_LABELS: Record<string, string> = {
  blocked: 'Blockiert',
  watch_only: 'Nur beobachten',
  planner_assist: 'Manuelle Prüfung',
  spendable: 'Budget-Gate offen mit Cap',
  shadow_only: 'Manuelle Prüfung',
  limited: 'Begrenzt',
  approved: 'Budget-Gate offen mit Cap',
  increase_approved: 'Erhöhen freigegeben',
  preposition_approved: 'Früh positionieren',
  maintain: 'Halten',
  cap_or_reduce: 'Deckeln oder senken',
  decrease_approved: 'Senken freigegeben',
};

const PERMISSION_LABELS: Record<string, string> = {
  blocked: 'Keine Budgetfreigabe',
  manual_approval_required: 'Manuelle Freigabe nötig',
  approved_with_cap: 'Budget-Gate offen mit Cap',
};

const RELEASE_HELP: Record<string, string> = {
  blocked: 'Keine verwertbare Media-Empfehlung. Das System beobachtet im Kalibrierungsfenster.',
  shadow_only: 'Empfehlungen werden berechnet, aber kein Budgetdelta ist freigegeben.',
  limited: 'Kleine budgetneutrale Deltas sind freigegeben, maximal 5 Prozent.',
  approved: 'Budgetneutrale Deltas sind innerhalb der normalen Caps freigegeben.',
};

const BLOCKED_REASON_LABELS: Record<string, string> = {
  forecast_quality_gate_failed: 'Forecast-Qualität nicht bestanden',
  decision_backtest_not_better_than_persistence: 'nicht besser als Persistence',
  decision_backtest_not_passed: 'Decision-Backtest nicht bestanden',
  data_quality_insufficient_for_budget_shift: 'Datenqualität reicht nicht für Budgetshift',
  business_constraints_block_budget_shift: 'Business-Regeln blockieren Budgetshift',
};

const REASON_LABELS: Record<string, string> = {
  high_surge_probability: 'hohe 7-Tage-Wachstumswahrscheinlichkeit',
  positive_wastewater_case_divergence: 'Abwasser steigt vor Fällen',
  high_import_pressure: 'Importdruck hoch',
  high_current_activity_but_plateauing: 'hohe Aktivität, aber Plateau',
  low_activity_low_growth: 'niedrige Aktivität und wenig Wachstum',
  insufficient_evaluable_weeks: 'zu wenige auswertbare Wochen',
  calibration_warning: 'Kalibrierung unsicher',
  model_not_better_than_persistence: 'nicht besser als Persistenz',
  stale_data: 'Daten zu alt',
  low_confidence: 'Konfidenz zu niedrig',
  manual_approval_required: 'manuelle Prüfung nötig',
};

const formatPct = (value: number | null | undefined): string => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toLocaleString('de-DE', { maximumFractionDigits: 1 })}%`;
};

const formatConfidence = (value: number | null | undefined): string => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  return `${Math.round(value * 100)}%`;
};

const formatDate = (value?: string): string => {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

const reasonLabel = (reason: string): string =>
  REASON_LABELS[reason] ?? reason.replace(/_/g, ' ');

const blockedReasonLabel = (reason: string): string =>
  BLOCKED_REASON_LABELS[reason] ?? reason.replace(/_/g, ' ');

const releaseModeFromPayload = (truth: MediaSpendingTruthPayload): string => {
  if (truth.release_mode || truth.releaseMode || truth.globalDecision) {
    return truth.release_mode ?? truth.releaseMode ?? truth.globalDecision ?? 'blocked';
  }
  if (truth.global_status === 'spendable') return 'approved';
  if (truth.global_status === 'planner_assist') return 'shadow_only';
  return truth.global_status || 'blocked';
};

const budgetCanChangeFromPayload = (truth: MediaSpendingTruthPayload, releaseMode: string): boolean => {
  const explicit =
    truth.can_change_budget ??
    truth.canChangeBudget ??
    truth.budget_can_change ??
    truth.budgetCanChange;
  if (typeof explicit === 'boolean') return explicit;
  return releaseMode === 'approved' && truth.budget_permission === 'approved_with_cap';
};

const approvedDelta = (region: MediaSpendingTruthRegion): number =>
  region.approved_delta_pct ?? region.approvedDeltaPct ?? region.recommended_delta_pct ?? 0;

const shadowDelta = (region: MediaSpendingTruthRegion): number =>
  region.shadow_delta_pct ?? region.shadowDeltaPct ?? region.recommended_delta_pct ?? 0;

const sortRegions = (regions: MediaSpendingTruthRegion[]): MediaSpendingTruthRegion[] =>
  [...regions]
    .sort((a, b) => {
      const approvedGap = Math.abs(approvedDelta(b)) - Math.abs(approvedDelta(a));
      if (Math.abs(approvedGap) > 0.001) return approvedGap;
      const shadowGap = Math.abs(shadowDelta(b)) - Math.abs(shadowDelta(a));
      if (Math.abs(shadowGap) > 0.001) return shadowGap;
      return (b.budget_opportunity_score ?? 0) - (a.budget_opportunity_score ?? 0);
    })
    .slice(0, 5);

interface Props {
  truth?: MediaSpendingTruthPayload | null;
  budgetCanChangeOverride?: boolean;
  calibrationLocked?: boolean;
}

const MediaSpendingTruthPanel: React.FC<Props> = ({
  truth,
  budgetCanChangeOverride,
  calibrationLocked = false,
}) => {
  if (!truth) return null;

  const releaseMode = releaseModeFromPayload(truth);
  const displayReleaseMode =
    calibrationLocked && ['approved', 'limited'].includes(releaseMode)
      ? 'shadow_only'
      : releaseMode;
  const permission = truth.budget_permission || 'blocked';
  const budgetCanChange =
    typeof budgetCanChangeOverride === 'boolean'
      ? budgetCanChangeOverride
      : budgetCanChangeFromPayload(truth, releaseMode);
  const diagnosticOnly =
    calibrationLocked || (truth.diagnostic_only ?? truth.diagnosticOnly ?? !budgetCanChange);
  const regions = sortRegions(truth.regions ?? []);
  const blockedReasons = (truth.blocked_because ?? truth.blockedBecause ?? []).slice(0, 4);
  const gateTrace = truth.gateTrace ?? truth.gate_evaluations ?? truth.gateEvaluations ?? [];
  const attentionGates = gateTrace
    .filter((gate) => ['failed', 'blocked', 'warning', 'insufficient_evidence'].includes(gate.status))
    .slice(0, 4);
  const hasActions = regions.some(
    (region) =>
      region.media_spending_truth !== 'watch_only' ||
      (!calibrationLocked && Math.abs(approvedDelta(region)) > 0) ||
      Math.abs(shadowDelta(region)) > 0,
  );

  return (
    <section className={`media-truth-panel media-truth-${displayReleaseMode}`} data-testid="media-spending-truth-panel">
      <div className="media-truth-head">
        <div>
          <div className="media-truth-kicker">Media-Entscheidungsstatus</div>
          <h3>{STATUS_LABELS[displayReleaseMode] ?? displayReleaseMode.replace(/_/g, ' ')}</h3>
        </div>
        <div className="media-truth-permission">
          <span>
            {calibrationLocked
              ? 'Keine Budgetfreigabe'
              : (PERMISSION_LABELS[permission] ?? permission.replace(/_/g, ' '))}
          </span>
          <b>{budgetCanChange ? 'budget_can_change=true' : 'budget_can_change=false'}</b>
          {diagnosticOnly ? <b>Kalibrierungsfenster</b> : null}
        </div>
      </div>

      <div className="media-truth-release-copy">
        {calibrationLocked
          ? 'Empfehlungen laufen als Shadow-Lauf mit. Ohne GELO-Sell-Out bleibt Echtgeld pausiert.'
          : RELEASE_HELP[releaseMode] ?? 'Empfehlungen werden anhand der aktuellen Gates begrenzt.'}
      </div>

      {releaseMode === 'blocked' ? (
        <div className="media-truth-block-explain">
          <p>
            Die aktuelle Daten- und Entscheidungsqualität reicht nicht für eine geprüfte
            Budgetverschiebung. Regionale Signale werden angezeigt, aber nicht zur
            Aktivierung freigegeben.
          </p>
          {blockedReasons.length ? (
            <div className="media-truth-block-reasons">
              <span>Blockiert durch</span>
              {blockedReasons.map((reason) => (
                <b key={reason}>{blockedReasonLabel(reason)}</b>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {attentionGates.length ? (
        <div className="media-truth-gates">
          <span>Gate-Prüfung</span>
          {attentionGates.map((gate) => (
            <b key={gate.gate} title={gate.explanation ?? gate.reason}>
              {gate.gate.replace(/_/g, ' ')}: {gate.status}
            </b>
          ))}
        </div>
      ) : null}

      <dl className="media-truth-meta">
        <div>
          <dt>Freigabemodus</dt>
          <dd>{displayReleaseMode.replace(/_/g, ' ')}</dd>
        </div>
        <div>
          <dt>Max. Delta</dt>
          <dd>
            {formatPct(
              calibrationLocked ? 0 : (truth.max_approved_delta_pct ?? truth.maxApprovedDeltaPct),
            )}
          </dd>
        </div>
        <div>
          <dt>Gültig bis</dt>
          <dd>{formatDate(truth.valid_until)}</dd>
        </div>
        <div>
          <dt>Datenqualität</dt>
          <dd>{truth.data_quality ?? '—'}</dd>
        </div>
      </dl>

      {hasActions ? (
        <div className="media-truth-regions">
          {regions.map((region) => {
            const reasons = (region.reason_codes ?? []).slice(0, 3);
            const executionStatus = region.execution_status ?? region.executionStatus ?? releaseMode;
            const regionActionLabel = STATUS_LABELS[region.media_spending_truth] ?? region.media_spending_truth.replace(/_/g, ' ');
            const actionLabel =
              executionStatus === 'blocked'
                ? 'Nicht freigegeben'
                : executionStatus === 'shadow_only'
                  ? `Shadow only · ${regionActionLabel}`
                  : regionActionLabel;
            return (
              <article className={`media-truth-region status-${region.media_spending_truth}`} key={region.region_code}>
                <div className="media-truth-region-top">
                  <div>
                    <span className="media-truth-code">{region.region_code}</span>
                    <strong>{region.region_name}</strong>
                  </div>
                  <div className="media-truth-delta-stack">
                    <b className="media-truth-delta">
                      {formatPct(calibrationLocked ? 0 : approvedDelta(region))}
                    </b>
                    <span>freigegeben</span>
                  </div>
                </div>
                <div className="media-truth-action">
                  {actionLabel}
                  {region.manual_approval_required ? ' · manuell' : ''}
                </div>
                <div className="media-truth-delta-pair">
                  <span>Shadow {formatPct(shadowDelta(region))}</span>
                  <span>Freigegeben {formatPct(calibrationLocked ? 0 : approvedDelta(region))}</span>
                </div>
                <div className="media-truth-region-metrics">
                  <span>Sicherheit {formatConfidence(region.confidence)}</span>
                  <span>Cap {formatPct(region.max_delta_pct)}</span>
                </div>
                {reasons.length ? (
                  <div className="media-truth-reasons">
                    {reasons.map((reason) => (
                      <span key={reason}>{reasonLabel(reason)}</span>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="media-truth-empty">
          Keine freigegebene Budgetbewegung. Das Signal bleibt im Watch- oder Blockierstatus.
        </div>
      )}

      {truth.limitations?.length ? (
        <div className="media-truth-limits">
          <span>Limitierungen</span>
          {truth.limitations.slice(0, 3).map((item) => (
            <b key={item}>{item.replace(/_/g, ' ')}</b>
          ))}
        </div>
      ) : null}
    </section>
  );
};

export default MediaSpendingTruthPanel;
