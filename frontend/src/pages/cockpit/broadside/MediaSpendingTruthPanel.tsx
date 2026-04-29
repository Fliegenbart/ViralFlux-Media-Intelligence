import React from 'react';
import type { MediaSpendingTruthPayload, MediaSpendingTruthRegion } from '../types';

const STATUS_LABELS: Record<string, string> = {
  blocked: 'Blockiert',
  watch_only: 'Nur beobachten',
  planner_assist: 'Manuelle Prüfung',
  spendable: 'Freigegeben mit Cap',
  increase_approved: 'Erhöhen freigegeben',
  preposition_approved: 'Früh positionieren',
  maintain: 'Halten',
  cap_or_reduce: 'Deckeln oder senken',
  decrease_approved: 'Senken freigegeben',
};

const PERMISSION_LABELS: Record<string, string> = {
  blocked: 'Keine Budgetfreigabe',
  manual_approval_required: 'Manuelle Freigabe nötig',
  approved_with_cap: 'Freigegeben mit Cap',
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

const sortRegions = (regions: MediaSpendingTruthRegion[]): MediaSpendingTruthRegion[] =>
  [...regions]
    .sort((a, b) => {
      const deltaGap = Math.abs(b.recommended_delta_pct ?? 0) - Math.abs(a.recommended_delta_pct ?? 0);
      if (Math.abs(deltaGap) > 0.001) return deltaGap;
      return (b.budget_opportunity_score ?? 0) - (a.budget_opportunity_score ?? 0);
    })
    .slice(0, 5);

interface Props {
  truth?: MediaSpendingTruthPayload | null;
}

const MediaSpendingTruthPanel: React.FC<Props> = ({ truth }) => {
  if (!truth) return null;

  const status = truth.global_status || 'blocked';
  const permission = truth.budget_permission || 'blocked';
  const regions = sortRegions(truth.regions ?? []);
  const blockedReasons = (truth.blocked_because ?? truth.blockedBecause ?? []).slice(0, 4);
  const failedGates = (truth.gate_evaluations ?? truth.gateEvaluations ?? [])
    .filter((gate) => ['failed', 'blocked'].includes(gate.status))
    .slice(0, 3);
  const hasActions = regions.some(
    (region) =>
      region.media_spending_truth !== 'watch_only' ||
      Math.abs(region.recommended_delta_pct ?? 0) > 0,
  );

  return (
    <section className={`media-truth-panel media-truth-${status}`} data-testid="media-spending-truth-panel">
      <div className="media-truth-head">
        <div>
          <div className="media-truth-kicker">Media-Entscheidungsstatus</div>
          <h3>{STATUS_LABELS[status] ?? status.replace(/_/g, ' ')}</h3>
        </div>
        <div className="media-truth-permission">
          {PERMISSION_LABELS[permission] ?? permission.replace(/_/g, ' ')}
        </div>
      </div>

      {status === 'blocked' ? (
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
          {failedGates.length ? (
            <div className="media-truth-gates">
              {failedGates.map((gate) => (
                <span key={gate.gate} title={gate.explanation}>
                  {gate.gate.replace(/_/g, ' ')}: {gate.status}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <dl className="media-truth-meta">
        <div>
          <dt>Gültig bis</dt>
          <dd>{formatDate(truth.valid_until)}</dd>
        </div>
        <div>
          <dt>Evidenz</dt>
          <dd>{truth.forecast_evidence ?? '—'}</dd>
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
            return (
              <article className={`media-truth-region status-${region.media_spending_truth}`} key={region.region_code}>
                <div className="media-truth-region-top">
                  <div>
                    <span className="media-truth-code">{region.region_code}</span>
                    <strong>{region.region_name}</strong>
                  </div>
                  <b className="media-truth-delta">{formatPct(region.recommended_delta_pct)}</b>
                </div>
                <div className="media-truth-action">
                  {status === 'blocked'
                    ? 'Nicht freigegeben'
                    : STATUS_LABELS[region.media_spending_truth] ?? region.media_spending_truth.replace(/_/g, ' ')}
                  {region.manual_approval_required ? ' · manuell' : ''}
                </div>
                <div className="media-truth-region-metrics">
                  <span>Confidence {formatConfidence(region.confidence)}</span>
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
