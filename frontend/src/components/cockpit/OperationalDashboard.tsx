import React, { useEffect, useId, useMemo, useState } from 'react';

import CollapsibleSection from '../CollapsibleSection';
import { evidenceStatusHelper, evidenceStatusLabel } from '../../lib/copy';
import { explainInPlainGerman } from '../../lib/plainLanguage';
import {
  RegionalAllocationRecommendation,
  RegionalAllocationResponse,
  RegionalCampaignRecommendation,
  RegionalCampaignRecommendationsResponse,
  RegionalDecisionReasonTrace,
  RegionalForecastPrediction,
  RegionalForecastResponse,
  StructuredReasonItem,
} from '../../types/media';
import { formatDateTime, formatPercent, VIRUS_OPTIONS } from './cockpitUtils';
import { OperatorChipRail, OperatorPanel, OperatorSection } from './operator/OperatorPrimitives';
import RegionMap, { RegionMapRegion } from './RegionMap';
import ActionPanel from './operational-dashboard/ActionPanel';
import CampaignDetailPanel from './operational-dashboard/CampaignDetailPanel';
import EvidencePanel from './operational-dashboard/EvidencePanel';
import RegionTicker from './operational-dashboard/RegionTicker';
import TracePanel from './operational-dashboard/TracePanel';
import { OperationalRegionRow } from './operational-dashboard/types';

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

function formatFractionPercent(value?: number | null, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '-';
  const pct = value <= 1 ? value * 100 : value;
  return formatPercent(pct, digits);
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

function trendLabel(value?: number | null, fallback?: string | null): string {
  if (value == null || Number.isNaN(value)) return fallback || 'stabil';
  if (value > 1) return 'steigend';
  if (value < -1) return 'fallend';
  return fallback || 'stabil';
}

function actionLabel(stage?: string | null): string {
  const normalized = normalizeStage(stage);
  if (normalized === 'activate') return 'Freigeben';
  if (normalized === 'prepare') return 'Prüfen';
  return 'Beobachten';
}

function toIsoRegionId(code: string): string {
  return code.startsWith('DE-') ? code : `DE-${code}`;
}

function fromIsoRegionId(code: string): string {
  return code.startsWith('DE-') ? code.slice(3) : code;
}

function sortRows(items: OperationalRegionRow[]): OperationalRegionRow[] {
  return [...items].sort((left, right) => {
    const leftRank = Number(left.rank ?? Number.MAX_SAFE_INTEGER);
    const rightRank = Number(right.rank ?? Number.MAX_SAFE_INTEGER);
    if (leftRank !== rightRank) return leftRank - rightRank;
    return Number(right.eventProbability || 0) - Number(left.eventProbability || 0);
  });
}

function getStageFromSources(
  prediction?: RegionalForecastPrediction | null,
  allocationItem?: RegionalAllocationRecommendation | null,
  campaign?: RegionalCampaignRecommendation | null,
): string {
  return displayStage(
    campaign?.activation_level
      || allocationItem?.recommended_activation_level
      || allocationItem?.decision_label
      || prediction?.decision_label
      || prediction?.decision?.stage
      || 'Watch',
  );
}

function buildOperationalRows(
  forecast: RegionalForecastResponse | null,
  allocation: RegionalAllocationResponse | null,
  campaignRecommendations: RegionalCampaignRecommendationsResponse | null,
): OperationalRegionRow[] {
  const predictionByCode = new Map((forecast?.predictions || []).map((item) => [item.bundesland, item]));
  const allocationByCode = new Map((allocation?.recommendations || []).map((item) => [item.bundesland, item]));
  const campaignByCode = new Map((campaignRecommendations?.recommendations || []).map((item) => [item.region, item]));

  const regionCodes = new Set<string>([
    ...Array.from(predictionByCode.keys()),
    ...Array.from(allocationByCode.keys()),
    ...Array.from(campaignByCode.keys()),
  ]);

  return sortRows(Array.from(regionCodes).map((code) => {
    const prediction = predictionByCode.get(code);
    const allocationItem = allocationByCode.get(code);
    const campaign = campaignByCode.get(code);
    const stage = getStageFromSources(prediction, allocationItem, campaign);

    const decisionTrace = [
      ...traceSectionLines(
        prediction?.reason_trace?.why_details,
        prediction?.reason_trace?.why,
      ),
      ...traceSectionLines(
        prediction?.decision?.reason_trace?.why_details,
        prediction?.decision?.reason_trace?.why,
      ),
    ];

    const recommendationTrace = campaign ? [
      ...traceSectionLines(
        campaign.recommendation_rationale?.why_details,
        campaign.recommendation_rationale?.why,
      ),
      ...traceSectionLines(
        campaign.recommendation_rationale?.product_fit_details,
        campaign.recommendation_rationale?.product_fit,
      ),
      ...traceSectionLines(
        campaign.recommendation_rationale?.guardrail_details,
        campaign.recommendation_rationale?.guardrails,
      ),
    ] : [];

    const evidenceKey = campaign?.evidence_class || allocationItem?.evidence_status || forecast?.evidence_tier || 'epidemiological_only';
    const businessGateKey = campaign?.spend_guardrail_status || allocationItem?.spend_gate_status || allocationItem?.budget_release_recommendation || 'observe_only';

    return {
      code,
      name: campaign?.region_name || allocationItem?.bundesland_name || prediction?.bundesland_name || code,
      rank: prediction?.decision_rank ?? prediction?.rank ?? allocationItem?.priority_rank ?? allocationItem?.rank ?? campaign?.priority_rank ?? null,
      stage,
      eventProbability: prediction?.event_probability_calibrated ?? allocationItem?.event_probability ?? prediction?.decision?.event_probability ?? null,
      trendLabel: trendLabel(prediction?.change_pct ?? allocationItem?.change_pct, prediction?.trend || allocationItem?.trend),
      trendPercent: prediction?.change_pct ?? allocationItem?.change_pct ?? null,
      budgetAmount: campaign?.suggested_budget_amount ?? allocationItem?.suggested_budget_amount ?? allocationItem?.budget_eur ?? null,
      budgetShare: campaign?.suggested_budget_share ?? allocationItem?.suggested_budget_share ?? allocationItem?.budget_share ?? null,
      productCluster: campaign?.recommended_product_cluster?.label || allocationItem?.products?.[0] || 'GELO Portfolio',
      keywordCluster: campaign?.recommended_keyword_cluster?.label || 'Keyword-Cluster folgt aus der Auswahl',
      keywords: campaign?.keywords || campaign?.recommended_keyword_cluster?.keywords || [],
      channels: campaign?.channels || allocationItem?.channels || [],
      signalStrength: prediction?.decision?.decision_score ?? prediction?.priority_score ?? allocationItem?.allocation_score ?? campaign?.confidence ?? null,
      businessGateLabel: evidenceStatusLabel(businessGateKey),
      businessGateHelper: evidenceStatusHelper(businessGateKey),
      evidenceLabel: evidenceStatusLabel(evidenceKey),
      evidenceHelper: evidenceStatusHelper(evidenceKey),
      actionLabel: actionLabel(stage),
      summary: firstReasonLine([
        prediction?.decision?.explanation_summary_detail,
        prediction?.decision?.explanation_summary,
        prediction?.reason_trace?.why_details?.[0],
        prediction?.reason_trace?.why?.[0],
        campaign?.recommendation_rationale?.why_details?.[0],
        campaign?.recommendation_rationale?.why?.[0],
        'Noch keine kompakte Begründung verfügbar.',
      ]),
      uncertainty: firstReasonLine([
        prediction?.decision?.uncertainty_summary_detail,
        prediction?.decision?.uncertainty_summary,
        prediction?.uncertainty_summary,
        ...(prediction?.reason_trace?.uncertainty_details || []),
        ...(prediction?.reason_trace?.uncertainty || []),
        allocationItem?.uncertainty_summary,
        ...reasonTraceLines(allocationItem?.allocation_reason_trace || allocationItem?.reason_trace),
        'Noch keine kompakte Unsicherheitsnote verfügbar.',
      ]),
      forecastConfidence: prediction?.decision?.forecast_confidence ?? allocationItem?.confidence ?? campaign?.confidence ?? null,
      sourceFreshness: prediction?.decision?.source_freshness_score ?? null,
      revisionRisk: prediction?.decision?.source_revision_risk ?? null,
      crossSourceAgreement: prediction?.decision?.cross_source_agreement_score ?? null,
      decisionTrace,
      allocationTrace: reasonTraceLines(allocationItem?.allocation_reason_trace || allocationItem?.reason_trace),
      recommendationTrace,
    };
  }));
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
  const dashboardId = useId();

  const rows = useMemo(
    () => buildOperationalRows(forecast, allocation, campaignRecommendations),
    [forecast, allocation, campaignRecommendations],
  );

  const supportedHorizons = forecast?.supported_horizon_days || HORIZON_OPTIONS;
  const regionOptions = rows.map((row) => ({ code: row.code, name: row.name }));

  useEffect(() => {
    const availableCodes = new Set(regionOptions.map((item) => item.code));
    if (selectedRegion !== REGION_FILTER_ALL && !availableCodes.has(selectedRegion)) {
      setSelectedRegion(REGION_FILTER_ALL);
    }
  }, [regionOptions, selectedRegion]);

  const focusedRow = useMemo(() => {
    if (rows.length === 0) return null;
    if (selectedRegion !== REGION_FILTER_ALL) {
      return rows.find((row) => row.code === selectedRegion) || rows[0];
    }
    return rows[0];
  }, [rows, selectedRegion]);

  const hasOperationalData = rows.length > 0;
  const emptyStatus = forecast?.status || allocation?.status || campaignRecommendations?.status;
  const emptyMessage = forecast?.message || allocation?.message || campaignRecommendations?.message;
  const lastUpdated = [forecast?.generated_at, allocation?.generated_at, campaignRecommendations?.generated_at]
    .filter(Boolean)
    .sort()
    .slice(-1)[0];

  const regionTickerRows = rows.slice(0, 16);
  const mapRegions = useMemo<RegionMapRegion[]>(
    () => rows.map((row) => ({
      region_id: toIsoRegionId(row.code),
      region_name: row.name,
      decision_stage: normalizeStage(row.stage) === 'activate'
        ? 'activate'
        : normalizeStage(row.stage) === 'prepare'
          ? 'prepare'
          : 'watch',
      signal_score: row.signalStrength ?? row.eventProbability ?? undefined,
    })),
    [rows],
  );

  const handleRowAction = (row: OperationalRegionRow) => {
    if (normalizeStage(row.stage) === 'watch') {
      onOpenRegions(row.code);
      return;
    }
    onOpenCampaigns();
  };

  if (loading && !forecast && !allocation && !campaignRecommendations) {
    return (
      <OperatorSection
        kicker="Operational Dashboard"
        title="Dashboard wird aufgebaut"
        description="Filter, Fokusregion und Detailbereiche werden gerade zusammengesetzt."
      >
        <div className="workspace-note-card" role="status" aria-live="polite">
          Lade operatives Dashboard...
        </div>
      </OperatorSection>
    );
  }

  return (
    <div className="page-stack operator-page ops-command-dashboard" id={dashboardId}>
      <section className="ops-command-toolbar" aria-label="Sticky Filterleiste">
        <div className="ops-command-toolbar__grid">
          <label className="ops-command-filter">
            <span className="ops-command-filter__label">Virus</span>
            <select value={virus} onChange={(event) => onVirusChange(event.target.value)} className="media-input ops-command-filter__select">
              {VIRUS_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>

          <label className="ops-command-filter">
            <span className="ops-command-filter__label">Horizont</span>
            <select value={horizonDays} onChange={(event) => onHorizonChange(Number(event.target.value))} className="media-input ops-command-filter__select">
              {supportedHorizons.map((option) => (
                <option key={option} value={option}>{option} Tage</option>
              ))}
            </select>
          </label>

          <label className="ops-command-filter">
            <span className="ops-command-filter__label">Region</span>
            <select value={selectedRegion} onChange={(event) => setSelectedRegion(event.target.value)} className="media-input ops-command-filter__select">
              <option value={REGION_FILTER_ALL}>Alle Bundesländer</option>
              {regionOptions.map((item) => (
                <option key={item.code} value={item.code}>{item.name}</option>
              ))}
            </select>
          </label>

          <OperatorChipRail className="ops-command-toolbar__meta">
            <span className="step-chip">Stand: {formatDateTime(lastUpdated)}</span>
            <span className="step-chip">Budgetrahmen {new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(weeklyBudget)}</span>
            <span className="step-chip">Bundesland-Ebene</span>
          </OperatorChipRail>
        </div>
      </section>

      {!hasOperationalData && !loading ? (
        <OperatorSection
          kicker="Operational Dashboard"
          title={emptyStatus === 'no_model' ? 'Für diesen Scope ist noch kein regionales Modell verfügbar.' : 'Für diesen Scope liegt noch keine belastbare Lage vor.'}
          description={emptyMessage || 'Bitte Virus oder Horizont wechseln und die Datenlage erneut prüfen.'}
        >
          <OperatorChipRail className="review-chip-row">
            <span className="step-chip">Virus {virus}</span>
            <span className="step-chip">Horizont {horizonDays} Tage</span>
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
      ) : focusedRow ? (
        <>
          <OperatorSection
            kicker="Operational Dashboard"
            title="Wo jetzt gehandelt werden sollte"
            description="Karte und Fokusfall beantworten zuerst Auswahl, Priorität und Freigabereife. Alles Weitere klappt erst bei Bedarf auf."
            tone="accent"
            className="ops-command-hero-section"
          >
            <div className="ops-command-hero">
              <OperatorPanel
                eyebrow="Bundesland-Karte"
                title="Regionale Lage nach Entscheidungsstufe"
                description="Activate, Prepare und Watch bleiben sofort sichtbar. Ein Klick auf ein Bundesland wechselt den Fokusfall."
                className="ops-command-map-panel"
              >
                <RegionMap
                  regions={mapRegions}
                  selectedRegion={toIsoRegionId(focusedRow.code)}
                  onRegionClick={(regionId) => setSelectedRegion(fromIsoRegionId(regionId))}
                />
              </OperatorPanel>

              <ActionPanel
                row={focusedRow}
                virus={virus}
                horizonDays={horizonDays}
                onOpenDetails={onOpenRegions}
                onOpenApproval={onOpenCampaigns}
              />
            </div>
          </OperatorSection>

          <OperatorSection
            kicker="Regionen-Ticker"
            title="Alle Bundesländer in einer Zeile"
            description="Die Tabelle bleibt kompakt: Rang, Stage, Trend, Budget und die direkt passende Aktion."
            className="ops-command-ticker-section"
          >
            <RegionTicker
              rows={regionTickerRows}
              selectedRegion={focusedRow.code}
              onSelectRegion={setSelectedRegion}
              onAction={handleRowAction}
            />
          </OperatorSection>

          <div className="ops-command-expandables">
            <CollapsibleSection
              title="Evidenz"
              subtitle="Forecast-Qualität, Unsicherheit und Backtest-Scores."
              className="ops-command-collapsible"
            >
              <EvidencePanel row={focusedRow} onOpenEvidence={onOpenEvidence} />
            </CollapsibleSection>

            <CollapsibleSection
              title="Kampagnen-Detail"
              subtitle="Produktcluster, Keywords, Spend-Gate und Rationale."
              className="ops-command-collapsible"
            >
              <CampaignDetailPanel row={focusedRow} onOpenCampaigns={onOpenCampaigns} />
            </CollapsibleSection>

            <CollapsibleSection
              title="Nachvollziehbarkeit"
              subtitle="Decision, Allocation und Recommendation Traces nebeneinander."
              className="ops-command-collapsible"
            >
              <TracePanel row={focusedRow} />
            </CollapsibleSection>
          </div>
        </>
      ) : null}
    </div>
  );
};

export default OperationalDashboard;
