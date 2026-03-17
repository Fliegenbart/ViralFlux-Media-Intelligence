import React, { useEffect, useState } from 'react';

import {
  RegionalAllocationRecommendation,
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalDecisionReasonTrace,
  RegionalForecastPrediction,
  RegionalForecastResponse,
} from '../../types/media';
import {
  formatCurrency,
  formatDateTime,
  formatPercent,
  VIRUS_OPTIONS,
} from './cockpitUtils';

interface Props {
  virus: string;
  onVirusChange: (value: string) => void;
  horizonDays: number;
  onHorizonChange: (value: number) => void;
  weeklyBudget: number;
  forecast: RegionalForecastResponse | null;
  allocation: RegionalAllocationResponse | null;
  campaignRecommendations: RegionalCampaignRecommendationsResponse | null;
  loading: boolean;
  onOpenRegions: (regionCode?: string) => void;
  onOpenCampaigns: () => void;
  onOpenEvidence: () => void;
}

const HORIZON_OPTIONS = [3, 5, 7];
const REGION_FILTER_ALL = 'ALL';
const STAGE_FILTER_ALL = 'ALL';

function normalizeStage(value?: string | null): string {
  return String(value || '').trim().toLowerCase();
}

function displayStage(value?: string | null): string {
  const normalized = normalizeStage(value);
  if (normalized === 'activate') return 'Activate';
  if (normalized === 'prepare') return 'Prepare';
  if (normalized === 'watch') return 'Watch';
  return value ? String(value) : 'Watch';
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

function statusTone(value?: string | null): React.CSSProperties {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized.includes('release') || normalized === 'ready') {
    return {
      background: 'rgba(5, 150, 105, 0.12)',
      color: 'var(--status-success)',
      border: '1px solid rgba(5, 150, 105, 0.22)',
    };
  }
  if (normalized.includes('review') || normalized.includes('guarded')) {
    return {
      background: 'rgba(245, 158, 11, 0.12)',
      color: 'var(--status-warning)',
      border: '1px solid rgba(245, 158, 11, 0.24)',
    };
  }
  if (normalized.includes('block')) {
    return {
      background: 'rgba(239, 68, 68, 0.12)',
      color: 'var(--status-danger)',
      border: '1px solid rgba(239, 68, 68, 0.24)',
    };
  }
  return {
    background: 'rgba(148, 163, 184, 0.12)',
    color: 'var(--text-secondary)',
    border: '1px solid rgba(148, 163, 184, 0.2)',
  };
}

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const pct = value <= 1 ? value * 100 : value;
  return formatPercent(pct, digits);
}

function formatScore(value?: number | null, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '-';
  return value.toFixed(digits);
}

function reasonTraceLines(trace?: RegionalDecisionReasonTrace | Record<string, unknown> | string[] | string | null): string[] {
  if (!trace) return [];
  if (typeof trace === 'string') return trace.trim() ? [trace] : [];
  if (Array.isArray(trace)) {
    return trace
      .map((item) => String(item || '').trim())
      .filter(Boolean);
  }
  const maybeTrace = trace as Partial<RegionalDecisionReasonTrace> & Record<string, unknown>;
  return [
    ...(Array.isArray(maybeTrace.why) ? maybeTrace.why : []),
    ...(Array.isArray(maybeTrace.uncertainty) ? maybeTrace.uncertainty : []),
    ...(Array.isArray(maybeTrace.policy_overrides) ? maybeTrace.policy_overrides : []),
  ].map((item) => String(item || '').trim()).filter(Boolean);
}

function stageMatchesFilter(value: string | undefined, filter: string): boolean {
  if (filter === STAGE_FILTER_ALL) return true;
  return normalizeStage(value) === normalizeStage(filter);
}

function regionMatchesFilter(regionCode: string | undefined, filter: string): boolean {
  if (filter === REGION_FILTER_ALL) return true;
  return String(regionCode || '').toUpperCase() === filter;
}

function sortByDecisionRank(items: RegionalForecastPrediction[]): RegionalForecastPrediction[] {
  return [...items].sort((left, right) => {
    const leftRank = Number(left.decision_rank ?? Number.MAX_SAFE_INTEGER);
    const rightRank = Number(right.decision_rank ?? Number.MAX_SAFE_INTEGER);
    if (leftRank !== rightRank) return leftRank - rightRank;
    const rightPriority = Number(right.priority_score || 0);
    const leftPriority = Number(left.priority_score || 0);
    if (rightPriority !== leftPriority) return rightPriority - leftPriority;
    return Number(right.event_probability_calibrated || 0) - Number(left.event_probability_calibrated || 0);
  });
}

function focusedReasonText(
  prediction?: RegionalForecastPrediction | null,
  allocationItem?: RegionalAllocationRecommendation | null,
): string {
  return String(
    prediction?.uncertainty_summary
    || allocationItem?.uncertainty_summary
    || prediction?.decision?.uncertainty_summary
    || 'Noch keine Unsicherheitserklärung verfügbar.',
  );
}

const OperationalDashboard: React.FC<Props> = ({
  virus,
  onVirusChange,
  horizonDays,
  onHorizonChange,
  weeklyBudget,
  forecast,
  allocation,
  campaignRecommendations,
  loading,
  onOpenRegions,
  onOpenCampaigns,
  onOpenEvidence,
}) => {
  const [selectedRegion, setSelectedRegion] = useState<string>(REGION_FILTER_ALL);
  const [selectedStage, setSelectedStage] = useState<string>(STAGE_FILTER_ALL);

  const regionOptions = (forecast?.predictions || []).map((item) => ({
    code: item.bundesland,
    name: item.bundesland_name,
  }));

  useEffect(() => {
    const availableRegionCodes = new Set(regionOptions.map((item) => item.code));
    if (selectedRegion !== REGION_FILTER_ALL && !availableRegionCodes.has(selectedRegion)) {
      setSelectedRegion(REGION_FILTER_ALL);
    }
  }, [regionOptions, selectedRegion]);

  const decisionRanked = sortByDecisionRank(forecast?.predictions || []);
  const stageContextPredictions = decisionRanked.filter((item) => regionMatchesFilter(item.bundesland, selectedRegion));
  const filteredPredictions = decisionRanked.filter((item) => (
    regionMatchesFilter(item.bundesland, selectedRegion)
    && stageMatchesFilter(item.decision_label, selectedStage)
  ));
  const filteredAllocation = (allocation?.recommendations || []).filter((item) => (
    regionMatchesFilter(item.bundesland, selectedRegion)
    && stageMatchesFilter(String(item.recommended_activation_level || item.decision_label || ''), selectedStage)
  ));
  const filteredCampaigns = (campaignRecommendations?.recommendations || []).filter((item) => (
    regionMatchesFilter(item.region, selectedRegion)
    && stageMatchesFilter(item.activation_level, selectedStage)
  ));

  const focusedRegionCode = selectedRegion !== REGION_FILTER_ALL
    ? selectedRegion
    : (filteredPredictions[0]?.bundesland || filteredAllocation[0]?.bundesland || filteredCampaigns[0]?.region || null);
  const focusedPrediction = focusedRegionCode
    ? decisionRanked.find((item) => item.bundesland === focusedRegionCode) || null
    : null;
  const focusedAllocation = focusedRegionCode
    ? (allocation?.recommendations || []).find((item) => item.bundesland === focusedRegionCode) || null
    : null;
  const focusedCampaign = focusedRegionCode
    ? (campaignRecommendations?.recommendations || []).find((item) => item.region === focusedRegionCode) || null
    : null;

  const hasOperationalData = Boolean(
    (forecast?.predictions || []).length
    || (allocation?.recommendations || []).length
    || (campaignRecommendations?.recommendations || []).length,
  );
  const emptyStatus = forecast?.status || allocation?.status || campaignRecommendations?.status;
  const emptyMessage = forecast?.message || allocation?.message || campaignRecommendations?.message;
  const supportedHorizons = forecast?.supported_horizon_days || HORIZON_OPTIONS;
  const activateCount = stageContextPredictions.filter((item) => normalizeStage(item.decision_label) === 'activate').length;
  const prepareCount = stageContextPredictions.filter((item) => normalizeStage(item.decision_label) === 'prepare').length;
  const watchCount = stageContextPredictions.filter((item) => normalizeStage(item.decision_label) === 'watch').length;
  const totalContextRegions = Math.max(stageContextPredictions.length, 1);

  const leadPrediction = filteredPredictions[0] || decisionRanked[0] || null;
  const leadAllocation = filteredAllocation[0] || allocation?.recommendations?.[0] || null;
  const leadCampaign = filteredCampaigns[0] || campaignRecommendations?.recommendations?.[0] || null;
  const leadRegionName = leadCampaign?.region_name || leadAllocation?.bundesland_name || leadPrediction?.bundesland_name || 'Deutschland';
  const leadStage = leadCampaign?.activation_level || leadAllocation?.recommended_activation_level || leadPrediction?.decision_label || 'Watch';
  const leadProductCluster = leadCampaign?.recommended_product_cluster?.label || leadAllocation?.products?.[0] || 'GELO Portfolio';
  const leadKeywordCluster = leadCampaign?.recommended_keyword_cluster?.label || 'Keyword-Cluster folgt aus Allocation';
  const leadBudget = leadCampaign?.suggested_budget_amount || leadAllocation?.suggested_budget_amount || 0;
  const leadConfidence = leadCampaign?.confidence ?? leadAllocation?.confidence ?? leadPrediction?.decision?.forecast_confidence ?? null;
  const leadEvidence = leadCampaign?.evidence_class || leadAllocation?.evidence_status || 'epidemiological_only';
  const leadSpendGate = leadCampaign?.spend_guardrail_status || leadAllocation?.spend_gate_status || 'observe_only';
  const leadCampaignWhy = leadCampaign?.recommendation_rationale?.why?.[0];
  const topBudgetShare = leadAllocation?.suggested_budget_share || leadCampaign?.suggested_budget_share || 0;

  const stageGroups = [
    {
      key: 'activate',
      label: 'Activate',
      count: activateCount,
      items: stageContextPredictions.filter((item) => normalizeStage(item.decision_label) === 'activate').slice(0, 3),
    },
    {
      key: 'prepare',
      label: 'Prepare',
      count: prepareCount,
      items: stageContextPredictions.filter((item) => normalizeStage(item.decision_label) === 'prepare').slice(0, 3),
    },
    {
      key: 'watch',
      label: 'Watch',
      count: watchCount,
      items: stageContextPredictions.filter((item) => normalizeStage(item.decision_label) === 'watch').slice(0, 3),
    },
  ];

  if (loading && !forecast && !allocation && !campaignRecommendations) {
    return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade operatives Dashboard...</div>;
  }

  return (
    <div className="page-stack">
      <section className="context-filter-rail">
        <div className="section-heading">
          <span className="section-kicker">Operational Dashboard</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {VIRUS_OPTIONS.map((option) => (
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
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
          <div className="ops-filter-group">
            <span className="ops-filter-label">Horizon</span>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {supportedHorizons.map((option) => (
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
          </div>
          <label className="ops-filter-group">
            <span className="ops-filter-label">Region</span>
            <select
              value={selectedRegion}
              onChange={(event) => setSelectedRegion(event.target.value)}
              className="media-input ops-filter-select"
            >
              <option value={REGION_FILTER_ALL}>Alle Regionen</option>
              {regionOptions.map((item) => (
                <option key={item.code} value={item.code}>{item.name}</option>
              ))}
            </select>
          </label>
          <label className="ops-filter-group">
            <span className="ops-filter-label">Decision Stage</span>
            <select
              value={selectedStage}
              onChange={(event) => setSelectedStage(event.target.value)}
              className="media-input ops-filter-select"
            >
              <option value={STAGE_FILTER_ALL}>Alle Stages</option>
              <option value="activate">Activate</option>
              <option value="prepare">Prepare</option>
              <option value="watch">Watch</option>
            </select>
          </label>
          <span className="step-chip">Budgetbasis {formatCurrency(weeklyBudget)}</span>
          <span className="step-chip">Forecast {formatDateTime(forecast?.generated_at)}</span>
          <span className="step-chip">Allocation {formatDateTime(allocation?.generated_at)}</span>
          <span className="step-chip">Recommendations {formatDateTime(campaignRecommendations?.generated_at)}</span>
        </div>
      </section>

      {!hasOperationalData && !loading ? (
        <section className="card" style={{ padding: 28, display: 'grid', gap: 16 }}>
          <div className="section-heading" style={{ gap: 8 }}>
            <span className="section-kicker">Kein operativer Output</span>
            <h1 className="subsection-title" style={{ margin: 0 }}>
              {emptyStatus === 'no_model' ? 'Für diesen Scope ist noch kein regionales Modell verfügbar.' : 'Für diesen Scope liegen aktuell keine verwertbaren Regionensignale vor.'}
            </h1>
            <p className="subsection-copy">
              {emptyMessage || 'Bitte Virus oder Horizon wechseln und die Datenlage erneut prüfen.'}
            </p>
          </div>
          <div className="review-chip-row">
            <span className="step-chip">Virus {virus}</span>
            <span className="step-chip">Horizon {horizonDays} Tage</span>
            <span className="step-chip">Unterstützte Horizonte {supportedHorizons.join(' / ')}</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            <button className="media-button secondary" type="button" onClick={() => onHorizonChange(7)}>
              Auf 7 Tage wechseln
            </button>
            <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
              Evidenz prüfen
            </button>
          </div>
        </section>
      ) : (
        <>
          <section className="card decision-header hero-card" style={{ padding: 32 }}>
            <div className="ops-exec-grid">
              <div style={{ display: 'grid', gap: 16 }}>
                <div className="hero-status-row">
                  <span style={{ ...stageTone(leadStage), padding: '8px 12px', borderRadius: 999, fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                    {displayStage(leadStage)}
                  </span>
                  <span className="campaign-confidence-chip">Horizon {horizonDays} Tage</span>
                  <span className="campaign-confidence-chip">Top Region {leadRegionName}</span>
                </div>
                <div className="section-heading" style={{ gap: 10 }}>
                  <span className="section-kicker">What should we do now?</span>
                  <h1 className="hero-title" style={{ margin: 0 }}>
                    {displayStage(leadStage)} {leadRegionName} für {leadProductCluster}.
                  </h1>
                  <p className="hero-context" style={{ margin: 0 }}>
                    {leadCampaignWhy || `${leadRegionName} führt das operative Regionenranking an und erhält im aktuellen Budget- und Evidenzrahmen die stärkste Aktivierungsempfehlung.`}
                  </p>
                  <p className="hero-copy" style={{ margin: 0 }}>
                    Keywords: {leadKeywordCluster}. Sicherheit {formatFractionPercent(leadConfidence, 0)}. Empfohlene Budgetspitze {formatCurrency(leadBudget)}.
                  </p>
                </div>
                <div className="review-chip-row">
                  <span className="step-chip">Activate {activateCount}</span>
                  <span className="step-chip">Prepare {prepareCount}</span>
                  <span className="step-chip">Watch {watchCount}</span>
                  <span className="step-chip">Lead Budget Share {formatFractionPercent(topBudgetShare, 1)}</span>
                  <span className="step-chip">Evidence {leadEvidence}</span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                  <button className="media-button" type="button" onClick={() => onOpenRegions(focusedRegionCode || undefined)}>
                    Fokusregion öffnen
                  </button>
                  <button className="media-button secondary" type="button" onClick={onOpenCampaigns}>
                    Kampagnen prüfen
                  </button>
                  <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
                    Evidenz prüfen
                  </button>
                </div>
              </div>

              <div className="soft-panel" style={{ padding: 22, display: 'grid', gap: 14 }}>
                <div className="section-kicker">Executive Summary</div>
                <div className="ops-summary-grid">
                  <div className="metric-box">
                    <span>Budget allokiert</span>
                    <strong>{formatCurrency(allocation?.summary?.total_budget_allocated)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Top Confidence</span>
                    <strong>{formatFractionPercent(leadConfidence, 0)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Top Wave Chance</span>
                    <strong>{formatFractionPercent(leadPrediction?.event_probability_calibrated, 0)}</strong>
                  </div>
                  <div className="metric-box">
                    <span>Spend Gate</span>
                    <strong>{leadSpendGate || '-'}</strong>
                  </div>
                </div>
                <div className="soft-panel" style={{ padding: 14, display: 'grid', gap: 8 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Warum diese Lage jetzt wichtig ist</div>
                  <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    {focusedPrediction?.decision?.explanation_summary || 'Der operative Score kombiniert Forecast, Datenfrische, Quelleneinigung und den Commercial Gate Layer.'}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    <span style={{ ...statusTone(leadSpendGate), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 700 }}>
                      {leadSpendGate || 'observe_only'}
                    </span>
                    <span style={{ ...statusTone(leadEvidence), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 700 }}>
                      {leadEvidence}
                    </span>
                    {focusedAllocation?.budget_release_recommendation && (
                      <span style={{ ...statusTone(focusedAllocation.budget_release_recommendation), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 700 }}>
                        {focusedAllocation.budget_release_recommendation}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="ops-dashboard-grid">
            <div className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Decision Stage Visualisierung</h2>
                <p className="subsection-copy">
                  Verteilung der Regionen nach kanonischem Decision Rank. Die Sortierung folgt nicht nur Forecast-Wahrscheinlichkeit, sondern dem Decision Layer.
                </p>
              </div>
              <div className="ops-stage-grid">
                {stageGroups.map((group) => (
                  <div key={group.key} className="soft-panel" style={{ padding: 16, display: 'grid', gap: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                      <span style={{ ...stageTone(group.label), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 800, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                        {group.label}
                      </span>
                      <strong style={{ fontSize: 24, color: 'var(--text-primary)' }}>{group.count}</strong>
                    </div>
                    <div className="ops-progress-track">
                      <div
                        className={`ops-progress-fill ops-progress-${group.key}`}
                        style={{ width: `${Math.max((group.count / totalContextRegions) * 100, group.count > 0 ? 8 : 0)}%` }}
                      />
                    </div>
                    <div style={{ display: 'grid', gap: 8 }}>
                      {group.items.length > 0 ? group.items.map((item) => (
                        <button
                          key={`${group.key}-${item.bundesland}`}
                          type="button"
                          className="campaign-list-card"
                          onClick={() => setSelectedRegion(item.bundesland)}
                          style={{ textAlign: 'left' }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                            <div>
                              <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{item.bundesland_name}</div>
                              <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                                Decision Rank #{item.decision_rank ?? item.rank ?? '-'}
                              </div>
                            </div>
                            <div style={{ textAlign: 'right' }}>
                              <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--accent-violet)' }}>
                                {formatFractionPercent(item.event_probability_calibrated, 0)}
                              </div>
                              <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                                {formatPercent(item.change_pct, 0)}
                              </div>
                            </div>
                          </div>
                        </button>
                      )) : (
                        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Keine Regionen in diesem Bucket.</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Confidence & Unsicherheit</h2>
                <p className="subsection-copy">
                  Für Management und Operative: warum diese Region oben liegt und welche Unsicherheit wir explizit sehen.
                </p>
              </div>
              {focusedPrediction ? (
                <div style={{ display: 'grid', gap: 16 }}>
                  <div className="metric-strip">
                    <div className="metric-box">
                      <span>Forecast Confidence</span>
                      <strong>{formatFractionPercent(focusedPrediction.decision?.forecast_confidence, 0)}</strong>
                    </div>
                    <div className="metric-box">
                      <span>Source Freshness</span>
                      <strong>{formatFractionPercent(focusedPrediction.decision?.source_freshness_score, 0)}</strong>
                    </div>
                    <div className="metric-box">
                      <span>Revision Risk</span>
                      <strong>{formatFractionPercent(focusedPrediction.decision?.source_revision_risk, 0)}</strong>
                    </div>
                    <div className="metric-box">
                      <span>Agreement</span>
                      <strong>{formatFractionPercent(focusedPrediction.decision?.cross_source_agreement_score, 0)}</strong>
                    </div>
                  </div>
                  <div className="soft-panel" style={{ padding: 16, display: 'grid', gap: 10 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Fokusregion</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
                      {focusedPrediction.bundesland_name}
                    </div>
                    <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      {focusedPrediction.decision?.explanation_summary}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      Unsicherheitskompakt: <strong style={{ color: 'var(--text-primary)' }}>{focusedReasonText(focusedPrediction, focusedAllocation)}</strong>
                    </div>
                  </div>
                  <div className="ops-rationale-grid">
                    <div className="soft-panel" style={{ padding: 16 }}>
                      <div className="ops-panel-title">Reason Trace</div>
                      <ul className="ops-rationale-list">
                        {(focusedPrediction.reason_trace?.why || []).map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="soft-panel" style={{ padding: 16 }}>
                      <div className="ops-panel-title">Unsicherheiten</div>
                      <ul className="ops-rationale-list">
                        {(focusedPrediction.reason_trace?.uncertainty || []).length > 0 ? (
                          focusedPrediction.reason_trace?.uncertainty?.map((item) => <li key={item}>{item}</li>)
                        ) : (
                          <li>Keine zusätzlichen Unsicherheiten markiert.</li>
                        )}
                      </ul>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ color: 'var(--text-muted)' }}>Wähle eine Region oder passe die Filter an, um die Confidence-Erklärung zu sehen.</div>
              )}
            </div>
          </section>

          <section className="ops-panel-grid">
            <div className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Regionen-Ranking</h2>
                <p className="subsection-copy">
                  Operative Priorisierung nach Decision Rank mit Wave-Chance, Trend und erster Begründung.
                </p>
              </div>
              <div className="ops-table-wrap">
                <table className="ops-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Region</th>
                      <th>Stage</th>
                      <th>Wave Chance</th>
                      <th>Trend</th>
                      <th>Priority</th>
                      <th>Confidence</th>
                      <th>Warum jetzt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPredictions.length > 0 ? filteredPredictions.map((item) => (
                      <tr key={item.bundesland} onClick={() => setSelectedRegion(item.bundesland)}>
                        <td>{item.decision_rank ?? item.rank ?? '-'}</td>
                        <td>
                          <strong>{item.bundesland_name}</strong>
                          <div className="ops-row-meta">{item.bundesland}</div>
                        </td>
                        <td>
                          <span style={{ ...stageTone(item.decision_label), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 800 }}>
                            {displayStage(item.decision_label)}
                          </span>
                        </td>
                        <td>{formatFractionPercent(item.event_probability_calibrated, 0)}</td>
                        <td>
                          <div>{item.trend}</div>
                          <div className="ops-row-meta">{formatPercent(item.change_pct, 0)}</div>
                        </td>
                        <td>{formatScore(item.priority_score)}</td>
                        <td>{formatFractionPercent(item.decision?.forecast_confidence, 0)}</td>
                        <td>{item.reason_trace?.why?.[0] || item.decision?.explanation_summary || '-'}</td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan={8} className="ops-table-empty">Keine Regionen im aktuellen Filter.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card subsection-card" style={{ padding: 24 }}>
              <div className="section-heading" style={{ gap: 6 }}>
                <h2 className="subsection-title">Allocation & Budget</h2>
                <p className="subsection-copy">
                  Budgetempfehlung pro Region mit Spend-Gate und transparenter Allocation-Logik.
                </p>
              </div>
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
                    {filteredAllocation.length > 0 ? filteredAllocation.map((item) => (
                      <tr key={item.bundesland} onClick={() => setSelectedRegion(item.bundesland)}>
                        <td>{item.priority_rank ?? '-'}</td>
                        <td>
                          <strong>{item.bundesland_name}</strong>
                          <div className="ops-row-meta">{item.products?.join(', ') || 'GELO Portfolio'}</div>
                        </td>
                        <td>
                          <span style={{ ...stageTone(item.recommended_activation_level), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 800 }}>
                            {displayStage(item.recommended_activation_level)}
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
              <div className="soft-panel" style={{ padding: 16, marginTop: 14 }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Allocation Summary</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                  <span className="step-chip">Budget allokiert {formatCurrency(allocation?.summary?.total_budget_allocated)}</span>
                  <span className="step-chip">Share Total {formatFractionPercent(allocation?.summary?.budget_share_total, 1)}</span>
                  <span className="step-chip">Spend Enabled {allocation?.summary?.spend_enabled ? 'ja' : 'nein'}</span>
                </div>
              </div>
            </div>
          </section>

          <section className="card subsection-card" style={{ padding: 24 }}>
            <div className="section-heading" style={{ gap: 6 }}>
              <h2 className="subsection-title">Recommendation-Ansicht</h2>
              <p className="subsection-copy">
                Konkrete Aktivierungsvorschläge für PEIX / GELO mit Produktcluster, Keywordcluster und guardrail-fähiger Begründung.
              </p>
            </div>
            {filteredCampaigns.length > 0 ? (
              <div className="ops-recommendation-grid">
                {filteredCampaigns.map((item) => (
                  <article key={`${item.region}-${item.recommended_product_cluster.cluster_key}`} className="card" style={{ padding: 20, display: 'grid', gap: 14 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                      <div>
                        <div className="section-kicker">Priority #{item.priority_rank}</div>
                        <h3 style={{ margin: '8px 0 0', fontSize: 20, color: 'var(--text-primary)' }}>{item.region_name}</h3>
                        <div style={{ marginTop: 6, fontSize: 13, color: 'var(--text-muted)' }}>
                          {item.recommended_product_cluster.label} · {item.recommended_keyword_cluster.label}
                        </div>
                      </div>
                      <span style={{ ...stageTone(item.activation_level), padding: '6px 10px', borderRadius: 999, fontSize: 12, fontWeight: 800 }}>
                        {displayStage(item.activation_level)}
                      </span>
                    </div>

                    <div className="metric-strip">
                      <div className="metric-box">
                        <span>Budget</span>
                        <strong>{formatCurrency(item.suggested_budget_amount)}</strong>
                      </div>
                      <div className="metric-box">
                        <span>Budget Share</span>
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

                    <div className="ops-rationale-grid">
                      <div className="soft-panel" style={{ padding: 16 }}>
                        <div className="ops-panel-title">Rationale</div>
                        <ul className="ops-rationale-list">
                          {(item.recommendation_rationale?.why || []).map((entry) => (
                            <li key={entry}>{entry}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="soft-panel" style={{ padding: 16 }}>
                        <div className="ops-panel-title">Produkt- & Keyword-Fit</div>
                        <ul className="ops-rationale-list">
                          {[...(item.recommendation_rationale?.product_fit || []), ...(item.recommendation_rationale?.keyword_fit || [])].map((entry) => (
                            <li key={entry}>{entry}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="soft-panel" style={{ padding: 16 }}>
                        <div className="ops-panel-title">Guardrails</div>
                        <ul className="ops-rationale-list">
                          {[...(item.recommendation_rationale?.budget_notes || []), ...(item.recommendation_rationale?.guardrails || []), ...(item.recommendation_rationale?.evidence_notes || [])].map((entry) => (
                            <li key={entry}>{entry}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="soft-panel" style={{ padding: 18, color: 'var(--text-secondary)' }}>
                Für den aktuellen Filter gibt es noch keine konkrete Campaign Recommendation. Das ist bei `Watch`-Regionen oder blockiertem Spend Gate ein erwartetes Verhalten.
              </div>
            )}
          </section>

          <section className="card subsection-card" style={{ padding: 24 }}>
            <div className="section-heading" style={{ gap: 6 }}>
              <h2 className="subsection-title">Reason Traces verständlich</h2>
              <p className="subsection-copy">
                Alle drei Layer bleiben sichtbar: Forecast-/Decision-Gründe, Allocation-Hebel und Campaign-Rationale.
              </p>
            </div>
            <div className="ops-rationale-grid">
              <div className="soft-panel" style={{ padding: 16 }}>
                <div className="ops-panel-title">Decision</div>
                <ul className="ops-rationale-list">
                  {(focusedPrediction?.reason_trace?.why || []).map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              </div>
              <div className="soft-panel" style={{ padding: 16 }}>
                <div className="ops-panel-title">Allocation</div>
                <ul className="ops-rationale-list">
                  {reasonTraceLines(focusedAllocation?.allocation_reason_trace || focusedAllocation?.reason_trace).length > 0 ? (
                    reasonTraceLines(focusedAllocation?.allocation_reason_trace || focusedAllocation?.reason_trace).map((entry) => (
                      <li key={entry}>{entry}</li>
                    ))
                  ) : (
                    <li>Noch keine Allocation-Trace verfügbar.</li>
                  )}
                </ul>
              </div>
              <div className="soft-panel" style={{ padding: 16 }}>
                <div className="ops-panel-title">Recommendation</div>
                <ul className="ops-rationale-list">
                  {focusedCampaign ? (
                    [
                      ...(focusedCampaign.recommendation_rationale?.why || []),
                      ...(focusedCampaign.recommendation_rationale?.product_fit || []),
                      ...(focusedCampaign.recommendation_rationale?.guardrails || []),
                    ].map((entry) => <li key={entry}>{entry}</li>)
                  ) : (
                    <li>Für die Fokusregion liegt aktuell keine konkrete Campaign Recommendation vor.</li>
                  )}
                </ul>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
};

export default OperationalDashboard;
