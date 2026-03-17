import React from 'react';

import LoadingSkeleton from '../LoadingSkeleton';
import {
  MediaEvidenceResponse,
  PilotReportingResponse,
  PilotSurfaceScope,
  PilotSurfaceStageFilter,
  RegionalAllocationRecommendation,
  RegionalAllocationResponse,
  RegionalCampaignRecommendation,
  RegionalCampaignRecommendationsResponse,
  RegionalForecastPrediction,
  RegionalForecastResponse,
} from '../../types/media';
import {
  businessValidationLabel,
  evidenceTierLabel,
  formatCurrency,
  formatDateTime,
  formatDateShort,
  formatPercent,
  statusTone,
  truthFreshnessLabel,
  truthLayerLabel,
} from './cockpitUtils';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  horizonDays: number;
  onHorizonChange: (value: number) => void;
  scope: PilotSurfaceScope;
  onScopeChange: (value: PilotSurfaceScope) => void;
  stage: PilotSurfaceStageFilter;
  onStageChange: (value: PilotSurfaceStageFilter) => void;
  weeklyBudget: number;
  forecast: RegionalForecastResponse | null;
  allocation: RegionalAllocationResponse | null;
  campaignRecommendations: RegionalCampaignRecommendationsResponse | null;
  evidence: MediaEvidenceResponse | null;
  pilotReporting: PilotReportingResponse | null;
  loading: boolean;
}

type SurfaceState = 'go' | 'watch' | 'no_go' | 'no_model' | 'no_data' | 'watch_only';

const HORIZON_OPTIONS = [3, 5, 7] as const;
const STAGE_OPTIONS: Array<{ key: PilotSurfaceStageFilter; label: string }> = [
  { key: 'ALL', label: 'Alle Stages' },
  { key: 'Activate', label: 'Activate' },
  { key: 'Prepare', label: 'Prepare' },
  { key: 'Watch', label: 'Watch' },
];
const SCOPE_OPTIONS: Array<{ key: PilotSurfaceScope; label: string; copy: string }> = [
  { key: 'forecast', label: 'Forecast', copy: 'Regionenpriorisierung und Wave Readiness' },
  { key: 'allocation', label: 'Allocation', copy: 'Budgetsplit und Spend-Gate' },
  { key: 'recommendation', label: 'Recommendation', copy: 'Produkt-, Keyword- und Kampagnenvorschlag' },
  { key: 'evidence', label: 'Evidence', copy: 'Pilot-Evidence und Readiness' },
];

function normalizeStage(value?: string | null): string {
  return String(value || '').trim().toLowerCase();
}

function matchesStage(value: string | undefined, filter: PilotSurfaceStageFilter): boolean {
  if (filter === 'ALL') return true;
  return normalizeStage(value) === normalizeStage(filter);
}

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const pct = value <= 1 ? value * 100 : value;
  return formatPercent(pct, digits);
}

function stageTone(value?: string | null): React.CSSProperties {
  const normalized = normalizeStage(value);
  if (normalized === 'activate') {
    return {
      background: 'rgba(5, 150, 105, 0.12)',
      color: 'var(--status-success)',
      border: '1px solid rgba(5, 150, 105, 0.22)',
    };
  }
  if (normalized === 'prepare') {
    return {
      background: 'rgba(245, 158, 11, 0.12)',
      color: 'var(--status-warning)',
      border: '1px solid rgba(245, 158, 11, 0.24)',
    };
  }
  return {
    background: 'rgba(10, 132, 255, 0.10)',
    color: 'var(--status-info)',
    border: '1px solid rgba(10, 132, 255, 0.2)',
  };
}

function readinessTone(value?: string | null): React.CSSProperties {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'go') {
    return {
      background: 'rgba(5, 150, 105, 0.12)',
      color: 'var(--status-success)',
      border: '1px solid rgba(5, 150, 105, 0.22)',
    };
  }
  if (normalized === 'watch' || normalized === 'watch_only') {
    return {
      background: 'rgba(245, 158, 11, 0.12)',
      color: 'var(--status-warning)',
      border: '1px solid rgba(245, 158, 11, 0.24)',
    };
  }
  return {
    background: 'rgba(239, 68, 68, 0.12)',
    color: 'var(--status-danger)',
    border: '1px solid rgba(239, 68, 68, 0.24)',
  };
}

function labelForState(state: SurfaceState): string {
  if (state === 'go') return 'GO';
  if (state === 'watch' || state === 'watch_only') return 'WATCH';
  if (state === 'no_model') return 'NO MODEL';
  if (state === 'no_data') return 'NO DATA';
  return 'NO GO';
}

function stateCopy(state: SurfaceState): { title: string; body: string } {
  switch (state) {
    case 'go':
      return {
        title: 'Der aktuelle Scope ist freigabereif.',
        body: 'Die vorhandenen Signale, Budgets und Evidenzen sind konsistent genug, um die aktuelle Empfehlung zu diskutieren und im Zweifel sauber zu erklären.',
      };
    case 'watch':
    case 'watch_only':
      return {
        title: 'Die Lage ist interessant, aber noch beobachtungsnah.',
        body: 'Es gibt eine klare Priorisierung, aber die Datenlage oder das Spend-Gate reicht noch nicht für eine harte Freigabe.',
      };
    case 'no_model':
      return {
        title: 'Für diesen Scope liegt noch kein belastbares Modell vor.',
        body: 'Wechsel den Virus oder den Horizon, bis der regionale Modellpfad für die gewünschte Sicht verfügbar ist.',
      };
    case 'no_data':
      return {
        title: 'Das Modell ist da, aber die Datenlage reicht noch nicht aus.',
        body: 'Die Oberfläche bleibt lesbar, doch für eine belastbare Empfehlung fehlen aktuell verwertbare Signale oder Evidenz.',
      };
    case 'no_go':
    default:
      return {
        title: 'Der Scope bleibt bewusst gesperrt.',
        body: 'Es gibt noch harte Gates oder Blocker. Wir zeigen die Evidenz transparent, aber empfehlen keinen Spend- oder Freigabeschritt.',
      };
  }
}

function uniqueNonEmpty(values: Array<string | null | undefined>): string[] {
  const result: string[] = [];
  values.map((item) => String(item || '').trim()).filter(Boolean).forEach((item) => {
    if (!result.includes(item)) {
      result.push(item);
    }
  });
  return result;
}

function reasonTraceLines(trace?: unknown): string[] {
  if (!trace) return [];
  if (typeof trace === 'string') return trace.trim() ? [trace.trim()] : [];
  if (Array.isArray(trace)) {
    return trace.map((item) => String(item || '').trim()).filter(Boolean);
  }
  const candidate = trace as Record<string, unknown>;
  return uniqueNonEmpty([
    ...(Array.isArray(candidate.why) ? candidate.why : []),
    ...(Array.isArray(candidate.uncertainty) ? candidate.uncertainty : []),
    ...(Array.isArray(candidate.policy_overrides) ? candidate.policy_overrides : []),
    ...(Array.isArray(candidate.budget_notes) ? candidate.budget_notes : []),
    ...(Array.isArray(candidate.guardrails) ? candidate.guardrails : []),
    ...(Array.isArray(candidate.evidence_notes) ? candidate.evidence_notes : []),
    ...(Array.isArray(candidate.product_fit) ? candidate.product_fit : []),
    ...(Array.isArray(candidate.keyword_fit) ? candidate.keyword_fit : []),
  ].map((item) => String(item || '').trim()));
}

function sortPredictions(predictions: RegionalForecastPrediction[]): RegionalForecastPrediction[] {
  return [...predictions].sort((left, right) => {
    const leftRank = Number(left.decision_rank ?? Number.MAX_SAFE_INTEGER);
    const rightRank = Number(right.decision_rank ?? Number.MAX_SAFE_INTEGER);
    if (leftRank !== rightRank) return leftRank - rightRank;
    const rightPriority = Number(right.priority_score || 0);
    const leftPriority = Number(left.priority_score || 0);
    if (rightPriority !== leftPriority) return rightPriority - leftPriority;
    return Number(right.event_probability_calibrated || 0) - Number(left.event_probability_calibrated || 0);
  });
}

function pickLeadPrediction(predictions: RegionalForecastPrediction[]): RegionalForecastPrediction | null {
  return predictions[0] || null;
}

function getCombinedReasons(
  prediction?: RegionalForecastPrediction | null,
  allocationItem?: RegionalAllocationRecommendation | null,
  campaignItem?: RegionalCampaignRecommendation | null,
): string[] {
  return uniqueNonEmpty([
    reasonTraceLines(prediction?.reason_trace)[0],
    prediction?.decision?.explanation_summary,
    reasonTraceLines(allocationItem?.reason_trace)[0],
    allocationItem?.uncertainty_summary,
    reasonTraceLines(campaignItem?.recommendation_rationale)[0],
  ]);
}

function surfaceStateForForecast(forecast: RegionalForecastResponse | null): SurfaceState {
  if (!forecast) return 'no_data';
  if (forecast.status === 'no_model') return 'no_model';
  if (forecast.status === 'no_data' || !forecast.predictions?.length) return 'no_data';
  if (forecast.quality_gate?.overall_passed) return 'go';
  return 'watch';
}

function surfaceStateForAllocation(allocation: RegionalAllocationResponse | null): SurfaceState {
  if (!allocation) return 'no_data';
  if (allocation.status === 'no_model') return 'no_model';
  if (allocation.status === 'no_data' || !allocation.recommendations?.length) return 'no_data';
  if (allocation.summary?.spend_blockers?.length) return 'no_go';
  if (allocation.summary?.spend_enabled) return 'go';
  return 'watch_only';
}

function surfaceStateForRecommendations(recommendations: RegionalCampaignRecommendationsResponse | null): SurfaceState {
  if (!recommendations) return 'no_data';
  if (recommendations.status === 'no_model') return 'no_model';
  if (recommendations.status === 'no_data' || !recommendations.recommendations?.length) return 'no_data';
  if (recommendations.summary?.ready_recommendations && !recommendations.summary?.guarded_recommendations) return 'go';
  if (recommendations.summary?.guarded_recommendations) return 'watch_only';
  return 'watch';
}

function surfaceStateForEvidence(
  evidence: MediaEvidenceResponse | null,
  pilotReporting: PilotReportingResponse | null,
): SurfaceState {
  const truthCoverage = evidence?.truth_coverage;
  const businessValidation = evidence?.business_validation;
  if (!evidence && !pilotReporting) return 'no_data';
  if (!truthCoverage?.coverage_weeks && !pilotReporting?.summary?.total_recommendations) return 'no_data';
  if (businessValidation?.validated_for_budget_activation) return 'go';
  if (businessValidation?.validation_status && businessValidation.validation_status !== 'pending_truth_connection') return 'watch_only';
  return 'watch';
}

function sectionStateTone(state: SurfaceState): React.CSSProperties {
  if (state === 'go') return readinessTone('go');
  if (state === 'watch' || state === 'watch_only') return readinessTone('watch');
  if (state === 'no_model' || state === 'no_data') {
    return {
      background: 'rgba(59, 130, 246, 0.08)',
      color: 'var(--accent-violet)',
      border: '1px solid rgba(59, 130, 246, 0.20)',
    };
  }
  return readinessTone('no_go');
}

const PilotSurface: React.FC<Props> = ({
  virus,
  onVirusChange,
  horizonDays,
  onHorizonChange,
  scope,
  onScopeChange,
  stage,
  onStageChange,
  weeklyBudget,
  forecast,
  allocation,
  campaignRecommendations,
  evidence,
  pilotReporting,
  loading,
}) => {
  const forecastRows = sortPredictions(forecast?.predictions || []).filter((item) => matchesStage(item.decision_label, stage));
  const allocationRows = (allocation?.recommendations || []).filter((item) => matchesStage(String(item.recommended_activation_level || item.decision_label || ''), stage));
  const campaignRows = (campaignRecommendations?.recommendations || []).filter((item) => matchesStage(item.activation_level, stage));
  const leadPrediction = pickLeadPrediction(forecastRows) || pickLeadPrediction(sortPredictions(forecast?.predictions || []));
  const leadAllocation = allocationRows[0] || allocation?.recommendations?.[0] || null;
  const leadCampaign = campaignRows[0] || campaignRecommendations?.recommendations?.[0] || null;
  const leadReasons = getCombinedReasons(leadPrediction, leadAllocation, leadCampaign).slice(0, 3);

  const forecastState = surfaceStateForForecast(forecast);
  const allocationState = surfaceStateForAllocation(allocation);
  const recommendationState = surfaceStateForRecommendations(campaignRecommendations);
  const evidenceState = surfaceStateForEvidence(evidence, pilotReporting);

  const scopeState: SurfaceState = ({
    forecast: forecastState,
    allocation: allocationState,
    recommendation: recommendationState,
    evidence: evidenceState,
  } as Record<PilotSurfaceScope, SurfaceState>)[scope];

  const topRegions = forecastRows.slice(0, 3);
  const campaignPreview = campaignRows.slice(0, 3);
  const regionEvidencePreview = pilotReporting?.region_evidence_view?.slice(0, 4) || [];
  const beforeAfterPreview = [...(pilotReporting?.before_after_comparison || [])]
    .filter((item) => item.delta_pct != null)
    .sort((left, right) => Number(right.delta_pct || 0) - Number(left.delta_pct || 0))
    .slice(0, 4);

  const leadStage = leadCampaign?.activation_level || leadAllocation?.recommended_activation_level || leadPrediction?.decision_label || 'Watch';
  const leadRegion = leadCampaign?.region_name || leadAllocation?.bundesland_name || leadPrediction?.bundesland_name || 'Deutschland';
  const leadBudget = leadCampaign?.suggested_budget_amount || leadAllocation?.suggested_budget_amount || 0;
  const leadShare = leadAllocation?.suggested_budget_share || leadCampaign?.suggested_budget_share || 0;
  const leadConfidence = leadCampaign?.confidence ?? leadAllocation?.confidence ?? leadPrediction?.decision?.forecast_confidence ?? null;
  const leadUncertainty = leadPrediction?.uncertainty_summary || leadAllocation?.uncertainty_summary || 'Noch keine Unsicherheitserklärung verfügbar.';
  const topAction = reasonTraceLines(leadCampaign?.recommendation_rationale)[0]
    || reasonTraceLines(leadAllocation?.reason_trace)[0]
    || leadPrediction?.decision?.explanation_summary
    || 'Die stärksten Regionen werden jetzt priorisiert und mit klaren Budgetsignalen übersetzt.';

  const pilotKpi = pilotReporting?.pilot_kpi_summary || {};
  const pilotSummary = pilotReporting?.summary || {};
  const reportingWindow = pilotReporting?.reporting_window || {};
  const truthCoverage = evidence?.truth_coverage;
  const businessValidation = evidence?.business_validation;
  const forecastMonitoring = evidence?.forecast_monitoring;

  if (loading && !forecast && !allocation && !campaignRecommendations && !evidence && !pilotReporting) {
    return (
      <div className="card" style={{ padding: 28 }}>
        <LoadingSkeleton lines={8} />
      </div>
    );
  }

  const showEmptyBanner = scopeState !== 'go';
  const emptyState = stateCopy(scopeState);
  const canSwitchToRSV = virus !== 'RSV A';

  const renderOperationalScope = () => {
    if (scope === 'forecast') {
      return (
        <div className="ops-table-wrap">
          <table className="ops-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Region</th>
                <th>Stage</th>
                <th>Wave Chance</th>
                <th>Priority</th>
                <th>Confidence</th>
                <th>Why now</th>
              </tr>
            </thead>
            <tbody>
              {forecastRows.length > 0 ? forecastRows.slice(0, 6).map((item) => (
                <tr key={item.bundesland}>
                  <td>{item.decision_rank ?? item.rank ?? '-'}</td>
                  <td>
                    <strong>{item.bundesland_name}</strong>
                    <div className="ops-row-meta">{item.bundesland}</div>
                  </td>
                  <td>
                    <span style={{ ...stageTone(item.decision_label), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 800 }}>
                      {String(item.decision_label || 'Watch')}
                    </span>
                  </td>
                  <td>{formatFractionPercent(item.event_probability_calibrated, 0)}</td>
                  <td>{(item.priority_score ?? 0).toFixed(2)}</td>
                  <td>{formatFractionPercent(item.decision?.forecast_confidence, 0)}</td>
                  <td>{reasonTraceLines(item.reason_trace)[0] || item.decision?.explanation_summary || '-'}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={7} className="ops-table-empty">Keine Regionen im aktuellen Filter.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      );
    }

    if (scope === 'allocation') {
      return (
        <>
          <div className="ops-table-wrap">
            <table className="ops-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Region</th>
                  <th>Activation</th>
                  <th>Budget</th>
                  <th>Share</th>
                  <th>Confidence</th>
                  <th>Spend Gate</th>
                </tr>
              </thead>
              <tbody>
                {allocationRows.length > 0 ? allocationRows.slice(0, 6).map((item) => (
                  <tr key={item.bundesland}>
                    <td>{item.priority_rank ?? '-'}</td>
                    <td>
                      <strong>{item.bundesland_name}</strong>
                      <div className="ops-row-meta">{item.products?.join(', ') || 'GELO Portfolio'}</div>
                    </td>
                    <td>
                      <span style={{ ...stageTone(item.recommended_activation_level), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 800 }}>
                        {String(item.recommended_activation_level || 'Watch')}
                      </span>
                    </td>
                    <td>{formatCurrency(item.suggested_budget_amount)}</td>
                    <td>{formatFractionPercent(item.suggested_budget_share, 1)}</td>
                    <td>{formatFractionPercent(item.confidence, 0)}</td>
                    <td>
                      <span style={{ ...statusTone(item.spend_gate_status), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 700 }}>
                        {item.spend_gate_status || 'observe_only'}
                      </span>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={7} className="ops-table-empty">Keine Budgetempfehlungen im aktuellen Filter.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="soft-panel" style={{ padding: 16, marginTop: 16 }}>
            <div className="section-kicker">Budget Summary</div>
            <div className="review-chip-row" style={{ marginTop: 10 }}>
              <span className="step-chip">Budget {formatCurrency(allocation?.summary?.total_budget_allocated)}</span>
              <span className="step-chip">Share {formatFractionPercent(allocation?.summary?.budget_share_total, 1)}</span>
              <span className="step-chip">Spend {allocation?.summary?.spend_enabled ? 'enabled' : 'blocked'}</span>
            </div>
          </div>
        </>
      );
    }

    if (scope === 'recommendation') {
      return (
        <div className="ops-recommendation-grid">
          {campaignPreview.length > 0 ? campaignPreview.map((item) => (
            <article key={`${item.region}-${item.recommended_product_cluster.cluster_key}`} className="card" style={{ padding: 20, display: 'grid', gap: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                <div>
                  <div className="section-kicker">Priority #{item.priority_rank}</div>
                  <h3 style={{ margin: '8px 0 0', fontSize: 20, color: 'var(--text-primary)' }}>{item.region_name}</h3>
                  <div style={{ marginTop: 6, fontSize: 13, color: 'var(--text-muted)' }}>
                    {item.recommended_product_cluster.label} · {item.recommended_keyword_cluster.label}
                  </div>
                </div>
                <span style={{ ...stageTone(item.activation_level), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 800 }}>
                  {String(item.activation_level || 'Watch')}
                </span>
              </div>
              <div className="metric-strip">
                <div className="metric-box">
                  <span>Budget</span>
                  <strong>{formatCurrency(item.suggested_budget_amount)}</strong>
                </div>
                <div className="metric-box">
                  <span>Share</span>
                  <strong>{formatFractionPercent(item.suggested_budget_share, 1)}</strong>
                </div>
                <div className="metric-box">
                  <span>Confidence</span>
                  <strong>{formatFractionPercent(item.confidence, 0)}</strong>
                </div>
                <div className="metric-box">
                  <span>Evidence</span>
                  <strong>{item.evidence_class}</strong>
                </div>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                <span style={{ ...statusTone(item.spend_guardrail_status), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 700 }}>
                  {item.spend_guardrail_status}
                </span>
                {(item.keywords || []).slice(0, 4).map((keyword) => (
                  <span key={keyword} className="step-chip">{keyword}</span>
                ))}
              </div>
              <div className="soft-panel" style={{ padding: 14, display: 'grid', gap: 10 }}>
                <div className="ops-panel-title">Warum</div>
                <ul className="ops-rationale-list">
                  {reasonTraceLines(item.recommendation_rationale).slice(0, 3).map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              </div>
            </article>
          )) : (
            <div className="soft-panel" style={{ padding: 18, color: 'var(--text-secondary)' }}>
              Für den aktuellen Filter gibt es noch keine konkrete Campaign Recommendation.
            </div>
          )}
        </div>
      );
    }

    return (
      <div style={{ display: 'grid', gap: 16 }}>
        <div className="metric-strip">
          <div className="metric-box">
            <span>Top Evidenz-Treiber</span>
            <strong>{pilotReporting?.region_evidence_view?.[0]?.region_name || 'keine Evidenz'}</strong>
          </div>
          <div className="metric-box">
            <span>Hit Rate</span>
            <strong>{formatFractionPercent(pilotKpi.hit_rate?.value, 0)}</strong>
          </div>
          <div className="metric-box">
            <span>Lead Time</span>
            <strong>{pilotKpi.early_warning_lead_time_days?.median != null ? `${pilotKpi.early_warning_lead_time_days.median.toFixed(1)}T` : '-'}</strong>
          </div>
          <div className="metric-box">
            <span>Agreement</span>
            <strong>{formatFractionPercent(pilotKpi.agreement_with_outcome_signals?.value, 0)}</strong>
          </div>
        </div>
        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
          {regionEvidencePreview.length > 0 ? regionEvidencePreview.map((item) => (
            <div key={item.region_code} className="soft-panel" style={{ padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                <div>
                  <div className="section-kicker">{item.region_code}</div>
                  <div style={{ marginTop: 6, fontSize: 16, fontWeight: 800 }}>{item.region_name}</div>
                </div>
                <span className="step-chip">{item.dominant_evidence_status || 'observational'}</span>
              </div>
              <div style={{ marginTop: 10, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {item.recommendations || 0} Empfehlungen · {item.activations || 0} Aktivierungen · Hit Rate {formatFractionPercent(item.hit_rate, 0)}
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                Top-Produkte: {(item.top_products || []).join(' / ') || 'keine'}
              </div>
            </div>
          )) : (
            <div className="soft-panel" style={{ padding: 18, color: 'var(--text-secondary)' }}>
              Noch keine Regionen-Evidence verfügbar.
            </div>
          )}
        </div>
        <div className="soft-panel" style={{ padding: 16 }}>
          <div className="ops-panel-title">Before / After</div>
          <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
            {beforeAfterPreview.length > 0 ? beforeAfterPreview.map((item) => (
              <div key={item.comparison_id || `${item.region_code}-${item.product}`} className="evidence-row">
                <span>
                  {item.region_name} · {item.primary_metric || 'metric'}
                  <div className="ops-row-meta">{item.product || 'Produkt'}</div>
                </span>
                <strong>
                  {item.delta_pct != null ? `${item.delta_pct > 0 ? '+' : ''}${item.delta_pct.toFixed(1)}%` : '-'}
                </strong>
              </div>
            )) : (
              <div style={{ color: 'var(--text-secondary)' }}>Noch keine Before/After-Vergleiche verfügbar.</div>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="page-stack">
      <section className="context-filter-rail">
        <div className="section-heading">
          <span className="section-kicker">PEIX / GELO Pilot Output Surface</span>
          <h1 className="section-title">What should we do now?</h1>
          <p className="section-copy">
            Eine management-taugliche Sicht auf Forecast, Allocation, Recommendation und Pilot Evidence.
          </p>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {SCOPE_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => onScopeChange(option.key)}
              className={`tab-chip ${scope === option.key ? 'active' : ''}`}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <div className="review-chip-row" style={{ width: '100%' }}>
            {['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A'].map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onVirusChange(option)}
                className={`tab-chip ${option === virus ? 'active' : ''}`}
              >
                {option}
              </button>
            ))}
          </div>
          <div className="review-chip-row" style={{ width: '100%' }}>
            {HORIZON_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onHorizonChange(option)}
                className={`tab-chip ${option === horizonDays ? 'active' : ''}`}
              >
                {option} Tage
              </button>
            ))}
          </div>
          <div className="review-chip-row" style={{ width: '100%' }}>
            {STAGE_OPTIONS.map((option) => (
              <button
                key={option.key}
                type="button"
                onClick={() => onStageChange(option.key)}
                className={`tab-chip ${option.key === stage ? 'active' : ''}`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="review-chip-row">
          <span className="step-chip">Budget {formatCurrency(weeklyBudget)}</span>
          <span className="step-chip">Forecast {formatDateTime(forecast?.generated_at)}</span>
          <span className="step-chip">Allocation {formatDateTime(allocation?.generated_at)}</span>
          <span className="step-chip">Recommendations {formatDateTime(campaignRecommendations?.generated_at)}</span>
          <span className="step-chip">Pilot Evidence {formatDateTime(pilotReporting?.generated_at)}</span>
        </div>
      </section>

      {showEmptyBanner && (
        <section className="card" style={{ padding: 24, border: '1px solid rgba(148, 163, 184, 0.24)' }}>
          <div className="section-heading" style={{ gap: 8 }}>
            <span
              style={{
                ...sectionStateTone(scopeState),
                padding: '6px 10px',
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 800,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                width: 'fit-content',
              }}
            >
              {labelForState(scopeState)}
            </span>
            <h2 className="subsection-title" style={{ margin: 0 }}>{emptyState.title}</h2>
            <p className="subsection-copy" style={{ margin: 0 }}>{emptyState.body}</p>
          </div>
          <div className="review-chip-row" style={{ marginTop: 12 }}>
            <span className="step-chip">Scope {SCOPE_OPTIONS.find((item) => item.key === scope)?.label}</span>
            <span className="step-chip">Virus {virus}</span>
            <span className="step-chip">Horizon {horizonDays} Tage</span>
            <span className="step-chip">Stage {stage === 'ALL' ? 'alle' : stage}</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 14 }}>
            {canSwitchToRSV && (
              <button className="media-button secondary" type="button" onClick={() => onVirusChange('RSV A')}>
                Auf RSV A wechseln
              </button>
            )}
            {horizonDays !== 7 && (
              <button className="media-button secondary" type="button" onClick={() => onHorizonChange(7)}>
                Auf 7 Tage wechseln
              </button>
            )}
            {scope !== 'forecast' && (
              <button className="media-button secondary" type="button" onClick={() => onScopeChange('forecast')}>
                Forecast ansehen
              </button>
            )}
            {scope !== 'recommendation' && (
              <button className="media-button secondary" type="button" onClick={() => onScopeChange('recommendation')}>
                Recommendation ansehen
              </button>
            )}
            {scope !== 'evidence' && (
              <button className="media-button secondary" type="button" onClick={() => onScopeChange('evidence')}>
                Evidence ansehen
              </button>
            )}
          </div>
        </section>
      )}

      <section className="card decision-header hero-card" style={{ padding: 32 }}>
        <div className="hero-grid" style={{ gridTemplateColumns: '1.45fr 0.95fr' }}>
          <div className="hero-main">
            <div className="hero-status-row">
              <span
                style={{
                  ...stageTone(leadStage),
                  padding: '8px 12px',
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                }}
              >
                {String(leadStage || 'Watch')}
              </span>
              <span className="campaign-confidence-chip">Scope {SCOPE_OPTIONS.find((item) => item.key === scope)?.label}</span>
              <span className="campaign-confidence-chip">{leadRegion}</span>
            </div>

            <div className="section-heading" style={{ gap: 12 }}>
              <h1 className="hero-title" style={{ margin: 0 }}>
                {String(leadStage || 'Watch')} {leadRegion} für PEIX / GELO.
              </h1>
              <p className="hero-context" style={{ margin: 0 }}>
                {topAction}
              </p>
              <p className="hero-copy" style={{ margin: 0 }}>
                Budget {formatCurrency(leadBudget)} · Share {formatFractionPercent(leadShare, 1)} · Confidence {formatFractionPercent(leadConfidence, 0)}.
              </p>
            </div>

            <div className="review-chip-row">
              <span className="step-chip">Forecast {labelForState(forecastState)}</span>
              <span className="step-chip">Allocation {labelForState(allocationState)}</span>
              <span className="step-chip">Recommendation {labelForState(recommendationState)}</span>
              <span className="step-chip">Evidence {labelForState(evidenceState)}</span>
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
              {scope !== 'forecast' && (
                <button className="media-button" type="button" onClick={() => onScopeChange('forecast')}>
                  Regionen prüfen
                </button>
              )}
              {scope !== 'allocation' && (
                <button className="media-button secondary" type="button" onClick={() => onScopeChange('allocation')}>
                  Budgetsplit prüfen
                </button>
              )}
              {scope !== 'recommendation' && (
                <button className="media-button secondary" type="button" onClick={() => onScopeChange('recommendation')}>
                  Empfehlungen öffnen
                </button>
              )}
              {scope !== 'evidence' && (
                <button className="media-button secondary" type="button" onClick={() => onScopeChange('evidence')}>
                  Evidenz öffnen
                </button>
              )}
            </div>
          </div>

          <div className="soft-panel" style={{ padding: 22, display: 'grid', gap: 14 }}>
            <div className="section-kicker">Executive Summary</div>
            <div className="ops-summary-grid">
              <div className="metric-box">
                <span>Lead Region</span>
                <strong>{leadRegion}</strong>
              </div>
              <div className="metric-box">
                <span>Lead Stage</span>
                <strong>{String(leadStage || 'Watch')}</strong>
              </div>
              <div className="metric-box">
                <span>Budget Spike</span>
                <strong>{formatCurrency(leadBudget)}</strong>
              </div>
              <div className="metric-box">
                <span>Uncertainty</span>
                <strong>{leadUncertainty}</strong>
              </div>
            </div>
            <div className="soft-panel" style={{ padding: 14, display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Why this matters now</div>
              <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {leadReasons[0] || 'Die Top-Regionen und Budgets sind in der aktuellen Lage klar priorisierbar.'}
              </div>
              {leadReasons.length > 1 && (
                <ul className="ops-rationale-list" style={{ marginTop: 4 }}>
                  {leadReasons.slice(1).map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gap: 14, marginTop: 18, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
          {topRegions.length > 0 ? topRegions.map((item) => (
            <div key={item.bundesland} className="soft-panel" style={{ padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                <div>
                  <div className="section-kicker"># {item.decision_rank ?? item.rank ?? '-'}</div>
                  <div style={{ marginTop: 6, fontSize: 16, fontWeight: 800 }}>{item.bundesland_name}</div>
                </div>
                <span className="step-chip" style={{ alignSelf: 'flex-start' }}>{String(item.decision_label || 'Watch')}</span>
              </div>
              <div style={{ marginTop: 10, fontSize: 13, color: 'var(--text-secondary)' }}>
                Wave chance {formatFractionPercent(item.event_probability_calibrated, 0)} · Confidence {formatFractionPercent(item.decision?.forecast_confidence, 0)}
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                {reasonTraceLines(item.reason_trace)[0] || item.uncertainty_summary || item.decision?.explanation_summary || 'Regionale Priorisierung aus Forecast und Decision Layer.'}
              </div>
            </div>
          )) : (
            <div className="soft-panel" style={{ padding: 16, color: 'var(--text-secondary)' }}>
              Noch keine Top-Regionen für den aktuellen Filter verfügbar.
            </div>
          )}
        </div>
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading" style={{ gap: 6 }}>
          <span className="section-kicker">Operational Recommendations</span>
          <h2 className="subsection-title">Focus lens: {SCOPE_OPTIONS.find((item) => item.key === scope)?.label}</h2>
          <p className="subsection-copy">
            Die Oberfläche bleibt bewusst nah an den bestehenden Backend-Outputs und verändert nur die Lesart für PEIX / GELO.
          </p>
        </div>
        <div className="review-chip-row" style={{ marginTop: 12 }}>
          <span className="step-chip" style={readinessTone(forecastState === 'go' ? 'go' : forecastState === 'watch' ? 'watch' : 'no_go')}>
            Forecast {labelForState(forecastState)}
          </span>
          <span className="step-chip" style={readinessTone(allocationState === 'go' ? 'go' : allocationState === 'watch' || allocationState === 'watch_only' ? 'watch' : 'no_go')}>
            Allocation {labelForState(allocationState)}
          </span>
          <span className="step-chip" style={readinessTone(recommendationState === 'go' ? 'go' : recommendationState === 'watch' || recommendationState === 'watch_only' ? 'watch' : 'no_go')}>
            Recommendation {labelForState(recommendationState)}
          </span>
        </div>
        <div style={{ marginTop: 18 }}>
          {renderOperationalScope()}
        </div>
      </section>

      <section className="card subsection-card" style={{ padding: 24 }}>
        <div className="section-heading" style={{ gap: 6 }}>
          <span className="section-kicker">Pilot Evidence / Readiness</span>
          <h2 className="subsection-title">What can PEIX safely show GELO?</h2>
          <p className="subsection-copy">
            Evidence bleibt sichtbar, aber die Oberfläche spricht in Business-Entscheidungen statt in Model-Terms.
          </p>
        </div>

        <div className="review-chip-row" style={{ marginTop: 12 }}>
          <span className="step-chip" style={readinessTone(forecastState === 'go' ? 'go' : 'watch')}>
            Forecast {labelForState(forecastState)}
          </span>
          <span className="step-chip" style={readinessTone(allocationState === 'go' ? 'go' : 'watch')}>
            Allocation {labelForState(allocationState)}
          </span>
          <span className="step-chip" style={readinessTone(recommendationState === 'go' ? 'go' : 'watch')}>
            Recommendation {labelForState(recommendationState)}
          </span>
          <span className="step-chip" style={readinessTone(evidenceState === 'go' ? 'go' : evidenceState === 'watch_only' || evidenceState === 'watch' ? 'watch' : 'no_go')}>
            Evidence {labelForState(evidenceState)}
          </span>
        </div>

        <div className="metric-strip" style={{ marginTop: 18 }}>
          <div className="metric-box">
            <span>Recommendations</span>
            <strong>{pilotSummary.total_recommendations ?? 0}</strong>
          </div>
          <div className="metric-box">
            <span>Activated</span>
            <strong>{pilotSummary.activated_recommendations ?? 0}</strong>
          </div>
          <div className="metric-box">
            <span>Regions covered</span>
            <strong>{pilotSummary.regions_covered ?? 0}</strong>
          </div>
          <div className="metric-box">
            <span>With evidence</span>
            <strong>{pilotSummary.comparisons_with_evidence ?? 0}</strong>
          </div>
        </div>

        <div style={{ display: 'grid', gap: 14, marginTop: 18, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
          <div className="soft-panel" style={{ padding: 16 }}>
            <div className="section-kicker">Pilot KPIs</div>
            <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
              <div className="evidence-row">
                <span>Hit rate</span>
                <strong>{formatFractionPercent(pilotKpi.hit_rate?.value, 0)}</strong>
              </div>
              <div className="evidence-row">
                <span>Lead time</span>
                <strong>{pilotKpi.early_warning_lead_time_days?.median != null ? `${pilotKpi.early_warning_lead_time_days.median.toFixed(1)} Tage` : '-'}</strong>
              </div>
              <div className="evidence-row">
                <span>Correct prioritizations</span>
                <strong>{formatFractionPercent(pilotKpi.share_of_correct_regional_prioritizations?.value, 0)}</strong>
              </div>
              <div className="evidence-row">
                <span>Agreement</span>
                <strong>{formatFractionPercent(pilotKpi.agreement_with_outcome_signals?.value, 0)}</strong>
              </div>
            </div>
          </div>

          <div className="soft-panel" style={{ padding: 16 }}>
            <div className="section-kicker">Readiness context</div>
            <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
              <div className="evidence-row">
                <span>Forecast gate</span>
                <strong>{forecast?.quality_gate?.overall_passed ? 'GO' : 'WATCH'}</strong>
              </div>
              <div className="evidence-row">
                <span>Truth coverage</span>
                <strong>{truthLayerLabel(truthCoverage)}</strong>
              </div>
              <div className="evidence-row">
                <span>Truth freshness</span>
                <strong>{truthFreshnessLabel(truthCoverage?.truth_freshness_state)}</strong>
              </div>
              <div className="evidence-row">
                <span>Business gate</span>
                <strong>{businessValidationLabel(businessValidation?.validation_status)}</strong>
              </div>
              <div className="evidence-row">
                <span>Evidence tier</span>
                <strong>{evidenceTierLabel(businessValidation?.evidence_tier)}</strong>
              </div>
              <div className="evidence-row">
                <span>Decision scope</span>
                <strong>{businessValidation?.decision_scope || '-'}</strong>
              </div>
            </div>
          </div>

          <div className="soft-panel" style={{ padding: 16 }}>
            <div className="section-kicker">Data window</div>
            <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
              <div className="evidence-row">
                <span>Reporting window</span>
                <strong>{formatDateShort(reportingWindow.start)} - {formatDateShort(reportingWindow.end)}</strong>
              </div>
              <div className="evidence-row">
                <span>Lookback</span>
                <strong>{reportingWindow.lookback_weeks ?? 26} Wochen</strong>
              </div>
              <div className="evidence-row">
                <span>Methodik</span>
                <strong>{pilotReporting?.methodology?.version || 'pilot_reporting_v1'}</strong>
              </div>
              <div className="evidence-row">
                <span>Forecast monitored</span>
                <strong>{forecastMonitoring?.forecast_readiness || '-'}</strong>
              </div>
              <div className="evidence-row">
                <span>Model version</span>
                <strong>{evidence?.model_lineage?.model_version || forecast?.model_version || '-'}</strong>
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gap: 14, marginTop: 18 }}>
          <div className="soft-panel" style={{ padding: 16 }}>
            <div className="section-kicker">Region evidence</div>
            <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
              {regionEvidencePreview.length > 0 ? regionEvidencePreview.map((item) => (
                <div key={item.region_code} className="evidence-row">
                  <span>
                    {item.region_name}
                    <div className="ops-row-meta">
                      {item.top_products?.join(' / ') || 'keine Produktspur'} · {item.recommendations || 0} Empfehlungen
                    </div>
                  </span>
                  <strong>
                    Hit {formatFractionPercent(item.hit_rate, 0)} · Lead {item.avg_lead_time_days != null ? `${item.avg_lead_time_days.toFixed(1)}T` : '-'}
                  </strong>
                </div>
              )) : (
                <div style={{ color: 'var(--text-secondary)' }}>Noch keine Regionsevidence verfügbar.</div>
              )}
            </div>
          </div>

          <div className="soft-panel" style={{ padding: 16 }}>
            <div className="section-kicker">Before / After comparison</div>
            <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
              {beforeAfterPreview.length > 0 ? beforeAfterPreview.map((item) => (
                <div key={item.comparison_id || `${item.region_code}-${item.product}`} className="evidence-row">
                  <span>
                    {item.region_name} · {item.primary_metric || 'metric'}
                    <div className="ops-row-meta">{item.product || 'Produkt'}</div>
                  </span>
                  <strong>
                    {item.delta_pct != null ? `${item.delta_pct > 0 ? '+' : ''}${item.delta_pct.toFixed(1)}%` : '-'} · {item.outcome_support_status || 'unknown'}
                  </strong>
                </div>
              )) : (
                <div style={{ color: 'var(--text-secondary)' }}>Noch keine Before/After-Deltas verfügbar.</div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default PilotSurface;
