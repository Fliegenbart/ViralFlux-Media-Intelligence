import React, { useEffect, useState } from 'react';

import { explainInPlainGerman } from '../../lib/plainLanguage';
import {
  RegionalAllocationRecommendation,
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalDecisionReasonTrace,
  RegionalForecastPrediction,
  RegionalForecastResponse,
  StructuredReasonItem,
} from '../../types/media';
import {
  formatCurrency,
  formatDateTime,
  formatPercent,
  VIRUS_OPTIONS,
} from './cockpitUtils';
import {
  OperatorChipRail,
  OperatorPanel,
  OperatorSection,
  OperatorStat,
} from './operator/OperatorPrimitives';

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

function explainedLines(items: Array<string | StructuredReasonItem | null | undefined>): string[] {
  const seen = new Set<string>();
  return items
    .map((item) => explainInPlainGerman(item))
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function traceSectionLines(
  detailItems?: StructuredReasonItem[] | null,
  fallbackItems?: string[] | null,
): string[] {
  if (detailItems && detailItems.length > 0) {
    return explainedLines(detailItems);
  }
  return explainedLines(fallbackItems || []);
}

function firstReasonLine(items: Array<string | StructuredReasonItem | null | undefined>): string {
  return explainedLines(items)[0] || '';
}

function reasonTraceLines(trace?: RegionalDecisionReasonTrace | Record<string, unknown> | string[] | string | null): string[] {
  if (!trace) return [];
  if (typeof trace === 'string') return trace.trim() ? explainedLines([trace]) : [];
  if (Array.isArray(trace)) {
    return explainedLines(trace.map((item) => String(item || '').trim()));
  }
  const maybeTrace = trace as Partial<RegionalDecisionReasonTrace> & Record<string, unknown>;
  return [
    ...traceSectionLines(maybeTrace.why_details, Array.isArray(maybeTrace.why) ? maybeTrace.why : []),
    ...traceSectionLines(
      maybeTrace.budget_driver_details,
      Array.isArray(maybeTrace.budget_drivers) ? maybeTrace.budget_drivers : [],
    ),
    ...traceSectionLines(
      maybeTrace.uncertainty_details,
      Array.isArray(maybeTrace.uncertainty) ? maybeTrace.uncertainty : [],
    ),
    ...traceSectionLines(
      maybeTrace.policy_override_details,
      Array.isArray(maybeTrace.policy_overrides) ? maybeTrace.policy_overrides : [],
    ),
    ...traceSectionLines(
      maybeTrace.blocker_details,
      Array.isArray(maybeTrace.blockers) ? maybeTrace.blockers : [],
    ),
  ];
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
  return firstReasonLine([
    prediction?.decision?.uncertainty_summary_detail,
    prediction?.decision?.uncertainty_summary,
    prediction?.uncertainty_summary,
    ...(prediction?.reason_trace?.uncertainty_details || []),
    ...(prediction?.reason_trace?.uncertainty || []),
    allocationItem?.uncertainty_summary,
    ...reasonTraceLines(allocationItem?.allocation_reason_trace || allocationItem?.reason_trace),
    'Noch keine Unsicherheitserklärung verfügbar.',
  ]);
}

function StageBadge({ value }: { value?: string | null }) {
  return (
    <span
      style={{
        ...stageTone(value),
        padding: '6px 10px',
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 800,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
      }}
    >
      {displayStage(value)}
    </span>
  );
}

function StatusBadge({ value }: { value?: string | null }) {
  return (
    <span
      style={{
        ...statusTone(value),
        padding: '6px 10px',
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 700,
      }}
    >
      {value || '-'}
    </span>
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
  const leadCampaignWhy = firstReasonLine([
    leadCampaign?.recommendation_rationale?.why_details?.[0],
    leadCampaign?.recommendation_rationale?.why?.[0],
  ]);
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
    <div className="page-stack operator-page">
      <OperatorSection
        kicker="Operational Dashboard"
        title="Operative Lageführung"
        description="Forecast, Budgetlogik und Kampagnenimpulse bleiben hier in einem kompakten Arbeitsraum gebündelt."
        tone="muted"
        className="operator-toolbar-shell"
      >
        <div className="operator-toolbar-grid">
          <div className="operator-toolbar-controls">
            <div className="ops-filter-group">
              <span className="ops-filter-label">Virus</span>
              <OperatorChipRail>
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
              </OperatorChipRail>
            </div>

            <div className="operator-toolbar-selects">
              <div className="ops-filter-group">
                <span className="ops-filter-label">Zeitraum</span>
                <OperatorChipRail>
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
                </OperatorChipRail>
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
                <span className="ops-filter-label">Entscheidungsstufe</span>
                <select
                  value={selectedStage}
                  onChange={(event) => setSelectedStage(event.target.value)}
                  className="media-input ops-filter-select"
                >
                  <option value={STAGE_FILTER_ALL}>Alle Stufen</option>
                  <option value="activate">Aktivieren</option>
                  <option value="prepare">Vorbereiten</option>
                  <option value="watch">Beobachten</option>
                </select>
              </label>
            </div>
          </div>

          <OperatorChipRail className="operator-toolbar-meta">
            <span className="step-chip">Budgetbasis {formatCurrency(weeklyBudget)}</span>
            <span className="step-chip">Forecast {formatDateTime(forecast?.generated_at)}</span>
            <span className="step-chip">Allocation {formatDateTime(allocation?.generated_at)}</span>
            <span className="step-chip">Empfehlungen {formatDateTime(campaignRecommendations?.generated_at)}</span>
          </OperatorChipRail>
        </div>
      </OperatorSection>

      {!hasOperationalData && !loading ? (
        <OperatorSection
          kicker="Kein operativer Output"
          title={emptyStatus === 'no_model' ? 'Für diesen Scope ist noch kein regionales Modell verfügbar.' : 'Für diesen Scope liegen aktuell keine verwertbaren Regionensignale vor.'}
          description={emptyMessage || 'Bitte Virus oder Zeitraum wechseln und die Datenlage erneut prüfen.'}
        >
          <OperatorChipRail className="review-chip-row">
            <span className="step-chip">Virus {virus}</span>
            <span className="step-chip">Zeitraum {horizonDays} Tage</span>
            <span className="step-chip">Unterstützte Horizonte {supportedHorizons.join(' / ')}</span>
          </OperatorChipRail>
          <div className="action-row">
            <button className="media-button secondary" type="button" onClick={() => onHorizonChange(7)}>
              Auf 7 Tage wechseln
            </button>
            <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
              Evidenz prüfen
            </button>
          </div>
        </OperatorSection>
      ) : (
        <>
          <OperatorSection
            kicker="Operative Empfehlung"
            title="Was solltest du jetzt tun?"
            description={`${leadRegionName} führt die aktuelle Lage an. Der Bereich bleibt in dieser Ansicht bewusst auf Entscheidung, Timing und nächste Arbeitsaktion verdichtet.`}
            tone="accent"
            className="decision-header hero-card"
          >
            <div className="ops-exec-grid">
              <div className="hero-main">
                <div className="hero-status-row">
                  <StageBadge value={leadStage} />
                  <span className="campaign-confidence-chip">Zeitraum {horizonDays} Tage</span>
                  <span className="campaign-confidence-chip">Fokusregion {leadRegionName}</span>
                </div>
                <div className="section-heading" style={{ gap: 10 }}>
                  <h1 className="hero-title" style={{ margin: 0 }}>
                    {displayStage(leadStage)} {leadRegionName} für {leadProductCluster}.
                  </h1>
                  <p className="hero-context" style={{ margin: 0 }}>
                    {leadCampaignWhy || `${leadRegionName} führt das operative Regionenranking an und erhält im aktuellen Budget- und Evidenzrahmen die stärkste Aktivierungsempfehlung.`}
                  </p>
                  <p className="hero-copy" style={{ margin: 0 }}>
                    Keyword-Fokus: {leadKeywordCluster}. Signal-Sicherheit {formatFractionPercent(leadConfidence, 0)}. Empfohlene Budgetspitze {formatCurrency(leadBudget)}.
                  </p>
                </div>
                <OperatorChipRail className="review-chip-row">
                  <span className="step-chip">Aktivieren {activateCount}</span>
                  <span className="step-chip">Vorbereiten {prepareCount}</span>
                  <span className="step-chip">Beobachten {watchCount}</span>
                  <span className="step-chip">Top-Budgetanteil {formatFractionPercent(topBudgetShare, 1)}</span>
                  <span className="step-chip">Evidenzstatus {leadEvidence}</span>
                </OperatorChipRail>
                <div className="action-row">
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

              <OperatorPanel eyebrow="Kurzüberblick" tone="muted">
                <div className="operator-stat-grid ops-summary-grid">
                  <OperatorStat label="Budget allokiert" value={formatCurrency(allocation?.summary?.total_budget_allocated)} tone="accent" />
                  <OperatorStat label="Signal-Sicherheit" value={formatFractionPercent(leadConfidence, 0)} />
                  <OperatorStat label="Event-Wahrscheinlichkeit" value={formatFractionPercent(leadPrediction?.event_probability_calibrated, 0)} />
                  <OperatorStat label="Spend-Status" value={leadSpendGate || '-'} />
                </div>
                <div className="soft-panel" style={{ padding: 14, display: 'grid', gap: 8 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Warum diese Lage jetzt wichtig ist</div>
                  <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    {firstReasonLine([
                      focusedPrediction?.decision?.explanation_summary_detail,
                      focusedPrediction?.decision?.explanation_summary,
                    ]) || 'Die operative Einordnung kombiniert Vorhersage, Datenfrische, Quellenabgleich und Freigabe-Regeln.'}
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    <strong style={{ color: 'var(--text-primary)' }}>So sind die Zahlen gemeint:</strong> Event-Wahrscheinlichkeit ist die Forecast-Chance für das definierte Ereignis. Prioritäts-Score ordnet Regionen. Signal-Sicherheit zeigt, wie belastbar das Signal ist.
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    <StatusBadge value={leadSpendGate || 'observe_only'} />
                    <StatusBadge value={leadEvidence} />
                    {focusedAllocation?.budget_release_recommendation && (
                      <StatusBadge value={focusedAllocation.budget_release_recommendation} />
                    )}
                  </div>
                </div>
              </OperatorPanel>
            </div>
          </OperatorSection>

          <section className="ops-dashboard-grid">
            <OperatorPanel
              title="Stufen nach Entscheidung"
              description="Verteilung der Regionen nach Entscheidungsrang. Die Reihenfolge folgt nicht nur der Event-Wahrscheinlichkeit, sondern dem gesamten Entscheidungsmodell."
            >
              <div className="ops-stage-grid">
                {stageGroups.map((group) => (
                  <div key={group.key} className="soft-panel" style={{ padding: 16, display: 'grid', gap: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                      <StageBadge value={group.label} />
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
                                Entscheidungsrang #{item.decision_rank ?? item.rank ?? '-'}
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
            </OperatorPanel>

            <OperatorPanel
              title="Sicherheit & Unsicherheit"
              description="Hier siehst du, warum eine Region oben liegt und wo wir noch Unsicherheit sehen."
            >
              {focusedPrediction ? (
                <div style={{ display: 'grid', gap: 16 }}>
                  <div className="operator-stat-grid metric-strip">
                    <OperatorStat label="Forecast-Sicherheit" value={formatFractionPercent(focusedPrediction.decision?.forecast_confidence, 0)} />
                    <OperatorStat label="Datenfrische" value={formatFractionPercent(focusedPrediction.decision?.source_freshness_score, 0)} />
                    <OperatorStat label="Revisionsrisiko" value={formatFractionPercent(focusedPrediction.decision?.source_revision_risk, 0)} />
                    <OperatorStat label="Quellenabgleich" value={formatFractionPercent(focusedPrediction.decision?.cross_source_agreement_score, 0)} />
                  </div>
                  <div className="soft-panel" style={{ padding: 16, display: 'grid', gap: 10 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Fokusregion</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
                      {focusedPrediction.bundesland_name}
                    </div>
                    <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      {firstReasonLine([
                        focusedPrediction.decision?.explanation_summary_detail,
                        focusedPrediction.decision?.explanation_summary,
                      ])}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      Unsicherheitskompakt: <strong style={{ color: 'var(--text-primary)' }}>{focusedReasonText(focusedPrediction, focusedAllocation)}</strong>
                    </div>
                  </div>
                  <div className="ops-rationale-grid">
                    <div className="soft-panel" style={{ padding: 16 }}>
                      <div className="ops-panel-title">Begründungslinie</div>
                      <ul className="ops-rationale-list">
                        {traceSectionLines(
                          focusedPrediction.reason_trace?.why_details,
                          focusedPrediction.reason_trace?.why,
                        ).map((item) => (
                          <li key={item}>{explainInPlainGerman(item)}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="soft-panel" style={{ padding: 16 }}>
                      <div className="ops-panel-title">Unsicherheiten</div>
                      <ul className="ops-rationale-list">
                        {traceSectionLines(
                          focusedPrediction.reason_trace?.uncertainty_details,
                          focusedPrediction.reason_trace?.uncertainty,
                        ).length > 0 ? (
                          traceSectionLines(
                            focusedPrediction.reason_trace?.uncertainty_details,
                            focusedPrediction.reason_trace?.uncertainty,
                          ).map((item) => <li key={item}>{explainInPlainGerman(item)}</li>)
                        ) : (
                          <li>Keine zusätzlichen Unsicherheiten markiert.</li>
                        )}
                      </ul>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ color: 'var(--text-muted)' }}>Wähle eine Region oder passe die Filter an, um die Sicherheits-Erklärung zu sehen.</div>
              )}
            </OperatorPanel>
          </section>

          <section className="ops-panel-grid">
            <OperatorPanel
              title="Regionen-Ranking"
              description="Operative Priorisierung nach Entscheidungsrang mit Event-Wahrscheinlichkeit, Trend und erster Begründung."
            >
              <div className="ops-table-wrap">
                <table className="ops-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Region</th>
                      <th>Stufe</th>
                      <th>Event-Wahrscheinlichkeit</th>
                      <th>Trend</th>
                      <th>Prioritäts-Score</th>
                      <th>Forecast-Sicherheit</th>
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
                          <StageBadge value={item.decision_label} />
                        </td>
                        <td>{formatFractionPercent(item.event_probability_calibrated, 0)}</td>
                        <td>
                          <div>{item.trend}</div>
                          <div className="ops-row-meta">{formatPercent(item.change_pct, 0)}</div>
                        </td>
                        <td>{formatScore(item.priority_score)}</td>
                        <td>{formatFractionPercent(item.decision?.forecast_confidence, 0)}</td>
                        <td>{firstReasonLine([
                          item.reason_trace?.why_details?.[0],
                          item.reason_trace?.why?.[0],
                          item.decision?.explanation_summary_detail,
                          item.decision?.explanation_summary,
                          '-',
                        ])}</td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan={8} className="ops-table-empty">Keine Regionen im aktuellen Filter.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </OperatorPanel>

            <OperatorPanel
              title="Budgetlogik"
              description="Budgetempfehlung pro Region mit Spend-Status und transparenter Allokationslogik."
            >
              <div className="ops-table-wrap">
                <table className="ops-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Region</th>
                      <th>Aktivierungsstufe</th>
                      <th>Budget</th>
                      <th>Budgetanteil</th>
                      <th>Allokations-Sicherheit</th>
                      <th>Spend-Status</th>
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
                          <StageBadge value={item.recommended_activation_level} />
                        </td>
                        <td>{formatCurrency(item.suggested_budget_amount)}</td>
                        <td>{formatFractionPercent(item.suggested_budget_share, 1)}</td>
                        <td>{formatFractionPercent(item.confidence, 0)}</td>
                        <td>
                          <StatusBadge value={item.spend_gate_status || 'observe_only'} />
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
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Budgetüberblick</div>
                <OperatorChipRail className="review-chip-row">
                  <span className="step-chip">Budget gesamt {formatCurrency(allocation?.summary?.total_budget_allocated)}</span>
                  <span className="step-chip">Anteil gesamt {formatFractionPercent(allocation?.summary?.budget_share_total, 1)}</span>
                  <span className="step-chip">Spend offen {allocation?.summary?.spend_enabled ? 'ja' : 'nein'}</span>
                </OperatorChipRail>
              </div>
            </OperatorPanel>
          </section>

          <OperatorSection
            title="Empfehlungsansicht"
            description="Konkrete Aktivierungsvorschläge für PEIX / GELO mit Produktcluster, Keywordcluster und klarer Freigabe-Begründung."
          >
            {filteredCampaigns.length > 0 ? (
              <div className="ops-recommendation-grid">
                {filteredCampaigns.map((item) => (
                  <OperatorPanel
                    key={`${item.region}-${item.recommended_product_cluster.cluster_key}`}
                    eyebrow={`Priorität #${item.priority_rank}`}
                    title={item.region_name}
                    description={`${item.recommended_product_cluster.label} · ${item.recommended_keyword_cluster.label}`}
                    actions={<StageBadge value={item.activation_level} />}
                    className="operator-recommendation-card"
                  >
                    <div className="operator-stat-grid metric-strip">
                      <OperatorStat label="Budget" value={formatCurrency(item.suggested_budget_amount)} tone="accent" />
                      <OperatorStat label="Budgetanteil" value={formatFractionPercent(item.suggested_budget_share, 1)} />
                      <OperatorStat label="Signal-Sicherheit" value={formatFractionPercent(item.confidence, 0)} />
                      <OperatorStat label="Evidenzstatus" value={item.evidence_class} />
                    </div>

                    <OperatorChipRail>
                      <StatusBadge value={item.spend_guardrail_status} />
                      {(item.keywords || []).slice(0, 4).map((keyword) => (
                        <span key={keyword} className="step-chip">{keyword}</span>
                      ))}
                    </OperatorChipRail>

                    <div className="ops-rationale-grid">
                      <div className="soft-panel" style={{ padding: 16 }}>
                        <div className="ops-panel-title">Rationale</div>
                        <ul className="ops-rationale-list">
                          {traceSectionLines(
                            item.recommendation_rationale?.why_details,
                            item.recommendation_rationale?.why,
                          ).map((entry) => (
                            <li key={entry}>{explainInPlainGerman(entry)}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="soft-panel" style={{ padding: 16 }}>
                        <div className="ops-panel-title">Produkt- & Keyword-Fit</div>
                        <ul className="ops-rationale-list">
                          {[
                            ...traceSectionLines(
                              item.recommendation_rationale?.product_fit_details,
                              item.recommendation_rationale?.product_fit,
                            ),
                            ...traceSectionLines(
                              item.recommendation_rationale?.keyword_fit_details,
                              item.recommendation_rationale?.keyword_fit,
                            ),
                          ].map((entry) => (
                            <li key={entry}>{explainInPlainGerman(entry)}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="soft-panel" style={{ padding: 16 }}>
                        <div className="ops-panel-title">Guardrails</div>
                        <ul className="ops-rationale-list">
                          {[
                            ...traceSectionLines(
                              item.recommendation_rationale?.budget_note_details,
                              item.recommendation_rationale?.budget_notes,
                            ),
                            ...traceSectionLines(
                              item.recommendation_rationale?.guardrail_details,
                              item.recommendation_rationale?.guardrails,
                            ),
                            ...traceSectionLines(
                              item.recommendation_rationale?.evidence_note_details,
                              item.recommendation_rationale?.evidence_notes,
                            ),
                          ].map((entry) => (
                            <li key={entry}>{explainInPlainGerman(entry)}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </OperatorPanel>
                ))}
              </div>
            ) : (
              <div className="soft-panel" style={{ padding: 18, color: 'var(--text-secondary)' }}>
                Für den aktuellen Filter gibt es noch keinen konkreten Kampagnenvorschlag. Das ist bei `Watch`-Regionen oder blockiertem Spend-Status ein erwartetes Verhalten.
              </div>
            )}
          </OperatorSection>

          <OperatorSection
            title="Begründungen im Klartext"
            description="Alle drei Layer bleiben sichtbar: Forecast-/Decision-Gründe, Allocation-Hebel und Campaign-Rationale."
          >
            <div className="ops-rationale-grid">
              <OperatorPanel title="Entscheidung" tone="muted">
                <ul className="ops-rationale-list">
                  {traceSectionLines(
                    focusedPrediction?.reason_trace?.why_details,
                    focusedPrediction?.reason_trace?.why,
                  ).map((entry) => (
                    <li key={entry}>{explainInPlainGerman(entry)}</li>
                  ))}
                </ul>
              </OperatorPanel>
              <OperatorPanel title="Budgetlogik" tone="muted">
                <ul className="ops-rationale-list">
                  {reasonTraceLines(focusedAllocation?.allocation_reason_trace || focusedAllocation?.reason_trace).length > 0 ? (
                    reasonTraceLines(focusedAllocation?.allocation_reason_trace || focusedAllocation?.reason_trace).map((entry) => (
                      <li key={entry}>{entry}</li>
                    ))
                  ) : (
                    <li>Noch keine Begründung aus der Budgetlogik verfügbar.</li>
                  )}
                </ul>
              </OperatorPanel>
              <OperatorPanel title="Kampagnenvorschlag" tone="muted">
                <ul className="ops-rationale-list">
                  {focusedCampaign ? (
                    [
                      ...traceSectionLines(
                        focusedCampaign.recommendation_rationale?.why_details,
                        focusedCampaign.recommendation_rationale?.why,
                      ),
                      ...traceSectionLines(
                        focusedCampaign.recommendation_rationale?.product_fit_details,
                        focusedCampaign.recommendation_rationale?.product_fit,
                      ),
                      ...traceSectionLines(
                        focusedCampaign.recommendation_rationale?.guardrail_details,
                        focusedCampaign.recommendation_rationale?.guardrails,
                      ),
                    ].map((entry) => <li key={entry}>{explainInPlainGerman(entry)}</li>)
                  ) : (
                    <li>Für die Fokusregion liegt aktuell noch kein konkreter Kampagnenvorschlag vor.</li>
                  )}
                </ul>
              </OperatorPanel>
            </div>
          </OperatorSection>
        </>
      )}
    </div>
  );
};

export default OperationalDashboard;
