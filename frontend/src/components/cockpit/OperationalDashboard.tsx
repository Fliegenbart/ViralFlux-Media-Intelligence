import React, { useEffect, useId, useMemo, useRef, useState } from 'react';

import CollapsibleSection from '../CollapsibleSection';
import { COCKPIT_SEMANTICS, UI_COPY, evidenceStatusHelper, evidenceStatusLabel } from '../../lib/copy';
import { explainInPlainGerman } from '../../lib/plainLanguage';
import {
  RegionalAllocationRecommendation,
  RegionalAllocationResponse,
  RegionalCampaignRecommendationsResponse,
  RegionalDecisionReasonTrace,
  RegionalForecastPrediction,
  RegionalForecastResponse,
  MetricContract,
  StructuredReasonItem,
} from '../../types/media';
import {
  formatCurrency,
  formatDateTime,
  formatPercent,
  metricContractDisplayLabel,
  metricContractNote,
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

function classNames(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ');
}

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

function stageBadgeTone(value?: string | null): string {
  const normalized = normalizeStage(value);
  if (normalized === 'activate') return 'badge-pill--success';
  if (normalized === 'prepare') return 'badge-pill--warning';
  return 'badge-pill--info';
}

function statusBadgeTone(value?: string | null): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized.includes('release') || normalized === 'ready') return 'badge-pill--success';
  if (normalized.includes('review') || normalized.includes('guarded')) return 'badge-pill--warning';
  if (normalized.includes('block')) return 'badge-pill--danger';
  return '';
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
    <span className={classNames('badge-pill', stageBadgeTone(value), 'ops-stage-badge')}>
      {displayStage(value)}
    </span>
  );
}

function StatusBadge({ value }: { value?: string | null }) {
  return (
    <span className={classNames('badge-pill', statusBadgeTone(value), 'ops-status-badge')}>
      {evidenceStatusLabel(value)}
    </span>
  );
}

function ScopeBadge({ children }: { children: React.ReactNode }) {
  return <span className="step-chip ops-scope-badge">{children}</span>;
}

interface ChipTabOption<T extends string | number> {
  value: T;
  label: string;
}

function ChipTabGroup<T extends string | number>({
  label,
  selectedValue,
  options,
  onChange,
}: {
  label: string;
  selectedValue: T;
  options: ChipTabOption<T>[];
  onChange: (value: T) => void;
}) {
  const tabListId = useId();
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const activeIndex = Math.max(options.findIndex((option) => option.value === selectedValue), 0);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();

    let nextIndex = activeIndex;
    if (event.key === 'ArrowRight') nextIndex = (activeIndex + 1) % options.length;
    if (event.key === 'ArrowLeft') nextIndex = (activeIndex - 1 + options.length) % options.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = options.length - 1;

    const nextOption = options[nextIndex];
    if (!nextOption) return;
    onChange(nextOption.value);
    buttonRefs.current[nextIndex]?.focus();
  };

  return (
    <div
      id={tabListId}
      role="tablist"
      aria-label={label}
      className="operator-chip-rail"
      onKeyDown={handleKeyDown}
    >
      {options.map((option, index) => {
        const selected = option.value === selectedValue;
        return (
          <button
            key={String(option.value)}
            ref={(node) => {
              buttonRefs.current[index] = node;
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={undefined}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(option.value)}
            className={`tab-chip ${selected ? 'active' : ''}`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
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
  const regionTableId = useId();
  const allocationTableId = useId();
  const detailSectionId = useId();

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
  const topRiskRegions = (filteredPredictions.length > 0 ? filteredPredictions : decisionRanked).slice(0, 3);
  const forecastFieldContracts = (focusedPrediction as ({ field_contracts?: Record<string, MetricContract> } & RegionalForecastPrediction) | null)?.field_contracts;
  const eventProbabilityLabel = metricContractDisplayLabel(
    forecastFieldContracts,
    'event_probability',
    'Event-Wahrscheinlichkeit',
  );
  const eventProbabilityNote = metricContractNote(
    forecastFieldContracts,
    'event_probability',
    'Beschreibt die kalibrierte Wahrscheinlichkeit für das definierte Forecast-Ereignis.',
  );
  const rankingSignalLabel = metricContractDisplayLabel(
    forecastFieldContracts,
    'signal_score',
    'Ranking-Signal',
  );
  const rankingSignalNote = metricContractNote(
    forecastFieldContracts,
    'signal_score',
    'Hilft beim Vergleichen und Priorisieren, ist aber keine Eintrittswahrscheinlichkeit.',
  );
  const priorityScoreLabel = metricContractDisplayLabel(
    forecastFieldContracts,
    'priority_score',
    UI_COPY.decisionPriority,
  );
  const rankingSignalValue = leadPrediction?.decision?.decision_score ?? leadPrediction?.priority_score ?? leadAllocation?.allocation_score ?? null;
  const leadEvidenceLabel = evidenceStatusLabel(leadEvidence);
  const leadEvidenceHelper = evidenceStatusHelper(leadEvidence);
  const leadSpendGateLabel = evidenceStatusLabel(leadSpendGate);
  const leadSpendGateHelper = evidenceStatusHelper(leadSpendGate);
  const leadActionTitle = `${displayStage(leadStage)} ${leadRegionName} auf ${UI_COPY.stateLevelScope}.`;
  const leadActionMeta = (() => {
    if (normalizeStage(leadStage) === 'activate') {
      return 'Jetzt zuerst den Aktivierungsfall und die Budgetfreigabe für dieses Bundesland prüfen.';
    }
    if (normalizeStage(leadStage) === 'prepare') {
      return 'Jetzt zuerst den Vorbereitungsfall schärfen und Guardrails prüfen.';
    }
    return 'Aktuell zuerst beobachten, Evidenz prüfen und keinen zu präzisen Aktivierungsanschein erzeugen.';
  })();
  const uncertaintySummary = focusedReasonText(focusedPrediction, focusedAllocation);
  const forecastSummary = firstReasonLine([
    focusedPrediction?.decision?.explanation_summary_detail,
    focusedPrediction?.decision?.explanation_summary,
    focusedPrediction?.reason_trace?.why_details?.[0],
    focusedPrediction?.reason_trace?.why?.[0],
  ]) || 'Für die Fokusregion liegt aktuell noch keine kurze Forecast-Zusammenfassung vor.';
  const riskSummary = topRiskRegions.length > 0
    ? topRiskRegions.map((item) => item.bundesland_name).join(', ')
    : 'Aktuell keine priorisierten Bundesländer im Filter.';

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
  const virusOptions = useMemo(
    () => VIRUS_OPTIONS.map((option) => ({ value: option, label: option })),
    [],
  );
  const horizonOptions = useMemo(
    () => supportedHorizons.map((option) => ({ value: option, label: `${option} Tage` })),
    [supportedHorizons],
  );

  const handleInteractiveRowKeyDown = (event: React.KeyboardEvent<HTMLElement>, nextRegion: string) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      setSelectedRegion(nextRegion);
    }
  };

  if (loading && !forecast && !allocation && !campaignRecommendations) {
    return <div className="card" role="status" aria-live="polite" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Lade operatives Dashboard...</div>;
  }

  return (
    <div className="page-stack operator-page">
      <OperatorSection
        kicker="Operational Dashboard"
        title="Operative Entscheidung"
        description="Hier ordnen wir die Lage auf Bundesland-Level so, dass du sofort siehst, was passiert, wo du handeln musst und wie sicher das Signal ist."
        tone="muted"
        className="operator-toolbar-shell"
      >
        <div className="operator-toolbar-grid">
            <div className="operator-toolbar-controls">
              <div className="ops-filter-group">
                <span className="ops-filter-label" id="ops-virus-filter-label">Virus</span>
                <ChipTabGroup label="Virus wählen" selectedValue={virus} options={virusOptions} onChange={onVirusChange} />
              </div>

              <div className="operator-toolbar-selects">
                <div className="ops-filter-group">
                  <span className="ops-filter-label" id="ops-horizon-filter-label">Zeitraum</span>
                  <ChipTabGroup label="Zeitraum wählen" selectedValue={horizonDays} options={horizonOptions} onChange={onHorizonChange} />
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
            kicker="Erster Blick"
            title="Was passiert, wo musst du handeln und wie sicher ist das?"
            description="Die Top-Zone verdichtet den aktuellen Scope zu einer klaren Operator-Entscheidung. Alles darunter dient nur noch zum Einordnen und Prüfen."
            tone="accent"
            className="decision-header hero-card ops-top-section"
          >
            <OperatorChipRail className="operator-toolbar-meta">
              <ScopeBadge>Scope {virus}</ScopeBadge>
              <ScopeBadge>Horizont {horizonDays} Tage</ScopeBadge>
              <ScopeBadge>{UI_COPY.stateLevelScope}</ScopeBadge>
              <ScopeBadge>Forecast {formatDateTime(forecast?.generated_at)}</ScopeBadge>
            </OperatorChipRail>

            <div className="ops-top-zone">
              <section className="ops-primary-action-card" aria-labelledby="ops-primary-action-title">
                <div className="ops-primary-action-card__header">
                  <div>
                    <div className="ops-panel-title">Empfohlene Aktion</div>
                    <h2 id="ops-primary-action-title" className="ops-primary-action-card__title">
                      {leadActionTitle}
                    </h2>
                  </div>
                  <StageBadge value={leadStage} />
                </div>
                <div className="ops-primary-action-card__body">
                  <div className="ops-question-block">
                    <span className="ops-question-block__label">Was passiert?</span>
                    <p className="ops-question-block__value">
                      {forecastSummary}
                    </p>
                  </div>
                  <div className="ops-question-block">
                    <span className="ops-question-block__label">Wo musst du handeln?</span>
                    <p className="ops-question-block__value">
                      {leadRegionName} ist im gewählten Scope das vorderste Bundesland und trägt aktuell den ersten Arbeitsfall für {leadProductCluster}.
                    </p>
                  </div>
                  <div className="ops-question-block">
                    <span className="ops-question-block__label">Wie sicher ist das?</span>
                    <p className="ops-question-block__value">
                      {uncertaintySummary}
                    </p>
                  </div>
                  <div className="ops-primary-action-card__meta">
                    <span>Keyword-Fokus: {leadKeywordCluster}</span>
                    <span>Empfohlene Budgetspitze: {formatCurrency(leadBudget)}</span>
                    <span>{leadActionMeta}</span>
                  </div>
                </div>
                <OperatorChipRail>
                  <ScopeBadge>Top-Budgetanteil {formatFractionPercent(topBudgetShare, 1)}</ScopeBadge>
                  <ScopeBadge>Evidenz {leadEvidenceLabel}</ScopeBadge>
                  <ScopeBadge>Spend-Status {leadSpendGateLabel}</ScopeBadge>
                </OperatorChipRail>
                <div className="action-row">
                  <button className="media-button" type="button" onClick={() => onOpenRegions(focusedRegionCode || undefined)}>
                    Fokus-Bundesland öffnen
                  </button>
                  <button className="media-button secondary" type="button" onClick={onOpenCampaigns}>
                    Kampagnen prüfen
                  </button>
                  <button className="media-button secondary" type="button" onClick={onOpenEvidence}>
                    Evidenz prüfen
                  </button>
                </div>
              </section>

              <div className="ops-top-stack">
                <OperatorPanel eyebrow="Aktueller Scope" title="Operator Summary" tone="muted">
                  <div className="operator-stat-grid ops-summary-grid">
                    <OperatorStat label="Hauptsignal" value={displayStage(leadStage)} meta={`${leadRegionName} · ${UI_COPY.stateLevelScope}`} tone="accent" />
                    <OperatorStat label={eventProbabilityLabel} value={formatFractionPercent(leadPrediction?.event_probability_calibrated, 0)} meta="Forecast-Ereignis" />
                    <OperatorStat label="Signal-Sicherheit" value={formatFractionPercent(leadConfidence, 0)} meta="Belastbarkeit des Signals" />
                    <OperatorStat label="Budget allokiert" value={formatCurrency(allocation?.summary?.total_budget_allocated)} meta="Aktueller Scope" />
                  </div>
                </OperatorPanel>

                <OperatorPanel eyebrow="Top-Risiko-Regionen" title="Wo zuerst hinschauen?" tone="muted">
                  <div className="ops-region-list" aria-label="Top-Risiko-Regionen">
                    {topRiskRegions.map((item) => (
                      <button
                        key={item.bundesland}
                  type="button"
                  className="campaign-list-card"
                  onClick={() => setSelectedRegion(item.bundesland)}
                  aria-pressed={selectedRegion === item.bundesland}
                >
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                          <div style={{ textAlign: 'left' }}>
                            <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>
                              {item.bundesland_name}
                            </div>
                            <div className="ops-row-meta">
                              {UI_COPY.stateLevelScope} · Rang #{item.decision_rank ?? item.rank ?? '-'}
                            </div>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <div className="ops-number-emphasis">{formatFractionPercent(item.event_probability_calibrated, 0)}</div>
                            <div className="ops-row-meta">{displayStage(item.decision_label)}</div>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                  <div className="workspace-note-card">
                    {riskSummary}
                  </div>
                </OperatorPanel>

                <OperatorPanel eyebrow="Unsicherheit" title="Wie sicher ist das Signal?" tone="muted">
                  <div className="ops-confidence-card">
                    <div className="ops-confidence-card__row">
                      <span className="ops-confidence-card__label">{eventProbabilityLabel}</span>
                      <strong className="ops-number-emphasis">{formatFractionPercent(leadPrediction?.event_probability_calibrated, 0)}</strong>
                    </div>
                    <p>{eventProbabilityNote}</p>
                  </div>
                  <div className="workspace-note-card">
                    <strong>{COCKPIT_SEMANTICS.uncertainty.badge}:</strong> {uncertaintySummary}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    <StatusBadge value={leadSpendGate || 'observe_only'} />
                    <StatusBadge value={leadEvidence} />
                    {focusedAllocation?.budget_release_recommendation && (
                      <StatusBadge value={focusedAllocation.budget_release_recommendation} />
                    )}
                  </div>
                </OperatorPanel>
              </div>
            </div>
          </OperatorSection>

          <section className="ops-dashboard-grid ops-dashboard-grid--three-up">
            <OperatorPanel
              title="Forecast / Ereigniswahrscheinlichkeit"
              description={`Hier trennen wir klar zwischen Forecast-Ereignis, ${COCKPIT_SEMANTICS.rankingSignal.label} und ${COCKPIT_SEMANTICS.decisionPriority.label}. ${COCKPIT_SEMANTICS.eventProbability.label} beschreibt das Forecast-Ereignis, nicht den Rang.`}
            >
              <div className="ops-supporting-metrics">
                <div className="ops-signal-card ops-signal-card--probability">
                  <span className="ops-signal-card__label">{eventProbabilityLabel}</span>
                  <strong>{formatFractionPercent(leadPrediction?.event_probability_calibrated, 0)}</strong>
                  <p>{eventProbabilityNote}</p>
                </div>
                <div className="ops-signal-card">
                  <span className="ops-signal-card__label">{rankingSignalLabel}</span>
                  <strong>{formatScore(rankingSignalValue, 2)}</strong>
                  <p>{rankingSignalNote}</p>
                </div>
                <div className="ops-signal-card">
                  <span className="ops-signal-card__label">{priorityScoreLabel}</span>
                  <strong>{formatScore(leadPrediction?.priority_score, 2)}</strong>
                  <p>{COCKPIT_SEMANTICS.decisionPriority.helper}</p>
                </div>
              </div>

              <div className="workspace-note-card">
                <strong>{UI_COPY.stateLevelScope}:</strong> {COCKPIT_SEMANTICS.stateLevelScope.helper} <strong>{UI_COPY.noCityForecast}:</strong> {COCKPIT_SEMANTICS.noCityForecast.helper}
              </div>

              <div className="ops-region-list">
                {topRiskRegions.map((item) => (
                  <button
                    key={`forecast-${item.bundesland}`}
                    type="button"
                    className="campaign-list-card"
                    onClick={() => setSelectedRegion(item.bundesland)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                      <div style={{ textAlign: 'left' }}>
                        <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>{item.bundesland_name}</div>
                        <div className="ops-row-meta">
                          {displayStage(item.decision_label)} · {item.trend} · {formatPercent(item.change_pct, 0)}
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div className="ops-number-emphasis">{formatFractionPercent(item.event_probability_calibrated, 0)}</div>
                        <div className="ops-row-meta">{COCKPIT_SEMANTICS.eventProbability.badge}</div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </OperatorPanel>

            <OperatorPanel
              title="Budget- / Portfolio-Allokation"
              description="Hier siehst du die Budgetentscheidung getrennt vom Forecast. Das Budget folgt der Priorisierung, ist aber nicht identisch mit der Event-Wahrscheinlichkeit."
            >
              <div className="operator-stat-grid metric-strip">
                <OperatorStat label="Budget allokiert" value={formatCurrency(allocation?.summary?.total_budget_allocated)} tone="accent" />
                <OperatorStat label="Top-Budgetanteil" value={formatFractionPercent(topBudgetShare, 1)} />
                <OperatorStat label="Empfohlene Spitze" value={formatCurrency(leadBudget)} />
                <OperatorStat label="Spend-Status" value={leadSpendGate || '-'} />
              </div>

              <div className="workspace-note-card">
                {focusedAllocation
                  ? `${focusedAllocation.bundesland_name} erhält im aktuellen Scope ${formatCurrency(focusedAllocation.suggested_budget_amount)} bei ${formatFractionPercent(focusedAllocation.suggested_budget_share, 1)} Budgetanteil.`
                  : 'Für den aktuellen Fokus liegt noch keine Budgetempfehlung vor.'}
              </div>

              <div className="ops-region-list">
                {filteredAllocation.slice(0, 3).map((item) => (
                  <button
                    key={`allocation-${item.bundesland}`}
                    type="button"
                    className="campaign-list-card"
                    onClick={() => setSelectedRegion(item.bundesland)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                      <div style={{ textAlign: 'left' }}>
                        <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>{item.bundesland_name}</div>
                        <div className="ops-row-meta">
                          {item.products?.join(', ') || 'GELO Portfolio'} · {displayStage(item.recommended_activation_level)}
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div className="ops-number-emphasis">{formatCurrency(item.suggested_budget_amount)}</div>
                        <div className="ops-row-meta">{formatFractionPercent(item.suggested_budget_share, 1)} Anteil</div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </OperatorPanel>

            <OperatorPanel
              title="Unsicherheit / Evidenz"
              description="Unsicherheit wird nie nur farblich gezeigt. Hier steht immer auch der kurze Text, warum das Signal belastbar ist oder wo es noch kippen kann."
            >
              <div className="operator-stat-grid metric-strip">
                <OperatorStat label="Forecast-Sicherheit" value={formatFractionPercent(focusedPrediction?.decision?.forecast_confidence, 0)} />
                <OperatorStat label="Datenfrische" value={formatFractionPercent(focusedPrediction?.decision?.source_freshness_score, 0)} />
                <OperatorStat label="Revisionsrisiko" value={formatFractionPercent(focusedPrediction?.decision?.source_revision_risk, 0)} />
                <OperatorStat label="Quellenabgleich" value={formatFractionPercent(focusedPrediction?.decision?.cross_source_agreement_score, 0)} />
              </div>

              <div className="workspace-note-list">
                <div className="workspace-note-card">
                  <strong>Warum liegt {leadRegionName} vorne?</strong> {forecastSummary}
                </div>
                <div className="workspace-note-card">
                  <strong>{COCKPIT_SEMANTICS.uncertainty.label}:</strong> {uncertaintySummary}
                </div>
                <div className="workspace-note-card">
                  <strong>Evidenzstatus:</strong> {leadEvidenceLabel}. <strong>Spend-Status:</strong> {leadSpendGateLabel}.
                  {leadEvidenceHelper ? ` ${leadEvidenceHelper}` : ''}{leadSpendGateHelper ? ` ${leadSpendGateHelper}` : ''}
                </div>
              </div>
            </OperatorPanel>
          </section>

          <CollapsibleSection
            title="Weitere operative Details"
            subtitle="Nur für den zweiten Blick: Verteilung, Tabellen und Klartext-Begründungen."
          >
            <div className="ops-panel-grid" id={detailSectionId}>
              <OperatorPanel
                title="Stufen nach Entscheidung"
                description="Verteilung der Regionen nach Entscheidungsrang."
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
                                <div className="ops-row-meta">Entscheidungsrang #{item.decision_rank ?? item.rank ?? '-'}</div>
                              </div>
                              <div style={{ textAlign: 'right' }}>
                                <div className="ops-number-emphasis">{formatFractionPercent(item.event_probability_calibrated, 0)}</div>
                                <div className="ops-row-meta">{formatPercent(item.change_pct, 0)}</div>
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
                title="Regionen-Ranking"
                description="Volle Tabelle für Forecast, Rang und erste Begründung."
              >
                <div className="ops-table-wrap">
                  <table className="ops-table" id={regionTableId}>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Bundesland</th>
                        <th>Stufe</th>
                        <th>{eventProbabilityLabel}</th>
                        <th>Trend</th>
                        <th>{priorityScoreLabel}</th>
                        <th>Forecast-Sicherheit</th>
                        <th>Warum jetzt</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredPredictions.length > 0 ? filteredPredictions.map((item) => (
                        <tr
                          key={item.bundesland}
                          onClick={() => setSelectedRegion(item.bundesland)}
                          onKeyDown={(event) => handleInteractiveRowKeyDown(event, item.bundesland)}
                          tabIndex={0}
                          role="button"
                          aria-label={`${item.bundesland_name} auswählen`}
                          aria-pressed={selectedRegion === item.bundesland}
                        >
                          <td>{item.decision_rank ?? item.rank ?? '-'}</td>
                          <td>
                            <strong>{item.bundesland_name}</strong>
                            <div className="ops-row-meta">{UI_COPY.stateLevelScope} · {item.bundesland}</div>
                          </td>
                          <td><StageBadge value={item.decision_label} /></td>
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
            </div>

            <div className="ops-panel-grid">
              <OperatorPanel
                title="Budgetlogik"
                description="Volle Allokationstabelle mit Spend-Status."
              >
                <div className="ops-table-wrap">
                  <table className="ops-table" id={allocationTableId}>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Bundesland</th>
                        <th>Aktivierungsstufe</th>
                        <th>Budget</th>
                        <th>Budgetanteil</th>
                        <th>Allokations-Sicherheit</th>
                        <th>Spend-Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredAllocation.length > 0 ? filteredAllocation.map((item) => (
                        <tr
                          key={item.bundesland}
                          onClick={() => setSelectedRegion(item.bundesland)}
                          onKeyDown={(event) => handleInteractiveRowKeyDown(event, item.bundesland)}
                          tabIndex={0}
                          role="button"
                          aria-label={`${item.bundesland_name} in Budgettabelle auswählen`}
                          aria-pressed={selectedRegion === item.bundesland}
                        >
                          <td>{item.priority_rank ?? '-'}</td>
                          <td>
                            <strong>{item.bundesland_name}</strong>
                            <div className="ops-row-meta">{item.products?.join(', ') || 'GELO Portfolio'}</div>
                          </td>
                          <td><StageBadge value={item.recommended_activation_level} /></td>
                          <td>{formatCurrency(item.suggested_budget_amount)}</td>
                          <td>{formatFractionPercent(item.suggested_budget_share, 1)}</td>
                          <td>{formatFractionPercent(item.confidence, 0)}</td>
                          <td><StatusBadge value={item.spend_gate_status || 'observe_only'} /></td>
                        </tr>
                      )) : (
                        <tr>
                          <td colSpan={7} className="ops-table-empty">Keine Budgetempfehlungen im aktuellen Filter.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <OperatorChipRail className="review-chip-row">
                  <span className="step-chip">Budget gesamt {formatCurrency(allocation?.summary?.total_budget_allocated)}</span>
                  <span className="step-chip">Anteil gesamt {formatFractionPercent(allocation?.summary?.budget_share_total, 1)}</span>
                  <span className="step-chip">Spend offen {allocation?.summary?.spend_enabled ? 'ja' : 'nein'}</span>
                </OperatorChipRail>
              </OperatorPanel>

              <OperatorPanel
                title="Empfehlungsansicht"
                description="Konkrete Aktivierungsvorschläge mit Produktcluster, Keywordcluster und Guardrails."
              >
                {filteredCampaigns.length > 0 ? (
                  <div className="ops-recommendation-grid">
                    {filteredCampaigns.slice(0, 2).map((item) => (
                      <div key={`${item.region}-${item.recommended_product_cluster.cluster_key}`} className="campaign-list-card">
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>{item.region_name}</div>
                            <div className="ops-row-meta">{item.recommended_product_cluster.label} · {item.recommended_keyword_cluster.label}</div>
                          </div>
                          <StageBadge value={item.activation_level} />
                        </div>
                        <div className="operator-stat-grid metric-strip" style={{ marginTop: 12 }}>
                          <OperatorStat label="Budget" value={formatCurrency(item.suggested_budget_amount)} tone="accent" />
                          <OperatorStat label="Budgetanteil" value={formatFractionPercent(item.suggested_budget_share, 1)} />
                          <OperatorStat label="Signal-Sicherheit" value={formatFractionPercent(item.confidence, 0)} />
                          <OperatorStat label="Evidenz" value={evidenceStatusLabel(item.evidence_class)} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="soft-panel" style={{ padding: 18, color: 'var(--text-secondary)' }}>
                    Für den aktuellen Filter gibt es noch keinen konkreten Kampagnenvorschlag.
                  </div>
                )}
              </OperatorPanel>
            </div>

            <OperatorSection
              title="Begründungen im Klartext"
              description="Forecast-/Decision-Gründe, Allocation-Hebel und Campaign-Rationale bleiben gesammelt in der zweiten Ebene."
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
          </CollapsibleSection>
        </>
      )}
    </div>
  );
};

export default OperationalDashboard;
